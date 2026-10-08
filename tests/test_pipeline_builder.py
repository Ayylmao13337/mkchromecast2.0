# this file is part of mkchromecast.

from typing import Any
import unittest
from unittest import mock

from mkchromecast import pipeline_builder
from mkchromecast import stream_infra
from mkchromecast import utils
from mkchromecast.constants import OpMode

class AudioBuilderTests(unittest.TestCase):

    def create_builder(self,
                       backend_name: str,
                       platform: str,
                       **special_encoder_kwargs):
        encoder_kwargs: dict[str, Any] = {
            "codec": "mp3",
            "adevice": None,
            "bitrate": "160",
            "frame_size": 32 * 128,
            "samplerate": "22050",
            "segment_time": None
        }

        encoder_kwargs |= special_encoder_kwargs
        backend = stream_infra.BackendInfo(backend_name, backend_name)
        settings = pipeline_builder.EncodeSettings(**encoder_kwargs)

        return pipeline_builder.Audio(backend, platform, settings)

    def testDarwinInputCommand(self):
        builder = self.create_builder("ffmpeg", "Darwin")

        input_cmd = builder._input_command()
        self.assertIn("avfoundation", input_cmd)
        self.assertIn(":BlackHole 16ch", input_cmd)
        self.assertNotIn("alsa", input_cmd)
        self.assertNotIn("pulse", input_cmd)
        self.assertNotIn("-frame_size", input_cmd)

    def testLinuxPulseInputCommand(self):
        builder = self.create_builder("ffmpeg", "Linux", adevice=None)

        input_cmd = builder._input_command()
        self.assertIn("pulse", input_cmd)
        self.assertIn("Mkchromecast.monitor", input_cmd)
        self.assertNotIn("avfoundation", input_cmd)
        self.assertNotIn("alsa", input_cmd)
        self.assertNotIn("-frame_size", input_cmd)

    def testLinuxAlsaInputCommand(self):
        adevice="hw:2,1"
        builder = self.create_builder("ffmpeg", "Linux", adevice=adevice)

        input_cmd = builder._input_command()
        self.assertIn("alsa", input_cmd)
        self.assertIn(adevice, input_cmd)
        self.assertNotIn("avfoundation", input_cmd)
        self.assertNotIn("pulse", input_cmd)
        self.assertNotIn("-frame_size", input_cmd)

    def testDebugSpecialCase(self):
        self.assertIn(
            "-loglevel",
            self.create_builder("ffmpeg", "Darwin", ffmpeg_debug=True).command)
        self.assertIn(
            "warning",
            self.create_builder("ffmpeg", "Darwin", ffmpeg_debug=False).command)

    def testBitrateSpecialCase(self):
        # wav doesn't emit bitrate.
        self.assertIn(
            "-b:a",
            self.create_builder("ffmpeg", "Darwin", codec="mp3").command)
        self.assertNotIn(
            "-b:a",
            self.create_builder("ffmpeg", "Darwin", codec="wav").command)

        # ffmpeg should use "k" suffix.
        self.assertIn(
            "160k",
            self.create_builder("ffmpeg", "Linux", bitrate=160).command)
        self.assertNotIn(
            "160",
            self.create_builder("ffmpeg", "Linux", bitrate=160).command)

        # non-ffmpeg (parec in this case) should omit "k" suffix.
        self.assertIn(
            "160",
            self.create_builder("parec", "Linux", bitrate=160).command)
        self.assertNotIn(
            "160k",
            self.create_builder("parec", "Linux", bitrate=160).command)

    def testSegmentTimeSpecialCase(self):
        self.assertIn(
            "-segment_time",
            self.create_builder("ffmpeg", "Darwin", codec="mp3", segment_time=2).command)
        self.assertIn(
            "-segment_time",
            self.create_builder("ffmpeg", "Darwin", codec="aac", segment_time=2).command)
        self.assertIn(
            "-segment_time",
            self.create_builder("ffmpeg", "Linux", codec="ogg", segment_time=2).command)

        self.assertNotIn(
            "-segment_time",
            self.create_builder("ffmpeg", "Darwin", codec="ogg", segment_time=2).command)
        self.assertNotIn(
            "-segment_time",
            self.create_builder("ffmpeg", "Linux", codec="aac", segment_time=2).command)

    def testCutoffSpecialCase(self):
        # We should emit cutoff IFF codec == "aac" and segment_time is not None.
        self.assertIn(
            "-cutoff",
            self.create_builder("ffmpeg", "Darwin", codec="aac", segment_time=2).command)
        self.assertIn(
            "-cutoff",
            self.create_builder("ffmpeg", "Linux", codec="aac", segment_time=2).command)

        # Not aac -> no cutoff.
        self.assertNotIn(
            "-cutoff",
            self.create_builder("ffmpeg", "Darwin", codec="mp3", segment_time=2).command)
        self.assertNotIn(
            "-cutoff",
            self.create_builder("ffmpeg", "Linux", codec="mp3", segment_time=2).command)

        # Empty segment time -> no cutoff.
        self.assertNotIn(
            "-cutoff",
            self.create_builder("ffmpeg", "Darwin", codec="aac", segment_time=None).command)
        self.assertNotIn(
            "-cutoff",
            self.create_builder("ffmpeg", "Linux", codec="aac", segment_time=None).command)

    def testFullLinux(self):
        exp_command = [
            "ffmpeg", "-loglevel", "warning",
            "-ac", "2",
            "-ar", "44100",
            "-fragment_size", str(32*128),
            "-f", "pulse",
            "-i", "Mkchromecast.monitor",
            "-f", "mp3",
            "-acodec", "libmp3lame",
            "-ac", "2",
            "-ar", "22050",
            "-b:a", "160k",
            "pipe:",
        ]

        self.assertEqual(
            exp_command,
            self.create_builder("ffmpeg", "Linux").command)

    def testFullDarwin(self):
        exp_command = [
            "ffmpeg", "-loglevel", "warning",
            "-f", "avfoundation",
            "-i", ":BlackHole 16ch",
            "-f", "segment",
            "-segment_time", "2",
            "-f", "adts",
            "-acodec", "aac",
            "-ac", "2",
            "-ar", "22050",
            "-b:a", "160k",
            "-cutoff", "18000",
            "pipe:",
        ]

        self.assertEqual(
            exp_command,
            self.create_builder("ffmpeg", "Darwin", codec="aac", segment_time=2).command)

    # TODO(xsdg): Use pyparameterized for this.
    def testLinuxOther(self):
        binary_for_codecs: dict[str, str] = {
            "mp3": "lame",
            "ogg": "oggenc",
            "aac": "faac",
            "opus": "opusenc",
            "wav": "sox",
            "flac": "flac",
        }

        for codec, binary in binary_for_codecs.items():
            command = self.create_builder("parec", "Linux", codec=codec).command
            self.assertEqual(
                binary, command[0], f"Unexpected binary for codec {codec}")

        with self.assertRaisesRegex(Exception, "unexpected codec.*noexist"):
            _ = self.create_builder("parec", "Linux", codec="noexist").command


class VideoBuilderTests(unittest.TestCase):

    def create_builder(self,
                       **special_encoder_kwargs):
        encoder_kwargs: dict[str, Any] = {
            "display": ":0",
            "fps": "25",
            "input_file": "/path/to/file.mp4",
            "loop": False,
            "resolution": None,
            "screencast": False,
            "seek": None,
            "subtitles": None,
            "user_command": None,
            "vcodec": "libx264",
            "youtube_url": None,
        }

        encoder_kwargs |= special_encoder_kwargs
        settings = pipeline_builder.VideoSettings(**encoder_kwargs)

        return pipeline_builder.Video(settings)

    def test_subtitles_force_transcoding_and_combine_filters(self):
        command = self.create_builder(operation=OpMode.INPUT_FILE, copy_video=True,
                                      subtitles="captions.srt", resolution="480p").command
        self.assertNotIn("copy", command)
        self.assertIn("libx264", command)
        self.assertEqual(1, command.count("-vf"))
        self.assertIn("scale=854:-2", command[command.index("-vf") + 1])
        self.assertIn("0:v:0", command)
        self.assertIn("0:a:0?", command)
        self.assertIn("aac", command)

    def test_copy_requires_explicit_probe_decision(self):
        command = self.create_builder(operation=OpMode.INPUT_FILE).command
        self.assertNotIn("copy", command)
        command = self.create_builder(operation=OpMode.INPUT_FILE, copy_video=True,
                                      loop=True, seek="00:00:01").command
        self.assertIn("copy", command)
        self.assertIn("-stream_loop", command)
        self.assertLess(command.index("-ss"), command.index("-i"))

    def testX11ScreencastCommand(self):
        # The X11 path stays on ffmpeg/x11grab, byte-for-byte unchanged.
        exp_command = [
            "ffmpeg",
            "-ac", "2",
            "-ar", "44100",
            "-fragment_size", "2048",
            "-f", "pulse",
            "-ac", "2",
            "-i", "Mkchromecast.monitor",
            "-f", "x11grab",
            "-r", "25",
            "-s", "1920x1080",
            "-i", ":0+0,0",
            "-vcodec", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-maxrate", "10000k",
            "-bufsize", "20000k",
            "-pix_fmt", "yuv420p",
            "-g", "60",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov",
            "-ar", "44100",
            "-acodec", "aac",
            "pipe:1",
        ]
        builder = self.create_builder(operation=OpMode.SCREENCAST,
                                      screencast=True,
                                      display=":0",
                                      fps="25")
        self.assertEqual(exp_command, builder.command)

    def testWaylandScreencastCommand(self):
        # The Wayland path is a gst-launch pipeline, not ffmpeg.
        builder = self.create_builder(operation=OpMode.SCREENCAST,
                                      screencast=True,
                                      fps="25",
                                      wayland_capture=(7, 42))
        command = builder.command
        self.assertEqual("gst-launch-1.0", command[0])
        self.assertNotIn("ffmpeg", command)
        self.assertNotIn("x11grab", command)
        self.assertIn("pipewiresrc", command)
        self.assertIn("fd=7", command)
        self.assertIn("path=42", command)
        self.assertIn("mp4mux", command)
        self.assertIn("fdsink", command)
        # Audio still captured from the pulse monitor sink.
        self.assertIn("pulsesrc", command)
        self.assertIn("device=Mkchromecast.monitor", command)
        # Chromecast-compatible video: 4:2:0 (I420), scaled to 1080p, fps, and
        # High profile constrained on the encoder output.
        self.assertIn("videoscale", command)
        caps = next(a for a in command if a.startswith("video/x-raw"))
        self.assertIn("format=I420", caps)
        self.assertIn("width=1920", caps)
        self.assertIn("height=1080", caps)
        self.assertIn("framerate=25/1", caps)
        self.assertIn("video/x-h264,profile=high", command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
