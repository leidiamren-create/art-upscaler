"""Exercise source-only packaging without touching real deliverables."""
import contextlib
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_source


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def setup_source(self, content='print("fixture")\n'):
        (self.root / 'app.py').write_text(content, encoding='utf-8')
        (self.root / 'SOURCE_FILES.txt').write_text('SOURCE_FILES.txt\napp.py\n', encoding='utf-8')

    def test_only_allowlisted_files_and_deterministic_zip(self):
        self.setup_source()
        (self.root / 'private.txt').write_text('not for distribution')
        with contextlib.redirect_stdout(io.StringIO()):
            first = build_source.build(self.root).read_bytes()
            output = build_source.build(self.root)
        self.assertEqual(first, output.read_bytes())
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            self.assertFalse(any('private' in name for name in archive.namelist()))

    def test_traversal_rejected(self):
        (self.root / 'SOURCE_FILES.txt').write_text('../outside.txt\n')
        with self.assertRaises(ValueError):
            build_source.source_files(self.root)

    def test_logs_rejected_even_when_listed(self):
        (self.root / 'logs').mkdir()
        (self.root / 'logs/report.txt').write_text('fixture')
        (self.root / 'SOURCE_FILES.txt').write_text('logs/report.txt\n')
        with self.assertRaises(ValueError):
            build_source.source_files(self.root)

    def test_credential_pattern_rejected(self):
        self.setup_source('value = "' + 'ghp_' + 'X' * 40 + '"\n')
        with self.assertRaises(ValueError):
            build_source.source_files(self.root)

    def test_binary_content_rejected(self):
        self.setup_source()
        (self.root / 'app.py').write_bytes(b'fixture\x00binary')
        with self.assertRaises(ValueError):
            build_source.source_files(self.root)


if __name__ == '__main__':
    unittest.main()
