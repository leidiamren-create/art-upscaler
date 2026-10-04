"""Public-safe unit tests with synthetic images only; no external engine."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_target_dimensions(self):
        self.assertEqual(core.target_size((1536, 1024), 2048), (2048, 1365))
        self.assertEqual(core.target_size((1024, 1536), 2048), (1365, 2048))
        self.assertEqual(core.target_size((4000, 2000), 2048), (2048, 1024))
        self.assertEqual(core.target_size((1, 1000), 64), (1, 64))

    def test_settings_reject_nested_output(self):
        source = self.root / 'input'
        source.mkdir()
        nested = source / 'out'
        nested.mkdir()
        for output in (source, nested):
            with self.assertRaises(ValueError):
                core.Settings(str(source), str(output)).validate()

    def test_scan_filters_types_and_nested_files(self):
        (self.root / 'a.png').write_bytes(b'fixture')
        (self.root / 'ignored.txt').write_text('fixture')
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'b.JPG').write_bytes(b'fixture')
        self.assertEqual(len(core.scan_files(self.root, True)), 2)
        self.assertEqual(len(core.scan_files(self.root, False)), 1)

    def test_scan_does_not_follow_symlink(self):
        target = self.root / 'real.png'
        target.write_bytes(b'fixture')
        link = self.root / 'link.png'
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('Creating symlinks is unavailable on this system')
        self.assertEqual(core.scan_files(self.root), [target])

    def test_save_does_not_overwrite(self):
        image = Image.new('RGBA', (16, 8), (120, 20, 70, 80))
        destination = self.root / 'result.png'
        first = core.save_png_exclusive(image, destination)
        original = first.read_bytes()
        second = core.save_png_exclusive(image, destination)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), original)

    def test_transparent_no_inference_and_resize(self):
        source = self.root / 'transparent.png'
        Image.new('RGBA', (64, 32), (240, 10, 80, 0)).save(source)
        settings = core.Settings(str(self.root), target=128)
        before, after, note, method = core.process_image(source, settings, object(), threading.Event())
        self.assertEqual(after.size, (128, 64))
        self.assertEqual(after.getchannel('A').getextrema(), (0, 0))

    def test_resize_only_keeps_alpha_at_same_size(self):
        source = self.root / 'alpha.png'
        image = Image.new('RGBA', (128, 64), (20, 120, 210, 127))
        image.save(source)
        settings = core.Settings(str(self.root), target=128, noise=-1)
        before, after, note, method = core.process_image(source, settings, object(), threading.Event())
        self.assertEqual(after.getchannel('A').tobytes(), image.getchannel('A').tobytes())
        self.assertIn('仅尺寸调整', method)

    def test_high_depth_rejected(self):
        source = self.root / 'high-depth.png'
        Image.new('I;16', (16, 16), 1000).save(source)
        with self.assertRaisesRegex(ValueError, '16位/HDR'):
            core.read_image(source)

    def test_animation_rejected(self):
        source = self.root / 'animated.png'
        image = Image.new('RGBA', (16, 16), 'red')
        image.save(source, save_all=True, append_images=[Image.new('RGBA', (16, 16), 'blue')])
        with self.assertRaisesRegex(ValueError, '动画/多页'):
            core.read_image(source)

    def test_cancel_signal(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(core.Cancelled):
            core.check_cancel(cancel)

    def test_csv_formula_is_escaped(self):
        folder = self.root / 'report'
        folder.mkdir()
        batch = core.Batch(self.root / 'engine')
        batch.state['items'] = [{'name': '=test.png', 'status': 'error', 'error': '@formula'}]
        batch._report(folder, core.Settings(str(self.root)))
        csv = (folder / '处理报告.csv').read_text('utf-8-sig')
        self.assertIn("'=test.png", csv)
        self.assertIn("'@formula", csv)


if __name__ == '__main__':
    unittest.main()
