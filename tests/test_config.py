"""Exercise persisted configuration, including interrupted writes and migration."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mkchromecast.config import Config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(self.tmp) / 'new' / 'mkchromecast.cfg'

    def test_defaults_create_directory_and_roundtrip(self):
        with Config('Linux', self.path) as conf:
            self.assertEqual('parec', conf.backend)
            conf.bitrate = 256
            conf.notifications = True
            conf.alsa_device = None
        with Config('Linux', self.path, read_only=True) as conf:
            self.assertEqual(256, conf.bitrate)
            self.assertTrue(conf.notifications)
            self.assertIsNone(conf.alsa_device)

    def test_readonly_does_not_create_files(self):
        with Config('Darwin', self.path, read_only=True) as conf:
            self.assertEqual('node', conf.backend)
        self.assertFalse(self.path.parent.exists())

    def test_failed_context_does_not_overwrite(self):
        with Config('Linux', self.path):
            pass
        before = self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            with Config('Linux', self.path) as conf:
                conf.bitrate = 128
                raise RuntimeError('abort')
        self.assertEqual(before, self.path.read_bytes())

    def test_failed_replace_preserves_original_and_removes_temporary(self):
        with Config('Linux', self.path):
            pass
        before = self.path.read_bytes()
        with patch('mkchromecast.config.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                with Config('Linux', self.path) as conf:
                    conf.bitrate = 128
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([self.path], list(self.path.parent.iterdir()))

    def test_migrates_legacy_without_deleting_it(self):
        self.path.parent.mkdir()
        legacy = self.path.with_name('mkchromecast_beta.cfg')
        legacy.write_text('[settings]\nbitrate = 256\n')
        with Config('Linux', self.path) as conf:
            self.assertEqual(256, conf.bitrate)
        self.assertTrue(self.path.exists())
        self.assertTrue(legacy.exists())

    def test_invalid_configuration_is_not_silently_overwritten(self):
        self.path.parent.mkdir()
        for text in ('[settings]\nbackend = obsolete\n', '[settings]\nbitrate = nope\n',
                     '[settings]\nnotifications = perhaps\n'):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    with Config('Linux', self.path):
                        pass
                self.assertEqual(text, self.path.read_text())

    def test_reset_writes_valid_defaults(self):
        conf = Config('Linux', self.path)
        conf.write_defaults()
        conf.load_and_validate()
        self.assertEqual(192, conf.bitrate)
