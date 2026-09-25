"""Open a path from a directory fd without following symlinks.

A check on the path string, followed by a later open() of that string, loses
to a symlink swapped in between the two. O_NOFOLLOW on a full path only covers
the last component, so a parent that is a symlink still redirects the open.
Walking from a held directory fd, one component at a time, ties the final
open to the directory that was walked, not to the path as it looks afterwards.
"""
from __future__ import annotations

import errno
import os
from contextlib import contextmanager

# macOS returns ENOTDIR for O_DIRECTORY|O_NOFOLLOW on a symlink to a directory.
# Linux returns ELOOP. Either one means the component was not opened as a
# real directory.
_SYMLINK_ERRNOS = {errno.ELOOP, errno.ENOTDIR}

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class SafeOpenError(Exception):
    """The path was not opened. reason is one short clause, with no newline."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _parts(relative: str) -> list[str]:
    if not relative or os.path.isabs(relative):
        raise SafeOpenError("the path is absolute")
    parts: list[str] = []
    for part in relative.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise SafeOpenError("the path contains '..'")
        parts.append(part)
    if not parts:
        raise SafeOpenError("the path is empty")
    return parts


def _close(fds: list[int]) -> None:
    for fd in reversed(fds):
        try:
            os.close(fd)
        except OSError:
            pass


def _open_dir(parent: int, name: str, *, create: bool) -> int:
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=parent)
    except FileNotFoundError:
        if not create:
            raise
    except OSError as exc:
        if exc.errno in _SYMLINK_ERRNOS:
            raise SafeOpenError("a directory on the path is a symlink") from exc
        raise
    try:
        os.mkdir(name, 0o755, dir_fd=parent)
    except FileExistsError:
        pass
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=parent)
    except OSError as exc:
        if exc.errno in _SYMLINK_ERRNOS:
            raise SafeOpenError("a directory on the path is a symlink") from exc
        raise


def _open_leaf(parent: int, name: str, *, write: bool) -> int:
    if write:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        mode = 0o644
    else:
        flags = os.O_RDONLY | os.O_NOFOLLOW
        mode = 0
    try:
        if write:
            return os.open(name, flags, mode, dir_fd=parent)
        return os.open(name, flags, dir_fd=parent)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SafeOpenError("it is a symlink") from exc
        raise


@contextmanager
def open_nofollow_leaf(directory: str, name: str, *, write: bool = False):
    """Yield name inside directory. directory is opened as a directory fd.

    name is one component. It is opened with O_NOFOLLOW, so a symlink at
    name is refused. directory itself is not walked: the caller resolved it.
    """
    if not name or name in (".", "..") or "/" in name:
        raise SafeOpenError("the path is empty")
    dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        leaf_fd = _open_leaf(dir_fd, name, write=write)
    except Exception:
        os.close(dir_fd)
        raise
    try:
        fileobj = os.fdopen(leaf_fd, "w" if write else "r", encoding="utf-8")
    except Exception:
        os.close(leaf_fd)
        os.close(dir_fd)
        raise
    try:
        yield fileobj
    finally:
        if not fileobj.closed:
            fileobj.close()
        os.close(dir_fd)


@contextmanager
def open_nofollow(root: str, relative: str, *, write: bool = False, create_parents: bool = False):
    """Yield a text file for relative under root.

    root is opened once, after realpath, as a directory fd. Each later
    component uses O_NOFOLLOW against the previous fd. '..' and an absolute
    relative path are refused. Missing directories are created only when
    create_parents is true, and only through that same fd walk.
    """
    parts = _parts(relative)
    directories, leaf = parts[:-1], parts[-1]
    fds: list[int] = []
    try:
        root_fd = os.open(os.path.realpath(root), _DIR_FLAGS)
        fds.append(root_fd)
        parent = root_fd
        for name in directories:
            parent = _open_dir(parent, name, create=create_parents)
            fds.append(parent)
        leaf_fd = _open_leaf(parent, leaf, write=write)
    except SafeOpenError:
        _close(fds)
        raise
    except OSError:
        _close(fds)
        raise

    try:
        fileobj = os.fdopen(leaf_fd, "w" if write else "r", encoding="utf-8")
    except Exception:
        os.close(leaf_fd)
        _close(fds)
        raise
    try:
        yield fileobj
    finally:
        if not fileobj.closed:
            fileobj.close()
        _close(fds)
