import unittest
from unittest.mock import Mock, patch
from mkchromecast.audio_devices import AudioRouter
from mkchromecast.pulseaudio import AudioSink


class RoutingTests(unittest.TestCase):
    def test_linux_unloads_only_created_module(self):
        with patch('mkchromecast.pulseaudio._list_audio', return_value=[]), patch('mkchromecast.pulseaudio.subprocess.run', return_value=Mock(stdout='42\n')) as run:
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

    def test_restore_only_preexisting_inputs_still_on_our_sink(self):
        sink = AudioSink()
        inventories = [
            [{'index': 1, 'name': 'speakers'}, {'index': 2, 'name': 'headphones'}],
            [{'index': 10, 'sink': 1}, {'index': 11, 'sink': 2}],
            [{'index': 1, 'name': 'speakers'}, {'index': 2, 'name': 'headphones'},
             {'index': 3, 'name': sink.name}],
            [{'index': 10, 'sink': 3}, {'index': 11, 'sink': 1}, {'index': 12, 'sink': 3}],
        ]
        with patch('mkchromecast.pulseaudio._list_audio', side_effect=inventories), patch(
                'mkchromecast.pulseaudio.subprocess.run', return_value=Mock(stdout='42')) as run:
            sink.start()
            sink.close()
        moves = [call.args[0] for call in run.call_args_list if 'move-sink-input' in call.args[0]]
        self.assertEqual([['pactl', 'move-sink-input', '10', 'speakers']], moves)
        self.assertEqual(['pactl', 'unload-module', '42'], run.call_args.args[0])

    def test_cleanup_still_unloads_sink_if_inventory_fails(self):
        sink = AudioSink()
        sink.module = '42'
        with patch('mkchromecast.pulseaudio._list_audio', side_effect=ValueError('bad list')), patch(
                'mkchromecast.pulseaudio.subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Audio routing cleanup'):
                sink.close()
            run.assert_called_once()
            self.assertEqual(['pactl', 'unload-module', '42'], run.call_args.args[0])
