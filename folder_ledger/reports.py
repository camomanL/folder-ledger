"""Stable serialization and explicit report-file writes."""
import csv
import io
import json
import os
from pathlib import Path
import tempfile


def write_report(result, root, output, format='json', force=False):
    """Write outside root, refusing replacement unless explicitly requested."""
    root = Path(root).resolve(strict=True)
    output = Path(output).absolute()
    parent = output.parent.resolve(strict=True)
    output = parent / output.name
    resolved = output.resolve()
    if resolved == root or root in resolved.parents:
        raise ValueError('Report must be outside the scanned tree')
    if output.is_symlink() or (hasattr(output, 'is_junction') and output.is_junction()):
        raise ValueError('Report path must not be a link')
    if format == 'json':
        content = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + '\n'
    elif format == 'csv':
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=('path', 'size', 'mtime_ns', 'sha256'),
                                lineterminator='\n')
        writer.writeheader()
        writer.writerows(result['files'])
        content = stream.getvalue()
    else:
        raise ValueError('Format must be json or csv')
    try:
        content.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError('CSV contains a filename that cannot be encoded as UTF-8; use JSON') from exc
    if not force:
        with output.open('x', encoding='utf-8', newline='') as stream:
            stream.write(content)
        return
    # Replace the directory entry, not a hard-linked input file's contents.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         dir=parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
