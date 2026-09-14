"""Reviewed, revision-bound edits to explicitly scoped UTF-8 context files.

No inference, ingestion, or model calls. Advisory locks serialize this service;
uncooperative external writers cannot be given a filesystem-wide CAS guarantee.
Full bytes and inode are checked immediately before atomic replacement. Durable
pending receipts make interrupted writes visible and recoverable without replay.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid


class CorrectionError(ValueError):
    pass


class CorrectionConflict(CorrectionError):
    pass


class CorrectionScopeError(CorrectionError):
    pass


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _actor(value):
    if not isinstance(value, str) or not value.strip():
        raise CorrectionError("An explicit actor is required (not authenticated by this service)")
    return value.strip()


class CorrectionStore:
    def __init__(self, state_dir, allowed_roots):
        # A disconnected project must not hide its saved correction history.
        # Availability is enforced by descriptor traversal at preview/apply/undo.
        self.roots = tuple(Path(p).expanduser().resolve(strict=False) for p in allowed_roots)
        if not self.roots or any((p.exists() and not p.is_dir()) or p == Path('/') for p in self.roots):
            raise CorrectionScopeError("Explicit non-root source directories are required")
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.db_path = self.state_dir / 'context-corrections.sqlite3'

    def _initialize(self):
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Backups can contain private prose. Never follow a swapped database link.
        fd = os.open(self.db_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS context_corrections '
                       '(id TEXT PRIMARY KEY, payload TEXT NOT NULL, before_bytes BLOB NOT NULL, '
                       'after_bytes BLOB NOT NULL, status TEXT NOT NULL, events TEXT NOT NULL)')

    @contextmanager
    def _db(self, readonly=False):
        db = (sqlite3.connect(self.db_path.as_uri() + '?mode=ro', uri=True, timeout=30)
              if readonly else sqlite3.connect(self.db_path, timeout=30))
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _scope(self, path):
        # Canonicalize system aliases in the root, never source-relative links.
        raw = Path(os.path.abspath(os.path.expanduser(str(path))))
        for root in sorted(self.roots, key=lambda p: len(p.parts), reverse=True):
            candidates = [root]
            if str(root).startswith('/private/'):
                candidates.append(Path(str(root)[8:]))
            for candidate in candidates:
                try:
                    rel = raw.relative_to(candidate)
                except ValueError:
                    continue
                target = root / rel
                if not rel.parts or target == self.state_dir or self.state_dir in target.parents:
                    raise CorrectionScopeError("Correction state is not an editable source")
                return root, rel, target
        raise CorrectionScopeError("Source is outside the explicitly allowed roots")

    @contextmanager
    def _source(self, path):
        root, rel, target = self._scope(path)
        fds = []
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            fds.append(parent)
            for part in (*root.parts[1:], *rel.parts[:-1]):
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                fds.append(parent)
            fd = os.open(rel.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            fds.append(fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4 * 1024 * 1024:
                raise CorrectionScopeError("Source must be a single-link regular text file under 4 MiB")
            data = b''
            while block := os.read(fd, 65536):
                data += block
                if len(data) > 4 * 1024 * 1024:
                    raise CorrectionScopeError("Source exceeds 4 MiB")
            try:
                data.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise CorrectionError("Source is not UTF-8 text") from exc
            if b'\x00' in data:
                raise CorrectionError("Source contains binary NUL bytes")
            yield target, parent, rel.name, info, data
        except OSError as exc:
            raise CorrectionScopeError(f"Source unavailable or unsafe: {exc.strerror}") from exc
        finally:
            for fd in reversed(fds):
                os.close(fd)

    @contextmanager
    def _lock(self):
        self._initialize()
        fd = os.open(self.state_dir / '.corrections.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _get(self, ident):
        with self._db() as db:
            row = db.execute('SELECT * FROM context_corrections WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise CorrectionError("Unknown correction")
        return row

    def _envelope(self, row):
        return {**json.loads(row['payload']), 'status': row['status'], 'events': json.loads(row['events'])}

    def _transition(self, ident, status, actor, detail=None):
        row = self._get(ident)
        events = json.loads(row['events'])
        events.append({'status': status, 'actor': actor, 'at': _now(), 'detail': detail})
        with self._db() as db:
            db.execute('UPDATE context_corrections SET status=?, events=? WHERE id=?',
                       (status, json.dumps(events), ident))
        return self._get(ident)

    def preview(self, path, source_hash, start_byte, end_byte, expected_text,
                replacement, actor, reason, finding_id=None):
        actor = _actor(actor)
        if not isinstance(reason, str) or not reason.strip():
            raise CorrectionError("A correction reason is required")
        if not isinstance(expected_text, str) or not isinstance(replacement, str) or '\x00' in replacement:
            raise CorrectionError("Expected text and replacement must be text without NUL")
        with self._lock(), self._source(path) as (target, _parent, _name, _info, before):
            if _hash(before) != source_hash:
                raise CorrectionConflict("Source changed since review")
            if (type(start_byte) is not int or type(end_byte) is not int
                    or not 0 <= start_byte <= end_byte <= len(before)):
                raise CorrectionError("Invalid byte span")
            if before[start_byte:end_byte] != expected_text.encode('utf-8'):
                raise CorrectionConflict("Reviewed span does not match exact source bytes")
            after = before[:start_byte] + replacement.encode('utf-8') + before[end_byte:]
            if len(after) > 4 * 1024 * 1024:
                raise CorrectionError("Corrected source exceeds 4 MiB")
            try:
                before[:start_byte].decode('utf-8')
                before[end_byte:].decode('utf-8')
                after.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise CorrectionError("Byte span splits a UTF-8 character") from exc
            if after == before:
                raise CorrectionError("Correction makes no change")
            ident = 'cc_' + uuid.uuid4().hex
            payload = dict(id=ident, correction_id=ident, preview_id=ident, path=str(target),
                           before_sha256=source_hash, after_sha256=_hash(after),
                           start_byte=start_byte, end_byte=end_byte, expected_text=expected_text,
                           replacement=replacement, actor=actor, reason=reason.strip(),
                           finding_id=finding_id, created_at=_now(),
                           diff=''.join(difflib.unified_diff(before.decode().splitlines(True),
                                     after.decode().splitlines(True), fromfile=str(target), tofile=str(target))))
            payload['preview_hash'] = _hash(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())
            events = [{'status': 'proposed', 'actor': actor, 'at': payload['created_at']}]
            with self._db() as db:
                db.execute('INSERT INTO context_corrections VALUES (?,?,?,?,?,?)',
                           (ident, json.dumps(payload), before, after, 'proposed', json.dumps(events)))
            return self._envelope(self._get(ident))

    def _recover(self, row):
        if row['status'] not in ('applying', 'undoing'):
            return row
        payload = json.loads(row['payload'])
        try:
            with self._source(payload['path']) as (_, _, _, _, data):
                current = _hash(data)
        except CorrectionError:
            return self._transition(row['id'], 'conflict', 'service:recovery', 'Source unavailable; no source write')
        if row['status'] == 'applying':
            status = ('applied' if current == payload['after_sha256'] else
                      'proposed' if current == payload['before_sha256'] else 'conflict')
        else:
            status = ('undone' if current == payload['before_sha256'] else
                      'applied' if current == payload['after_sha256'] else 'conflict')
        return self._transition(row['id'], status, 'service:recovery',
                                'Recovered by current source hash; no source write; causation not inferred')

    def _replace(self, target, parent, name, info, current, desired):
        temp = '.helicon-correction-' + uuid.uuid4().hex
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     stat.S_IMODE(info.st_mode), dir_fd=parent)
        try:
            os.fchmod(fd, stat.S_IMODE(info.st_mode))
            with os.fdopen(fd, 'wb') as stream:
                stream.write(desired)
                stream.flush()
                os.fsync(stream.fileno())
            # Reopen via the configured root: catches moved directories and link swaps.
            with self._source(target) as (_, _, _, checked, data):
                if (checked.st_dev, checked.st_ino) != (info.st_dev, info.st_ino) or data != current:
                    raise CorrectionConflict("Source changed before atomic replacement")
            os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass

    def _perform(self, row, actor, undo=False):
        payload = json.loads(row['payload'])
        expected = row['after_bytes'] if undo else row['before_bytes']
        desired = row['before_bytes'] if undo else row['after_bytes']
        with self._source(payload['path']) as (target, parent, name, info, current):
            if current != expected:
                raise CorrectionConflict("Source has later edits; correction refused")
            self._transition(row['id'], 'undoing' if undo else 'applying', actor)
            self._replace(target, parent, name, info, current, desired)
        with self._source(payload['path']) as (_, _, _, _, actual):
            if actual != desired:
                self._transition(row['id'], 'conflict', actor, 'Post-write verification failed')
                raise CorrectionConflict("Source changed during post-write verification")
        return self._envelope(self._transition(row['id'], 'undone' if undo else 'applied', actor))

    def apply(self, preview_id, preview_hash, actor):
        actor = _actor(actor)
        with self._lock():
            row = self._get(preview_id)
            payload = json.loads(row['payload'])
            self._scope(payload['path'])
            if payload['preview_hash'] != preview_hash:
                raise CorrectionConflict("Reviewed preview hash does not match")
            row = self._recover(row)
            if row['status'] == 'applied':
                return self._envelope(row)  # Receipt only; never replay an applied edit.
            if row['status'] != 'proposed':
                raise CorrectionConflict("Correction is not applicable; create a new review")
            return self._perform(row, actor)

    def undo(self, correction_id, actor):
        actor = _actor(actor)
        with self._lock():
            row = self._get(correction_id)
            self._scope(json.loads(row['payload'])['path'])
            row = self._recover(row)
            if row['status'] == 'undone':
                return self._envelope(row)
            if row['status'] != 'applied':
                raise CorrectionConflict("Only an applied correction can be undone")
            return self._perform(row, actor, undo=True)

    def history(self, path=None):
        selected = str(self._scope(path)[2]) if path is not None else None
        if not self.db_path.exists():
            return []
        with self._db(readonly=True) as db:
            rows = db.execute('SELECT * FROM context_corrections ORDER BY rowid DESC').fetchall()
            result = []
            for row in rows:
                item = json.loads(row['payload'])
                try:
                    self._scope(item['path'])
                except CorrectionScopeError:
                    continue
                if selected is None or selected == item['path']:
                    result.append(self._envelope(row))
            return result

    def recover(self, correction_id):
        """Explicit metadata reconciliation; never writes a source file."""
        with self._lock():
            row = self._get(correction_id)
            self._scope(json.loads(row['payload'])['path'])
            return self._envelope(self._recover(row))
