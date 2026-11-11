"""Filesystem traversal and content grouping; never modifies input files."""
from collections import defaultdict
from fnmatch import fnmatchcase
import hashlib
import os
from pathlib import Path
import stat


def _identity(info):
    # Windows lstat and fstat disagree about creation-time semantics.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & 0x400)


def _digest(path, expected):
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if _identity(before) != _identity(expected):
            raise OSError('File changed before hashing')
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise OSError('File changed while hashing')
    if _identity(path.lstat()) != _identity(expected):
        raise OSError('File changed after hashing')
    return digest.hexdigest()


def scan(root, excludes=(), hashes=False, duplicates=False):
    """Return a stable inventory; errors indicate an incomplete scan.

    Glob patterns match slash-separated relative paths, case sensitively.
    Symlinks and Windows reparse points are skipped, including directories.
    A concurrent filesystem writer can still race traversal: not a snapshot.
    """
    root = Path(root)
    try:
        info = root.lstat()
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError('Root must be a regular directory, not a link')
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError('Root cannot be accessed') from exc
    result = {'schema_version': 1, 'files': [], 'duplicates': [], 'errors': [], 'skipped': []}
    candidates = {}

    def error(relative, exc):
        result['errors'].append({'path': relative, 'error': str(exc)})

    def walk(directory):
        relative = directory.relative_to(root).as_posix()
        try:
            with os.scandir(directory) as entries:
                entries = sorted(entries, key=lambda entry: entry.name)
        except OSError as exc:
            error(relative, exc)
            return
        for entry in entries:
            path = Path(entry.path)
            rel = path.relative_to(root).as_posix()
            if any(fnmatchcase(rel, pattern) for pattern in excludes):
                continue
            try:
                # DirEntry.stat on Windows can omit the inode/device fields.
                info = path.lstat()
                if _is_link(info):
                    result['skipped'].append(rel)
                elif stat.S_ISDIR(info.st_mode):
                    walk(path)
                elif stat.S_ISREG(info.st_mode):
                    result['files'].append({'path': rel, 'size': info.st_size,
                                            'mtime_ns': info.st_mtime_ns, 'sha256': None})
                    candidates[rel] = (path, info)
                else:
                    result['skipped'].append(rel)
            except OSError as exc:
                error(rel, exc)

    walk(root)
    result['files'].sort(key=lambda record: record['path'])
    sizes = defaultdict(int)
    for record in result['files']:
        sizes[record['size']] += 1
    groups = defaultdict(list)
    for record in result['files']:
        if hashes or (duplicates and sizes[record['size']] > 1):
            try:
                record['sha256'] = _digest(*candidates[record['path']])
                groups[(record['size'], record['sha256'])].append(record['path'])
            except OSError as exc:
                error(record['path'], exc)
    if duplicates:
        result['duplicates'] = sorted((paths for paths in groups.values() if len(paths) > 1),
                                      key=lambda paths: paths[0])
    result['errors'].sort(key=lambda item: (item['path'], item['error']))
    result['skipped'].sort()
    return result
