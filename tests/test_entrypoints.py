import io
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from mkchromecast import Mkchromecast, _arg_parsing
from mkchromecast.constants import OpMode
from mkchromecast.stream_infra import FlaskServer


class AudioSetupTests(unittest.TestCase):
    def tearDown(self):
        FlaskServer.close()
        FlaskServer._app = None

    def test_raw_sample_rate_agrees_between_capture_and_encoder(self):
        from mkchromecast.audio import _flask_init
        with patch('platform.system', return_value='Linux'):
            conf = Mkchromecast(_arg_parsing.Parser.parse_args(['-c', 'mp3', '--sample-rate', '22050']))
        conf.capture_device = 'owned.monitor'
        _flask_init(conf)
        self.assertIn('--rate=22050', FlaskServer._producer)
        self.assertIn('owned.monitor', FlaskServer._producer)
        self.assertIn('22.05', FlaskServer._command)
        self.assertEqual('audio/mpeg', FlaskServer._media_type)

    def test_youtube_audio_does_not_capture_desktop(self):
        from mkchromecast.audio import _flask_init
        conf = Mkchromecast(_arg_parsing.Parser.parse_args(['-y', 'https://youtu.be/abc', '-c', 'opus']))
        _flask_init(conf)
        self.assertEqual('yt-dlp', FlaskServer._producer[0])
        self.assertEqual('ffmpeg', FlaskServer._command[0])
        self.assertIn('libmp3lame', FlaskServer._command)
        self.assertEqual('audio/mpeg', FlaskServer._media_type)


class CLITests(unittest.TestCase):
    def test_version_never_constructs_session(self):
        from mkchromecast.cli import main
        with patch('mkchromecast.session.CastSession') as session, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(0, main(['--version']))
            session.assert_not_called()
            self.assertIn('mkchromecast', output.getvalue())

    def test_startup_failure_returns_nonzero_and_closes(self):
        from mkchromecast.cli import main
        session = Mock()
        session.start.side_effect = RuntimeError('fixture failure')
        with patch('mkchromecast.session.CastSession', return_value=session), patch('sys.stderr', new_callable=io.StringIO) as output:
            self.assertEqual(1, main([]))
            self.assertIn('fixture failure', output.getvalue())
            session.close.assert_called_once()

    def test_discovery_closes_on_error(self):
        from mkchromecast.cli import main
        receiver = Mock()
        receiver.initialize_cast.side_effect = RuntimeError('network fixture')
        with patch('mkchromecast.session.receiver_for', return_value=receiver), patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(1, main(['--discover']))
        receiver.close.assert_called_once()


class NodeTests(unittest.TestCase):
    def test_legacy_command_includes_user_bitrate_and_sample_rate(self):
        from mkchromecast.node import command_for
        conf = SimpleNamespace(bitrate=256, samplerate=48000, port=5000)
        with patch('mkchromecast.node.shutil.which', return_value='/usr/bin/node'), patch('mkchromecast.node.Path.is_file', return_value=True):
            command = command_for(conf)
        self.assertEqual('256', command[command.index('-b') + 1])
        self.assertEqual('48000', command[command.index('-s') + 1])

    def test_missing_legacy_addon_explains_ffmpeg_alternative(self):
        from mkchromecast.node import command_for
        with patch('mkchromecast.node.shutil.which', return_value=None), patch('mkchromecast.node.Path.is_file', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'encoder-backend ffmpeg'):
                command_for(SimpleNamespace())
