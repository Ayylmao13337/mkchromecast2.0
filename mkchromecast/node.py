"""Legacy Node audio adapter. FFmpeg remains available without native Node addons."""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

from mkchromecast import Mkchromecast, utils


def command_for(settings):
    binary = shutil.which("node")
    candidates = [Path(__file__).resolve().parent.parent / "nodejs/node_modules/webcast-osx-audio/bin/webcast.js",
                  Path(sys.prefix) / "share/mkchromecast/nodejs/node_modules/webcast-osx-audio/bin/webcast.js"]
    script = next((p for p in candidates if p.is_file()), None)
    if not binary or script is None:
        raise RuntimeError("Node audio requires node and webcast-osx-audio. Install the legacy addon or use --encoder-backend ffmpeg")
    return [binary, str(script), "-b", str(utils.clamp_bitrate("mp3", settings.bitrate)),
            "-s", str(utils.quantize_sample_rate("mp3", settings.samplerate)),
            "-p", str(settings.port), "-u", "stream"]


class NodeProcess:
    def __init__(self, settings):
        self.settings = settings
        self.process = None

    def start(self, timeout=30, cancel=None):
        # Reject an occupied port before spawning; never adopt another server.
        with socket.socket() as probe:
            probe.bind((self.settings.host, self.settings.port))
        self.process = subprocess.Popen(command_for(self.settings), start_new_session=True)
        deadline = time.monotonic() + min(timeout, 30)
        try:
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    raise RuntimeError("Startup cancelled")
                self.check()
                try:
                    with socket.create_connection((self.settings.host, self.settings.port), timeout=.2):
                        return self
                except OSError:
                    time.sleep(.1)
            raise RuntimeError("Node audio server did not become ready")
        except BaseException:
            self.close()
            raise

    def check(self):
        if self.process is not None and self.process.poll() is not None:
            raise RuntimeError(f"Node audio exited with status {self.process.returncode}")

    def pause(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGSTOP)

    def resume(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGCONT)

    def close(self):
        if self.process is None:
            return
        process, self.process = self.process, None
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGCONT)
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)


def stream_audio(settings=None, cancel=None):
    settings = settings or Mkchromecast()
    return NodeProcess(settings).start(timeout=settings.startup_timeout, cancel=cancel)
