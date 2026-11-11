import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from folder_ledger.__main__ import main
from folder_ledger.reports import write_report
from folder_ledger.scan import scan


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'input'
        self.root.mkdir()
        (self.root / 'a.txt').write_bytes(b'abc')
        self.result = scan(self.root)

    def test_json_and_csv_reports(self):
        for kind in ('json', 'csv'):
            out = self.parent / ('report.' + kind)
            write_report(self.result, self.root, out, kind)
            self.assertTrue(out.exists())
            if kind == 'json':
                self.assertEqual(json.loads(out.read_text()), self.result)
            else:
                rows = list(csv.DictReader(io.StringIO(out.read_text())))
                self.assertEqual(rows[0]['path'], 'a.txt')
                self.assertEqual(rows[0]['size'], '3')
                self.assertEqual(rows[0]['sha256'], '')

    def test_refuses_overwrite_unless_forced(self):
        out = self.parent / 'report.json'
        out.write_text('original')
        with self.assertRaises(FileExistsError):
            write_report(self.result, self.root, out)
        self.assertEqual(out.read_text(), 'original')
        write_report(self.result, self.root, out, force=True)
        self.assertEqual(json.loads(out.read_text()), self.result)

    def test_refuses_report_inside_input_even_with_force(self):
        for output in (self.root / 'out.json', self.root / 'a.txt'):
            with self.assertRaises(ValueError):
                write_report(self.result, self.root, output, force=True)
        self.assertEqual((self.root / 'a.txt').read_bytes(), b'abc')

    def test_refuses_symlink_output_parent_into_input(self):
        alias = self.parent / 'alias'
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest('OS does not allow symlinks')
        with self.assertRaises(ValueError):
            write_report(self.result, self.root, alias / 'report.json')

    def test_cli_json_duplicates_and_exit_codes(self):
        (self.root / 'b.txt').write_bytes(b'abc')
        out = self.parent / 'report.json'
        proc = subprocess.run([sys.executable, '-m', 'folder_ledger', str(self.root),
                               '--duplicates', '--output', str(out)],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(out.exists())
        self.assertEqual(json.loads(out.read_text())['duplicates'], [['a.txt', 'b.txt']])
        self.assertIn('2 files', proc.stdout)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root / 'missing')]), 2)
        incomplete = dict(self.result, errors=[{'path': 'x', 'error': 'denied'}])
        with patch('folder_ledger.__main__.scan', return_value=incomplete, create=True):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(self.root)]), 1)

    def test_force_replaces_hardlink_without_modifying_input(self):
        import os
        out = self.parent / 'linked.json'
        os.link(self.root / 'a.txt', out)
        write_report(self.result, self.root, out, force=True)
        self.assertEqual((self.root / 'a.txt').read_bytes(), b'abc')
        self.assertEqual(json.loads(out.read_text()), self.result)

    def test_repeated_json_has_identical_bytes(self):
        first, second = self.parent / 'one.json', self.parent / 'two.json'
        write_report(self.result, self.root, first)
        write_report(scan(self.root), self.root, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_unencodable_csv_name_fails_without_creating_report(self):
        result = dict(self.result, files=[dict(self.result['files'][0], path='bad\udcff')])
        out = self.parent / 'bad.csv'
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            write_report(result, self.root, out, 'csv')
        self.assertFalse(out.exists())
        with patch('folder_ledger.__main__.scan', return_value=result):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(self.root), '--output', str(out), '--format', 'csv']), 2)
        self.assertFalse(out.exists())
        json_out = self.parent / 'bad.json'
        write_report(result, self.root, json_out)
        self.assertEqual(json.loads(json_out.read_text())['files'][0]['path'], 'bad\udcff')


if __name__ == '__main__':
    unittest.main()
