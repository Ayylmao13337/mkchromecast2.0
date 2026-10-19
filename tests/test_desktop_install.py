import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mkchromecast import desktop_install, gui_settings


class DesktopInstallTests(unittest.TestCase):
    def test_launcher_uses_this_environment_and_user_directory(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'XDG_DATA_HOME': root}), patch(
                'sys.executable', '/home/user/My Programs/venv/bin/python'), patch('sys.platform', 'linux'):
            path = desktop_install.install()
            self.assertEqual(Path(root) / 'applications/mkchromecast.desktop', path)
            self.assertIn('Exec="/home/user/My Programs/venv/bin/python" -m mkchromecast.cli --tray', path.read_text())

    def test_exec_path_cannot_inject_another_entry(self):
        with self.assertRaises(ValueError):
            desktop_install.quote_exec('/tmp/python\nExec=bad')
        self.assertIn('%%', desktop_install.quote_exec('/tmp/100%/python'))

    def test_corrupt_preferences_do_not_prevent_launch(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'XDG_CONFIG_HOME': root}):
            gui_settings.save('Linux', {'fps': 25})
            self.assertEqual(25, gui_settings.load('Linux')['fps'])
            (Path(root) / 'mkchromecast/desktop.json').write_text('{broken')
            self.assertEqual({}, gui_settings.load('Linux'))
