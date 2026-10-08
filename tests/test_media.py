from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from mkchromecast.constants import OpMode
from mkchromecast.media import plan_media, youtube_commands
from mkchromecast.pipeline_builder import Video, VideoSettings


def settings(**changes):
    values = dict(operation=OpMode.INPUT_FILE, input_file='movie.mp4', videoarg=True,
                  subtitles=None, resolution=None, seek=None, loop=False, codec='mp3', mtype=None)
    return SimpleNamespace(**(values | changes))


class MediaTests(unittest.TestCase):
    def test_probe_stream_type_not_first_stream_or_extension(self):
        audio = dict(codec_type='audio', codec_name='aac')
        video = dict(codec_type='video', codec_name='h264', pix_fmt='yuv420p', level=40, width=1280, height=720)
        with patch('mkchromecast.utils.probe_media', return_value={'streams': [audio, video]}):
            plan = plan_media(settings())
            self.assertEqual('BUFFERED', plan.stream_type)
            self.assertIsNotNone(plan.direct_file)
            self.assertIsNone(plan_media(settings(subtitles='sub.srt')).direct_file)
            video['codec_name'] = 'vp9'
            plan = plan_media(settings())
            self.assertFalse(plan.copy_video)
            self.assertIsNone(plan.direct_file)

    def test_hdr_rejected_with_explanation(self):
        with patch('mkchromecast.utils.probe_media', return_value={'streams': [dict(codec_type='video', color_transfer='smpte2084')]}):
            with self.assertRaisesRegex(ValueError, 'HDR'):
                plan_media(settings())

    def test_youtube_normalizes_declared_format(self):
        for videoarg, codec in ((True, 'aac'), (False, 'libmp3lame')):
            conf = settings(operation=OpMode.YOUTUBE, videoarg=videoarg)
            conf.youtube_url, conf.bitrate, conf.samplerate = 'https://youtu.be/abc', 192, 44100
            producer, encoder = youtube_commands(conf)
            self.assertEqual(['--', conf.youtube_url], producer[-2:])
            self.assertIn(codec, encoder)
            self.assertEqual('video/mp4' if videoarg else 'audio/mpeg', plan_media(conf).media_type)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/ffprobe integration dependency missing')
class FFmpegTests(unittest.TestCase):
    def test_real_mp4_probe_and_subtitle_filter_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'movie.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=160x90:rate=5',
                            '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '0.6', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True, timeout=20)
            self.assertEqual(str(source), plan_media(settings(input_file=str(source))).direct_file)
            subtitle = Path(directory) / "a'b:[c],;.srt"
            subtitle.write_text('1\n00:00:00,000 --> 00:00:00,500\nHello\n')
            config = VideoSettings(display=':0', fps='5', input_file=str(source), loop=False,
                                   operation=OpMode.INPUT_FILE, resolution='480p', screencast=False,
                                   seek=None, subtitles=str(subtitle), user_command=None, vcodec='libx264', youtube_url=None)
            result = subprocess.run(Video(config).command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr.decode())
            output = Path(directory) / 'output.mp4'
            output.write_bytes(result.stdout)
            from mkchromecast.utils import probe_media
            streams = probe_media(str(output))['streams']
            self.assertEqual(['h264', 'aac'], [s['codec_name'] for s in streams])
            self.assertEqual(854, streams[0]['width'])
