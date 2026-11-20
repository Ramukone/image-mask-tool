import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from PIL import Image


class RegressionTests(unittest.TestCase):
    def test_unsigned_16bit_grayscale(self):
        values = [0, 128, 257, 16384, 32768, 65535]
        expected = [0, 0, 1, 64, 128, 255]
        with tempfile.TemporaryDirectory() as folder:
            for mode, suffix in [('I;16', '.tif'), ('I;16B', '.tif'), ('I;16', '.png')]:
                with self.subTest(mode=mode, suffix=suffix):
                    source = Image.new(mode, (len(values), 1))
                    source.putdata(values)
                    path = Path(folder) / ('gray' + suffix)
                    source.save(path)
                    actual = app.open_image(path)
                    self.assertEqual(list(actual.get_flattened_data()),
                                     [(v, v, v, 255) for v in expected])

    def test_failed_pair_rolls_back_only_new_output_and_retry_succeeds(self):
        image = Image.new('RGBA', (20, 20), 'red')
        points = [(1, 1), (18, 1), (10, 18)]
        save = app.unique_save
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / 'sample_选区内.png'
            existing.write_bytes(b'existing file must survive')

            def fail_second(image, folder, stem):
                if stem.endswith('选区外'):
                    raise OSError('second write failed')
                return save(image, folder, stem)

            with patch.object(app, 'unique_save', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'second write failed'):
                    app.save_selection(image, points, folder, 'sample', 'both')
            self.assertEqual(list(Path(folder).iterdir()), [existing])
            self.assertEqual(existing.read_bytes(), b'existing file must survive')
            outputs = app.save_selection(image, points, folder, 'sample', 'both')
            self.assertEqual([p.name for p in outputs],
                             ['sample_选区内_1.png', 'sample_选区外.png'])
            for output in outputs:
                with Image.open(output) as result:
                    self.assertEqual(result.size, image.size)

    def test_failed_rollback_reports_remaining_path(self):
        image = Image.new('RGBA', (20, 20), 'red')
        points = [(1, 1), (18, 1), (10, 18)]
        with tempfile.TemporaryDirectory() as folder:
            remaining = Path(folder) / 'sample_选区内.png'
            with patch.object(app, 'unique_save', side_effect=[remaining, OSError('disk full')]), \
                 patch.object(Path, 'unlink', side_effect=PermissionError('locked')):
                with self.assertRaises(OSError) as raised:
                    app.save_selection(image, points, folder, 'sample', 'both')
            self.assertIn(str(remaining), str(raised.exception))
            self.assertIn('disk full', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
