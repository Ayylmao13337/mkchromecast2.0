"""Measure FFmpeg output cadence, NOT display latency. Run from the checkout:

python -m tools.benchmark_screencast --seconds 8 --resolution 720p
Only synthetic audio/video is used; no desktop capture or receiver connection.
"""
import argparse
from dataclasses import replace
import json
import os
import select
import statistics
import struct
import subprocess
import tempfile
import time

from mkchromecast.constants import OpMode
from mkchromecast.pipeline_builder import Video, VideoSettings
from mkchromecast.resolution import resolution


def settings_for(low_latency=False, fps="25", size="720p"):
    return VideoSettings(":0", fps, None, False, OpMode.SCREENCAST, size,
                         True, None, None, None, "libx264", None,
                         low_latency=low_latency)


def fixture_command(settings, seconds):
    """Replace capture inputs only, keeping the actual production encoder/mux."""
    command = Video(settings).command
    encoding = command[command.index("-vcodec"):]
    return [
        "ffmpeg", "-nostdin", "-v", "error",
        "-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-re", "-f", "lavfi", "-i",
        f"testsrc2=size={resolution(settings.resolution, True)}:rate={settings.fps}",
        "-t", str(seconds), *encoding,
    ]


def measure(settings, seconds=8):
    """Return complete-media-box timings and decoded stream metadata."""
    command = fixture_command(settings, seconds)
    pending = bytearray()
    data = bytearray()
    times = []
    with tempfile.TemporaryFile() as errors:
        started = time.monotonic()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        deadline = started + seconds + 30
        try:
            while True:
                if time.monotonic() > deadline:
                    raise RuntimeError("Synthetic capture benchmark timed out")
                if not select.select([process.stdout], [], [], .2)[0]:
                    continue
                block = os.read(process.stdout.fileno(), 65536)
                if not block:
                    break
                data.extend(block)
                pending.extend(block)
                if len(data) > 128 * 1024 * 1024:
                    raise RuntimeError("Benchmark output exceeded 128 MiB")
                while len(pending) >= 8:
                    length, kind = struct.unpack(">I4s", pending[:8])
                    header = 8
                    if length == 1:
                        if len(pending) < 16:
                            break
                        length = struct.unpack(">Q", pending[8:16])[0]
                        header = 16
                    if length < header:
                        raise RuntimeError("Invalid MP4 box in benchmark output")
                    if len(pending) < length:
                        break
                    if kind == b"mdat":
                        times.append(time.monotonic() - started)
                    del pending[:length]
            code = process.wait(timeout=5)
            if code:
                errors.seek(0)
                raise RuntimeError(errors.read(8192).decode(errors="replace"))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            process.stdout.close()
    with tempfile.NamedTemporaryFile(suffix=".mp4") as output:
        output.write(data)
        output.flush()
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_name,has_b_frames",
            "-of", "json", output.name,
        ], capture_output=True, text=True, check=True, timeout=15)
        decoded = subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", output.name,
            "-f", "null", "-",
        ], capture_output=True, text=True, timeout=30)
        if decoded.returncode:
            raise RuntimeError(decoded.stderr)
    # Exclude the possibly short final fragment. Startup cadence is not screen
    # latency: FFmpeg read-rate initial bursts can emit the first frames early.
    intervals = [b - a for a, b in zip(times[:-2], times[1:-1])]
    return {
        "profile": "low-latency" if settings.low_latency else "default",
        "resolution": settings.resolution, "fps": settings.fps,
        "seconds": seconds, "bytes": len(data),
        "complete_media_fragments_s": [round(t, 3) for t in times],
        "median_fragment_interval_s": round(statistics.median(intervals), 3) if intervals else None,
        "decode": "passed", "streams": json.loads(probe.stdout)["streams"],
        "scope": "Synthetic encoder/mux output only; excludes capture, network and receiver",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, choices=range(6, 31), default=8)
    parser.add_argument("--fps", type=int, choices=range(10, 61), default=25)
    parser.add_argument("--resolution", choices=("480p", "720p", "1080p"), default="720p")
    args = parser.parse_args()
    settings = settings_for(fps=str(args.fps), size=args.resolution)
    for low in (False, True):
        print(json.dumps(measure(replace(settings, low_latency=low), args.seconds)), flush=True)


if __name__ == "__main__":
    main()
