import unittest
from unittest.mock import Mock, patch
from mkchromecast.audio_devices import AudioRouter
from mkchromecast.pulseaudio import AudioSink


class RoutingTests(unittest.TestCase):
    def test_linux_unloads_only_created_module(self):
        with patch('mkchromecast.pulseaudio.subprocess.run', return_value=Mock(stdout='42\n')) as run:
            sink = AudioSink().start()
            sink.close()
            sink.close()
        self.assertEqual(2, run.call_count)
        self.assertEqual(['pactl', 'unload-module', '42'], run.call_args.args[0])

    def test_macos_restores_actual_devices_after_partial_failure(self):
        with patch('mkchromecast.audio_devices.shutil.which', return_value='/bin/SwitchAudioSource'):
            router = AudioRouter()
        with patch.object(router, '_get', side_effect=['Microphone', 'Speakers']), patch.object(router, '_set', side_effect=[None, RuntimeError('failure'), None, None]) as set_device:
            with self.assertRaisesRegex(RuntimeError, 'failure'):
                router.start()
            self.assertEqual([('input', 'Microphone'), ('output', 'Speakers')], [c.args for c in set_device.call_args_list[-2:]])
            count = set_device.call_count
            router.close()
            self.assertEqual(count, set_device.call_count)
