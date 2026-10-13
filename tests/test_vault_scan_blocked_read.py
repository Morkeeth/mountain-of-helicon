"""A note that is not on the disk must not hang the vault scan.

An iCloud vault holds notes whose bytes are not downloaded. Opening one can block
with no end, and one such note (Untitled.md) hung a full scan. Each test runs the
scan in a worker with a deadline, so a hang is a failed assert and not a stuck suite.
"""
import builtins
import logging
import os
import threading
import types

import pytest

from helicon.connectors import obsidian

DEADLINE = 6.0


def _vault(tmp_path):
    vault = tmp_path / "vault"
    (vault / "01 Projects").mkdir(parents=True)
    (vault / "01 Projects" / "Kite.md").write_text("# Kite stall\nThe kite stall sells kites.\n", encoding="utf-8")
    (vault / "Bakery.md").write_text("# Bakery\nThe bakery orders flour on Monday.\n", encoding="utf-8")
    (vault / "Untitled.md").write_text("# Untitled\nThis note is not on the disk.\n", encoding="utf-8")
    return vault


def _scan(vault, **config):
    """Run the scan with a deadline. Returns its results, or fails when it hangs."""
    box = {}
    worker = threading.Thread(
        target=lambda: box.setdefault("results", obsidian.scan({"vault_path": str(vault), **config})), daemon=True)
    worker.start()
    worker.join(DEADLINE)
    assert not worker.is_alive(), "the vault scan hung on a note that could not be read"
    return box["results"]


def _titles(results):
    return sorted(r.title for r in results)


def test_scan_skips_a_note_whose_read_blocks_and_says_so(tmp_path, monkeypatch, caplog):
    vault = _vault(tmp_path)
    release = threading.Event()

    def blocking_open(path, *args, **kwargs):
        if str(path).endswith("Untitled.md"):
            release.wait(60)  # the stand-in for a download that never arrives
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(obsidian, "open", blocking_open, raising=False)
    try:
        with caplog.at_level(logging.WARNING, logger=obsidian.__name__):
            results = _scan(vault, read_timeout=0.3)
    finally:
        release.set()
    assert _titles(results) == ["Bakery", "Kite stall"]
    assert any("Untitled.md" in m and "did not finish in 0.3 s" in m for m in caplog.messages)
    assert any("1 note(s) skipped" in m for m in caplog.messages)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a named pipe")
def test_scan_skips_a_file_that_is_not_a_regular_file(tmp_path, caplog):
    vault = _vault(tmp_path)
    pipe = vault / "Pipe.md"
    os.mkfifo(pipe)  # a read-open of a pipe blocks until a writer comes; none does
    try:
        with caplog.at_level(logging.WARNING, logger=obsidian.__name__):
            results = _scan(vault)
    finally:
        try:  # let a reader that did block go, so no thread outlives the test
            os.close(os.open(pipe, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
    assert _titles(results) == ["Bakery", "Kite stall", "Untitled"]
    assert any("Pipe.md" in m and "not a regular file" in m for m in caplog.messages)


def test_scan_does_not_open_a_file_marked_as_not_downloaded(tmp_path, monkeypatch, caplog):
    vault = _vault(tmp_path)
    real_stat, opened = os.stat, []

    def stat_with_flag(path, *args, **kwargs):
        info = real_stat(path, *args, **kwargs)
        if str(path).endswith("Untitled.md"):
            return types.SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size, st_mtime=info.st_mtime,
                                         st_flags=0x40000000)
        return info

    def watching_open(path, *args, **kwargs):
        opened.append(os.path.basename(str(path)))
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(obsidian.os, "stat", stat_with_flag)
    monkeypatch.setattr(obsidian, "open", watching_open, raising=False)
    with caplog.at_level(logging.WARNING, logger=obsidian.__name__):
        results = _scan(vault)
    assert _titles(results) == ["Bakery", "Kite stall"]
    assert "Untitled.md" not in opened
    assert any("Untitled.md" in m and "not downloaded" in m for m in caplog.messages)


def test_scan_names_an_icloud_placeholder(tmp_path, caplog):
    vault = _vault(tmp_path)
    (vault / ".Evicted.md.icloud").write_bytes(b"bplist00")
    with caplog.at_level(logging.WARNING, logger=obsidian.__name__):
        results = _scan(vault)
    assert _titles(results) == ["Bakery", "Kite stall", "Untitled"]
    assert any(".Evicted.md.icloud" in m and "iCloud placeholder" in m for m in caplog.messages)


def test_a_vault_with_every_note_on_disk_logs_nothing(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger=obsidian.__name__):
        results = _scan(_vault(tmp_path))
    assert _titles(results) == ["Bakery", "Kite stall", "Untitled"]
    assert caplog.messages == []
