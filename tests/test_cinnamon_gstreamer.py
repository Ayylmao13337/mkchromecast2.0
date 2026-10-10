"""Real SHM transport, reconnect, H.264/AAC mux and decode; no Cinnamon/GPU.

Required in the dedicated Linux CI job. Other environments may skip it.
"""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time
import unittest

from mkchromecast.pipeline_builder import Video, VideoSettings
from mkchromecast.constants import OpMode


class CinnamonGStreamerTests(unittest.TestCase):
    def test_private_frames_reconnect_and_decode(self):
        self._check_transport(False)

    def test_low_latency_frames_reconnect_and_decode(self):
        self._check_transport(True)

    def _check_transport(self, low_latency):
        programs = ('gst-launch-1.0', 'gst-inspect-1.0', 'ffprobe', 'ffmpeg')
        missing = [p for p in programs if not shutil.which(p)]
        if missing:
            if os.environ.get('MKCHROMECAST_REQUIRE_GSTREAMER'):
                self.fail('Missing required integration dependencies: ' + ', '.join(missing))
            self.skipTest('GStreamer integration dependencies are not installed')
        with tempfile.TemporaryDirectory() as directory:
            socket_path = str(Path(directory) / 'frames')
            caps = 'video/x-raw,format=I420,width=854,height=480,framerate=25/1,pixel-aspect-ratio=1/1'
            source_log = tempfile.TemporaryFile()
            writer = subprocess.Popen([
                'gst-launch-1.0', '-q', 'videotestsrc', 'is-live=true', '!', caps, '!',
                'shmsink', 'socket-path=' + socket_path, 'shm-size=33554432',
                'perms=384', 'wait-for-connection=false', 'sync=false',
            ], stdout=subprocess.DEVNULL, stderr=source_log)
            try:
                deadline = time.monotonic() + 10
                while not Path(socket_path).exists():
                    self.assertIsNone(writer.poll(), 'GStreamer SHM writer failed')
                    self.assertLess(time.monotonic(), deadline, 'No SHM socket')
                    time.sleep(.05)
                settings = VideoSettings(None, '25', None, False, OpMode.SCREENCAST,
                                         '480p', True, None, None, None, 'libx264', None,
                                         cinnamon_capture=socket_path, low_latency=low_latency)
                command = Video(settings).command
                # Use a clocked synthetic audio source instead of a real sound server.
                audio = command.index('pulsesrc')
                command[audio:audio + 2] = ['audiotestsrc', 'is-live=true']
                # Each HTTP reconnect starts a new reader of the same live recorder.
                for attempt in range(2):
                    output = Path(directory) / f'capture-{attempt}.mp4'
                    with tempfile.TemporaryFile() as errors:
                        reader = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
                        data = bytearray()
                        deadline = time.monotonic() + 15
                        try:
                            while time.monotonic() < deadline and data.count(b'moof') < 3:
                                if select.select([reader.stdout], [], [], .2)[0]:
                                    block = os.read(reader.stdout.fileno(), 65536)
                                    if not block:
                                        break
                                    data.extend(block)
                            # End only after multiple complete fragment boundaries.
                            self.assertGreaterEqual(data.count(b'moof'), 3)
                        finally:
                            reader.terminate()
                            try:
                                reader.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                reader.kill()
                                reader.wait(timeout=5)
                            reader.stdout.close()
                        # Remove the possibly incomplete final fragment (including
                        # its size field), leaving the previous fragments intact.
                        output.write_bytes(data[:data.rfind(b'moof') - 4])
                    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams',
                                            '-of', 'json', str(output)],
                                           capture_output=True, text=True, timeout=10, check=True)
                    streams = json.loads(probe.stdout)['streams']
                    self.assertEqual({s['codec_name'] for s in streams}, {'h264', 'aac'})
                    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(output),
                                              '-t', '0.2', '-f', 'null', '-'],
                                             capture_output=True, text=True, timeout=10)
                    self.assertEqual(decoded.returncode, 0, decoded.stderr)
                    self.assertIsNone(writer.poll())
            finally:
                writer.terminate()
                try:
                    writer.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    writer.kill()
                    writer.wait(timeout=5)
                source_log.close()
