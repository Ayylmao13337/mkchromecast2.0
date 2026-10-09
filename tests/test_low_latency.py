import shutil
import unittest
from unittest.mock import patch

from mkchromecast import Mkchromecast, _arg_parsing, video
from mkchromecast.pipeline_builder import Video
from tools.benchmark_screencast import measure, settings_for
from tests.test_video import _make_stub_mkcc


class LowLatencyTests(unittest.TestCase):
    def test_profile_requires_screencast(self):
        with patch('platform.system', return_value='Linux'):
            with self.assertRaisesRegex(ValueError, 'requires --video --screencast'):
                Mkchromecast(_arg_parsing.Parser.parse_args(['--low-latency']))
            settings = Mkchromecast(_arg_parsing.Parser.parse_args(
                ['--video', '--screencast', '--low-latency']))
        self.assertTrue(settings.low_latency)

    def test_setting_reaches_video_builder(self):
        stub = _make_stub_mkcc()
        stub.low_latency = True
        self.assertTrue(video._build_video_settings(stub, None).low_latency)

    def test_gop_scales_with_fps_without_zero(self):
        for fps, expected in [('1', '1'), ('25', '13'), ('29.97', '15'), ('60', '30')]:
            settings = settings_for(True, fps)
            ffmpeg = Video(settings).command
            self.assertEqual(ffmpeg[ffmpeg.index('-g') + 1], expected)
            settings.wayland_capture = (7, 42)
            self.assertIn('key-int-max=' + expected, Video(settings).command)

    def test_compressed_frames_are_never_dropped(self):
        settings = settings_for(True)
        settings.cinnamon_capture = '/private/frames'
        command = Video(settings).command
        encoder = command.index('x264enc')
        self.assertIn('leaky=downstream', command[:encoder])
        self.assertNotIn('leaky=downstream', command[encoder:])
        self.assertIn('fragment-duration=250', command)

    def test_default_profile_keeps_existing_output(self):
        settings = settings_for()
        command = Video(settings).command
        self.assertEqual(command[command.index('-g') + 1], '60')
        self.assertNotIn('-frag_duration', command)
        settings.cinnamon_capture = '/private/frames'
        command = Video(settings).command
        self.assertIn('fragment-duration=1000', command)
        self.assertIn('key-int-max=50', command)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_low_latency_output_is_decodable_and_fragmented(self):
        # Check the real encoder/mux output, not just option strings. Do not use
        # tight wall-clock assertions on shared CI runners.
        result = measure(settings_for(True, size='480p'), seconds=2)
        self.assertEqual({s['codec_name'] for s in result['streams']}, {'h264', 'aac'})
        self.assertGreaterEqual(len(result['complete_media_fragments_s']), 7)
        h264 = next(s for s in result['streams'] if s['codec_name'] == 'h264')
        self.assertEqual(h264['has_b_frames'], 0)
