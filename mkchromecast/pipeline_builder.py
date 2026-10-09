# This file is part of mkchromecast.

from dataclasses import dataclass
import os
from typing import Optional, Union
from fractions import Fraction
import math

import mkchromecast
from mkchromecast import colors
from mkchromecast import constants
from mkchromecast import resolution
from mkchromecast import stream_infra
from mkchromecast import utils
from mkchromecast.constants import OpMode

SubprocessCommand = Union[list[str], str, os.PathLike]

@dataclass
class EncodeSettings:
    codec: str
    adevice: Optional[str]
    bitrate: int
    frame_size: int
    samplerate: str
    segment_time: Optional[int]
    ffmpeg_debug: bool = False


class Audio:

    _ffmpeg_fmt_to_acodec: dict[str, str] = {
        "mp3": "libmp3lame",
        "ogg": "libvorbis",
        "adts": "aac",
        "opus": "libopus",
        "wav": "pcm_s24le",
        "flac": "flac",
    }

    def __init__(self,
                 backend: stream_infra.BackendInfo,
                 platform: str,
                 encode_settings: EncodeSettings):
        self._backend = backend
        self._platform = platform
        self._settings = encode_settings

    # TODO(xsdg): Use SubprocessCommand here.
    @property
    def command(self) -> list[str]:
        if self._platform == "Darwin":
            return self._build_ffmpeg_command()
        else:  # platform == "Linux"
            if self._backend.name == "ffmpeg":
                return self._build_ffmpeg_command()

            elif self._backend.name == "parec":
                return self._build_linux_other_command()

            else:
                raise Exception(f"Unsupported backend: {self._backend.name}")

    def _input_command(self) -> list[str]:
        """Returns an appropriate set of input arguments for the pipeline.

        Considers the platform and (on Linux) whether we're configured to use
        pulse or alsa.
        """
        if self._platform == "Darwin":
            return ["-f", "avfoundation", "-i", ":BlackHole 16ch"]
        else:  # platform == "Linux"
            # NOTE(xsdg): Warning on console:
            # [Pulse indev @ 0x564d070e7440] The "frame_size" option is deprecated: set number of bytes per frame
            cmd: list[str] = [
                "-ac", "2",
                "-ar", "44100",
            ]

            if self._settings.adevice:
                cmd.extend(["-f", "alsa", "-i", self._settings.adevice])
            else:
                cmd.extend(["-fragment_size", str(self._settings.frame_size),
                            "-f", "pulse", "-i", "Mkchromecast.monitor"])

            return cmd

    def _build_ffmpeg_command(self) -> list[str]:
        fmt = self._settings.codec
        # Special case: the ffmpeg format for AAC is ADTS
        if self._settings.codec == "aac":
            fmt = "adts"

        # Runs ffmpeg with debug logging enabled.
        maybe_debug_cmd: list[str] = (
            ["-loglevel", "warning"] if not self._settings.ffmpeg_debug else ["-loglevel", "info"]
        )

        maybe_bitrate_cmd: list[str]
        if self._settings.codec in constants.CODECS_WITH_BITRATE:
            maybe_bitrate_cmd = ["-b:a", f"{self._settings.bitrate}k"]
        else:
            maybe_bitrate_cmd = []

        # TODO(xsdg): It's really weird that the legacy code excludes
        # specifically Darwin/ogg and Linux/aac.  Do some more testing to
        # determine if this was just a copy-paste error or if there's an
        # underlying motivation for which of these don't use segment_time.
        maybe_segment_cmd: list[str]
        if self._settings.segment_time and (
            (self._platform == "Darwin" and fmt != "ogg") or
            (self._platform == "Linux" and fmt != "adts")):
            maybe_segment_cmd = [
                "-f", "segment",
                "-segment_time", str(self._settings.segment_time)
            ]
        else:
            maybe_segment_cmd = []

        # TODO(xsdg): Figure out and document why -segment_time and -cutoff are
        # clustered specifically for aac.
        maybe_cutoff_cmd: list[str]
        if fmt == "adts" and self._settings.segment_time:
            maybe_cutoff_cmd = ["-cutoff", "18000"]
        else:  # fmt != "adts" or bool(segment_time) == False
            maybe_cutoff_cmd = []

        return [self._backend.path,
                *maybe_debug_cmd,
                *self._input_command(),
                *maybe_segment_cmd,
                "-f", fmt,
                "-acodec", self._ffmpeg_fmt_to_acodec[fmt],
                "-ac", "2",
                "-ar", self._settings.samplerate,
                *maybe_bitrate_cmd,
                *maybe_cutoff_cmd,
                "pipe:",
        ]

    def _build_linux_other_command(self) -> list[str]:
        if self._settings.codec == "mp3":
            return ["lame",
                    "-b", str(self._settings.bitrate),
                    "-r",
                    "-"]

        if self._settings.codec == "ogg":
            return ["oggenc",
                    "-b", str(self._settings.bitrate),
                    "-Q",
                    "-r",
                    "--ignorelength",
                    "-"]

        # Original comment: AAC > 128k for Stereo, Default sample rate: 44100Hz.
        if self._settings.codec == "aac":
            # TODO(xsdg): This always applies the 18kHz cutoff, in contrast to
            # the ffmpeg code which only applies it when segment_time is
            # included.  Figure out this discrepancy.
            return ["faac",
                    "-b", str(self._settings.bitrate),
                    "-X",
                    "-P",
                    "-c", "18000",
                    "-o", "-",
                    "-"]

        if self._settings.codec == "opus":
            return ["opusenc",
                    "-",
                    "--raw",
                    "--bitrate", str(self._settings.bitrate),
                    "--raw-rate", self._settings.samplerate,
                    "-"]

        if self._settings.codec == "wav":
            return ["sox",
                    "-t", "raw",
                    "-b", "16",
                    "-e", "signed",
                    "-c", "2",
                    "-r", self._settings.samplerate,
                    "-",
                    "-t", "wav",
                    "-b", "16",
                    "-e", "signed",
                    "-c", "2",
                    "-r", self._settings.samplerate,
                    "-L",
                    "-"]

        if self._settings.codec == "flac":
            return ["flac",
                    "-",
                    "-c",
                    "--channels", "2",
                    "--bps", "16",
                    "--sample-rate", self._settings.samplerate,
                    "--endian", "little",
                    "--sign", "signed",
                    "-s"]

        raise Exception(f"Can't handle unexpected codec {self._settings.codec}")


def is_mkv(filename: str) -> bool:
    return filename.endswith("mkv")


@dataclass
class VideoSettings:
    display: Optional[str]  # TODO(xsdg): Should this be Optional?
    fps: str
    input_file: Optional[str]
    loop: bool
    operation: OpMode
    resolution: Optional[str]
    screencast: bool
    seek: Optional[str]
    subtitles: Optional[str]
    user_command: Optional[list[str]]  # TODO(xsdg): check type.
    vcodec: str
    youtube_url: Optional[str]
    wayland_capture: Optional[tuple[int, int]] = None
    copy_video: bool = False
    cinnamon_capture: Optional[str] = None
    low_latency: bool = False


class Video:
    # Differences compared to original policies:
    # - Using `veryfast` preset across the board, instead of `ultrafast`.
    # - Differences in vencode policy (see function).
    # - Avoids running ffmpeg with panic loglevel when --debug specified.
    #

    def __init__(self, video_settings: VideoSettings):
        self._settings = video_settings

    @property
    def command(self) -> SubprocessCommand:
        if self._settings.operation == OpMode.YOUTUBE:
            return ["yt-dlp", "-o", "-", self._settings.youtube_url]

        if self._settings.operation == OpMode.SCREENCAST:
            return self._screencast_command()

        if self._settings.user_command:
            return self._settings.user_command

        if self._settings.operation == OpMode.INPUT_FILE:
            return self._input_file_command()

        # TODO(xsdg): Figure out if there's any way to actually get here.
        raise Exception("Internal error: Unexpected video operation mode "
                        f"{self._settings.operation}")

    def _screencast_command(self) -> list[str]:
        if self._settings.cinnamon_capture is not None:
            size = resolution.resolution(self._settings.resolution or "1080p", True)
            width, height = size.split("x")
            return self._gst_screencast_command([
                "shmsrc", "socket-path=" + self._settings.cinnamon_capture,
                "is-live=true", "do-timestamp=true", "!",
                (f"video/x-raw,format=I420,width={width},height={height},"
                 f"framerate={int(float(self._settings.fps))}/1,pixel-aspect-ratio=1/1"),
            ])
        # Wayland can't be grabbed with x11grab; capture via the portal +
        # PipeWire using a GStreamer pipeline instead. The X11 path is unchanged.
        if self._settings.wayland_capture is not None:
            return self._wayland_screencast_command()
        return self._x11_screencast_command()

    def _x11_screencast_command(self) -> list[str]:
        screen_size = resolution.resolution(
            self._settings.resolution or "1080p",
            self._settings.screencast
        )

        maybe_veryfast_cmd: list[str]
        if self._settings.vcodec != "h264_nvenc":
            maybe_veryfast_cmd = ["-preset", "veryfast"]
        else:
            maybe_veryfast_cmd = []

        keyframes = str(max(1, math.ceil(float(self._settings.fps) / 2))) if self._settings.low_latency else "60"

        return ["ffmpeg",
                "-ac", "2",
                "-ar", "44100",
                "-fragment_size", "2048",
                "-f", "pulse",
                "-ac", "2",
                "-i", "Mkchromecast.monitor",
                "-f", "x11grab",
                "-r", self._settings.fps,
                "-s", screen_size,
                "-i", "{}+0,0".format(self._settings.display),
                "-vcodec", self._settings.vcodec,
                *maybe_veryfast_cmd,
                "-tune", "ll" if self._settings.vcodec == "h264_nvenc" else "zerolatency",
                "-maxrate", "10000k",
                "-bufsize", "20000k",
                "-pix_fmt", "yuv420p",
                "-g", keyframes,
                *(["-bf", "0"] if self._settings.low_latency else []),
                "-f", "mp4",
                "-movflags", "frag_keyframe+empty_moov",
                *(["-frag_duration", "250000", "-flush_packets", "1"]
                  if self._settings.low_latency else []),
                "-ar", "44100",
                "-acodec", "aac",
                "pipe:1",
        ]

    def _wayland_screencast_command(self) -> list[str]:
        """A gst-launch pipeline: portal/PipeWire video + pulse audio → mp4.

        Reads the PipeWire stream (whose remote fd is inherited by this process
        and named via `fd=`) and the PulseAudio monitor sink, encodes H.264/AAC,
        and muxes a fragmented MP4 to stdout (fd 1) for the Flask server to relay.
        """
        fd, node = self._settings.wayland_capture
        return self._gst_screencast_command([
            "pipewiresrc", f"fd={fd}", f"path={node}", "do-timestamp=true",
        ])

    def _gst_screencast_command(self, source) -> list[str]:
        """Shared H.264/AAC encoding for compositor-provided video frames."""
        fps = str(self._settings.fps)
        low_latency = self._settings.low_latency
        key_int_max = str(max(1, math.ceil(float(fps) / 2) if low_latency else round(float(fps) * 2)))
        frame_rate = Fraction(fps).limit_denominator(1001)
        fragment_ms = 250 if low_latency else 1000
        # Dropping raw frames is safe; dropping encoded H.264 packets is not.
        raw_queue = (["!", "queue", "max-size-buffers=2", "max-size-bytes=0",
                      "max-size-time=0", "leaky=downstream"] if low_latency else [])
        encoded_queue = (["max-size-time=250000000", "max-size-buffers=0",
                          "max-size-bytes=0"] if low_latency else [])

        # Chromecast needs H.264 High profile, 4:2:0 (yuv420p / I420), at a
        # supported resolution. videoconvert otherwise negotiates 4:4:4 (which
        # the device can't decode), and the raw monitor may be >1080p, so pin
        # the chroma to I420, scale to the configured size (default 1080p), and
        # constrain the encoder to High profile.
        screen_size = resolution.resolution(
            self._settings.resolution or "1080p",
            self._settings.screencast
        )
        width, height = screen_size.split("x")

        return [
            "gst-launch-1.0", "-q",
            *source,
            "!", "videoconvert",
            "!", "videoscale",
            "!", "videorate",
            "!", (f"video/x-raw,format=I420,width={width},height={height},"
                  f"framerate={frame_rate.numerator}/{frame_rate.denominator}"),
            *raw_queue,
            "!", "x264enc", "tune=zerolatency", "speed-preset=veryfast",
            "bitrate=8000", f"key-int-max={key_int_max}",
            "!", "video/x-h264,profile=high",
            "!", "h264parse",
            "!", "queue", *encoded_queue,
            "!", "mp4mux", "name=mux", f"fragment-duration={fragment_ms}",
            "streamable=true",
            "!", "fdsink", "fd=1",
            "pulsesrc", "device=Mkchromecast.monitor",
            "!", "audioconvert",
            "!", "audioresample",
            "!", "avenc_aac",
            "!", "aacparse",
            "!", "queue", *encoded_queue,
            "!", "mux.",
        ]

    def _input_file_command(self) -> list[str]:
        if not self._settings.input_file:
            raise ValueError("Input file is not specified")
        filters = []
        if self._settings.subtitles:
            filters.append("subtitles=" + escape_filter_path(self._settings.subtitles))
        if self._settings.resolution:
            filters.append(resolution.resolutions[self._settings.resolution.lower()][0])
        video_codec = (["-c:v", "copy"] if self._settings.copy_video and not filters else
                       ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                        "-maxrate", "10000k", "-bufsize", "20000k"])
        return [
            "ffmpeg", "-nostdin", "-loglevel", "warning",
            *(["-stream_loop", "-1"] if self._settings.loop else []),
            *(["-ss", self._settings.seek] if self._settings.seek else []),
            "-re", "-i", self._settings.input_file,
            "-map", "0:v:0", "-map", "0:a:0?", "-map_chapters", "-1",
            *video_codec, "-c:a", "aac", "-ac", "2", "-b:a", "192k",
            *(["-vf", ",".join(filters)] if filters else []),
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1",
        ]


def escape_filter_path(path: str) -> str:
    """Escape both FFmpeg's option parser and filtergraph parser (no shell)."""
    value = os.path.abspath(path)
    for chars in ("\\':", "\\'[],;"):
        value = "".join("\\" + c if c in chars else c for c in value)
    return value
