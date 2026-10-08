import tempfile
import unittest
from unittest.mock import patch
from mkchromecast import Mkchromecast, _arg_parsing
from mkchromecast.constants import OpMode


class SettingsTests(unittest.TestCase):
    def make(self, *argv):
        with patch('platform.system', return_value='Linux'):
            return Mkchromecast(_arg_parsing.Parser.parse_args(argv))

    def test_defaults(self):
        settings = self.make()
        self.assertEqual(OpMode.AUDIOCAST, settings.operation)
        self.assertEqual('parec', settings.backend)
        self.assertEqual(5000, settings.port)

    def test_node_requires_mp3(self):
        with patch('platform.system', return_value='Darwin'):
            settings = Mkchromecast(_arg_parsing.Parser.parse_args(['--encoder-backend', 'node', '-c', 'opus']))
        self.assertEqual('mp3', settings.codec)

    def test_tray_reads_real_configuration(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'XDG_CONFIG_HOME': directory}):
            from mkchromecast.config import Config
            with Config('Linux') as conf:
                conf.backend = 'ffmpeg'
                conf.bitrate = 256
            settings = self.make('--tray')
            self.assertEqual(256, settings.bitrate)
            self.assertEqual('ffmpeg', settings.backend)

    def test_invalid_parameters(self):
        for argv in (['--port', '0'], ['--fps', 'nan'], ['--discovery-timeout', 'inf'],
                     ['--startup-timeout', '-1'], ['--screencast'], ['--segment-time', '2'],
                     ['--source-url', 'not-a-url'], ['--receiver', 'sonos', '--video'],
                     ['--video'], ['--tries', '0'], ['--mtype', 'audio/aac']):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                self.make(*argv)

    def test_ytdlp_accepts_short_url(self):
        settings = self.make('-y', 'https://youtu.be/abc')
        self.assertEqual(OpMode.YOUTUBE, settings.operation)
        self.assertEqual('ffmpeg', settings.backend)

    def test_custom_command_preserves_quoted_arguments(self):
        settings = self.make('--video', '--command', 'ffmpeg -i "my movie.mp4" -f mp4 pipe:1')
        self.assertIn('my movie.mp4', settings.command)
        self.assertEqual(OpMode.INPUT_FILE, settings.operation)
        with self.assertRaises(ValueError):
            self.make('--video', '--command', 'echo unsafe')

    def test_resolution_normalized(self):
        self.assertEqual('720p', self.make('--resolution', '720P').resolution)
