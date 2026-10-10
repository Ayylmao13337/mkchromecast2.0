import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from mkchromecast.session import CastSession
from mkchromecast.constants import OpMode


def settings(operation=OpMode.AUDIOCAST):
    return SimpleNamespace(operation=operation, receiver='chromecast', platform='Linux',
                           adevice=None, codec='mp3', backend='ffmpeg', videoarg=False,
                           host='127.0.0.1', port=5000, hijack=False, mtype=None)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.receiver = Mock()
        self.enterContext(patch('mkchromecast.session.receiver_for', return_value=self.receiver))
        self.pipeline = Mock()
        self.start = self.enterContext(patch('mkchromecast.audio.main', return_value=self.pipeline))
        self.sink = Mock(monitor='session.monitor')
        self.enterContext(patch('mkchromecast.pulseaudio.AudioSink', return_value=Mock(start=Mock(return_value=self.sink))))

    def test_ready_before_play_and_idempotent_close(self):
        events = []
        self.start.side_effect = lambda *a, **kw: events.append('ready') or self.pipeline
        self.receiver.play_cast.side_effect = lambda: events.append('play')
        session = CastSession(settings()).start()
        self.assertEqual(['ready', 'play'], events)
        self.assertEqual('session.monitor', session.settings.capture_device)
        session.close()
        session.close()
        self.pipeline.close.assert_called_once()
        self.receiver.close.assert_called_once()
        self.sink.close.assert_called_once()

    def test_failed_start_cleans_routing_and_does_not_play(self):
        self.start.side_effect = RuntimeError('occupied port')
        session = CastSession(settings())
        with self.assertRaisesRegex(RuntimeError, 'occupied port'):
            session.start()
        self.assertEqual('failed', session.state)
        self.receiver.play_cast.assert_not_called()
        self.receiver.close.assert_called_once()
        self.sink.close.assert_called_once()

    def test_all_cleanup_attempted_when_one_fails(self):
        session = CastSession(settings()).start()
        self.pipeline.close.side_effect = RuntimeError('fixture')
        session.close()
        self.receiver.close.assert_called_once()
        self.sink.close.assert_called_once()

    def test_source_url_never_starts_capture(self):
        conf = settings(OpMode.SOURCE_URL)
        conf.source_url = 'https://example.com/audio.mp3'
        session = CastSession(conf).start()
        self.start.assert_not_called()
        self.assertIsNone(session.sink)
        session.close()

    def test_pause_does_not_trigger_hijack_retry(self):
        session = CastSession(settings()).start()
        session.settings.hijack = True
        session.pause()
        self.receiver.play_cast.reset_mock()
        session.check()
        self.receiver.play_cast.assert_not_called()
        session.close()

    def test_explicit_source_does_not_change_audio_routing(self):
        conf = settings()
        conf.audio_source = 'speakers.monitor'
        with patch('mkchromecast.pulseaudio.list_sources', return_value=[{'name': conf.audio_source}]):
            session = CastSession(conf).start()
        self.assertEqual('speakers.monitor', conf.capture_device)
        self.assertIsNone(session.sink)
        session.close()
        self.sink.close.assert_not_called()

    def test_missing_source_fails_without_fallback_or_playback(self):
        conf = settings()
        conf.audio_source = 'unplugged'
        with patch('mkchromecast.pulseaudio.list_sources', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'no longer available'):
                CastSession(conf).start()
        self.start.assert_not_called()
        self.receiver.play_cast.assert_not_called()
        self.receiver.close.assert_called_once()
