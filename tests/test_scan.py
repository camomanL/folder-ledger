import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from folder_ledger.scan import scan, _digest


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_inventory_sorted_relative_paths_and_metadata(self):
        self.put('z.txt', b'123')
        self.put('nested/café.txt', b'xy')
        result = scan(self.root)
        self.assertEqual([f['path'] for f in result['files']], ['nested/café.txt', 'z.txt'])
        self.assertEqual([f['size'] for f in result['files']], [2, 3])
        self.assertIsInstance(result['files'][0]['mtime_ns'], int)
        self.assertIsNone(result['files'][0]['sha256'])
        self.assertEqual(result, scan(self.root))

    def test_hash_all_and_empty_tree(self):
        self.assertEqual(scan(self.root)['files'], [])
        self.put('a', b'abc')
        result = scan(self.root, hashes=True)
        self.assertEqual(len(result['files']), 1)
        self.assertEqual(result['files'][0]['sha256'],
                         'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

    def test_duplicate_candidates_not_just_sizes(self):
        self.put('a', b'abc')
        self.put('b', b'abc')
        self.put('c', b'xyz')
        self.put('solo', b'x')
        result = scan(self.root, duplicates=True)
        self.assertEqual(result['duplicates'], [['a', 'b']])
        self.assertIsNone(result['files'][-1]['sha256'])
        self.assertEqual(result['files'][2]['sha256'], hashlib.sha256(b'xyz').hexdigest())

    def test_exclusions_prune_directories(self):
        self.put('cache/nested/a', b'x')
        self.put('keep/a.tmp', b'x')
        self.put('keep/a.txt', b'x')
        result = scan(self.root, excludes=('cache', '*.tmp'))
        self.assertEqual([f['path'] for f in result['files']], ['keep/a.txt'])

    def test_invalid_root_is_rejected(self):
        with self.assertRaises(ValueError):
            scan(self.root / 'missing')
        path = self.put('file', b'')
        with self.assertRaises(ValueError):
            scan(path)

    def test_symlinks_are_skipped(self):
        self.put('a', b'a')
        try:
            (self.root / 'link').symlink_to(self.root / 'a')
        except OSError:
            self.skipTest('OS does not allow creating test symlinks')
        result = scan(self.root)
        self.assertEqual([f['path'] for f in result['files']], ['a'])
        self.assertEqual(result['skipped'], ['link'])

    def test_unreadable_hash_is_reported_without_false_duplicates(self):
        self.put('a', b'abc')
        with patch('folder_ledger.scan._digest', side_effect=PermissionError('denied')):
            result = scan(self.root, hashes=True)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['errors'][0]['path'], 'a')
        self.assertIsNone(result['files'][0]['sha256'])
        self.assertEqual(result['duplicates'], [])

    def test_changed_file_is_rejected_by_hash_check(self):
        path = self.put('a', b'abc')
        expected = path.stat()
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(OSError, 'changed'):
            _digest(path, expected)

    def test_empty_files_are_duplicates(self):
        self.put('a', b'')
        self.put('b', b'')
        self.assertEqual(scan(self.root, duplicates=True)['duplicates'], [['a', 'b']])


if __name__ == '__main__':
    unittest.main()
