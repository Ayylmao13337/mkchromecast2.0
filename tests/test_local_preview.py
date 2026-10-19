import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from mkchromecast import Mkchromecast, _arg_parsing
from mkchromecast.local_preview import LocalPreviewSession


class LocalPreviewTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('mkchromecast.local_preview.shutil.which', return_value='/bin/ffplay'))
        self.sink = Mock(monitor='private.monitor')
        self.enterContext(patch('mkchromecast.pulseaudio.AudioSink', return_value=Mock(start=Mock(return_value=self.sink))))
        self.pipeline = Mock(port=12345)
        self.start = self.enterContext(patch('mkchromecast.video.main', return_value=self.pipeline))
        self.player = Mock()
        self.player.output.poll.return_value = None
        self.spawn = self.enterContext(patch('mkchromecast.local_preview.OwnedPipeline', return_value=self.player))
        self.settings = SimpleNamespace(host='10.0.0.51', port=5000)

    def test_loopback_ephemeral_port_and_production_capture(self):
        with patch('mkchromecast.session.receiver_for') as receiver:
            session = LocalPreviewSession(self.settings).start()
            receiver.assert_not_called()
        used = self.start.call_args.args[0]
        self.assertEqual(('127.0.0.1', 0, 'private.monitor'), (used.host, used.port, used.capture_device))
        self.assertEqual('10.0.0.51', self.settings.host)
        command = self.spawn.call_args.args[0]
        self.assertEqual('http://127.0.0.1:12345/stream', command[-1])
        session.check()
        self.assertFalse(session.finished)
        self.player.output.poll.return_value = 0
        session.check()
        self.assertTrue(session.finished)
        session.close()
        session.close()
        for resource in (self.sink, self.pipeline, self.player):
            resource.close.assert_called_once()

    def test_player_start_failure_closes_capture_and_sink(self):
        self.spawn.side_effect = RuntimeError('player failed')
        with self.assertRaisesRegex(RuntimeError, 'player failed'):
            LocalPreviewSession(self.settings).start()
        self.pipeline.close.assert_called_once()
        self.sink.close.assert_called_once()

    def test_missing_player_does_not_start_capture(self):
        with patch('mkchromecast.local_preview.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'ffplay'):
                LocalPreviewSession(self.settings).start()
        self.start.assert_not_called()

    def test_cli_rejects_unrelated_modes(self):
        with patch('platform.system', return_value='Linux'):
            with self.assertRaisesRegex(ValueError, 'requires Cinnamon'):
                Mkchromecast(_arg_parsing.Parser.parse_args(['--local-preview']))
            settings = Mkchromecast(_arg_parsing.Parser.parse_args([
                '--local-preview', '--video', '--screencast', '--capture-backend', 'cinnamon']))
            self.assertTrue(settings.local_preview)
