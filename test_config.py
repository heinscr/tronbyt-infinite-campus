"""Offline installer configuration checks using synthetic values."""
from pathlib import Path
import tempfile
import unittest

from config import load_config, REQUIRED


class ConfigTests(unittest.TestCase):
    def settings(self):
        values = {key: 'example-value' for key in REQUIRED}
        values.update(IC_CAMPUS_URL='https://school.example/campus',
                      TRONBYT_SERVER_URL='http://localhost:8000',
                      IC_PASSWORD="'example&with#symbols=inside'")
        return values

    def load(self, values):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('\n'.join(f'{k}={v}' for k, v in values.items()), encoding='utf-8')
            return load_config(path)

    def test_quotes_and_password_symbols_preserved(self):
        config = self.load(self.settings())
        self.assertEqual(config['IC_PASSWORD'], 'example&with#symbols=inside')
        self.assertEqual(config['IC_CAMPUS_URL'], 'https://school.example/campus/')

    def test_campus_requires_https(self):
        with self.assertRaisesRegex(ValueError, 'IC_CAMPUS_URL'):
            self.load(dict(self.settings(), IC_CAMPUS_URL='http://school.example/campus/'))

    def test_missing_password_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'IC_PASSWORD'):
            self.load(dict(self.settings(), IC_PASSWORD="''"))
