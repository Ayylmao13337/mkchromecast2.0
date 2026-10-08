"""Explicit audio setup; importing this module has no runtime side effects."""
from functools import partial

from mkchromecast import Mkchromecast, constants, pipeline_builder, stream_infra, utils
from mkchromecast.constants import OpMode
from mkchromecast.media import AUDIO_TYPES, youtube_commands


def _flask_init(settings):
    backend = stream_infra.BackendInfo(settings.backend, settings.backend)
    sample_rate = 48000 if settings.codec == "opus" else utils.quantize_sample_rate(settings.codec, settings.samplerate)
    encode = pipeline_builder.EncodeSettings(
        codec=settings.codec, adevice=settings.adevice,
        bitrate=utils.clamp_bitrate(settings.codec, settings.bitrate),
        frame_size=32 * settings.chunk_size, samplerate=str(sample_rate),
        segment_time=None, ffmpeg_debug=settings.debug,
    )
    producer = None
    media_type = AUDIO_TYPES[settings.codec]
    if settings.operation == OpMode.YOUTUBE:
        producer, command = youtube_commands(settings)
        media_type = "video/mp4" if settings.videoarg else "audio/mpeg"
    elif settings.operation == OpMode.INPUT_FILE:
        fmt = "adts" if settings.codec == "aac" else settings.codec
        command = ["ffmpeg", "-nostdin", "-loglevel", "warning",
                   *(["-stream_loop", "-1"] if settings.loop else []),
                   *(["-ss", settings.seek] if settings.seek else []),
                   "-re", "-i", settings.input_file, "-map", "0:a:0", "-vn",
                   "-c:a", pipeline_builder.Audio._ffmpeg_fmt_to_acodec[fmt],
                   "-ac", "2", "-ar", str(sample_rate),
                   *(["-b:a", f"{encode.bitrate}k"] if settings.codec in constants.CODECS_WITH_BITRATE else []),
                   "-f", fmt, "pipe:1"]
    else:
        command = pipeline_builder.Audio(backend, settings.platform, encode).command
        if backend.name == "parec":
            producer = [backend.path, "--format=s16le", "--rate=" + str(sample_rate),
                        "--channels=2", "-d", settings.capture_device]
            # All raw PCM encoders must agree with the producer's format.
            if settings.codec == "mp3":
                command = ["lame", "-r", "-s", str(sample_rate / 1000), "-b", str(encode.bitrate), "-", "-"]
            elif settings.codec == "ogg":
                command = ["oggenc", "-r", "-R", str(sample_rate), "-C", "2", "-b", str(encode.bitrate), "--ignorelength", "-o", "-", "-"]
            elif settings.codec == "aac":
                command = ["faac", "-P", "-R", str(sample_rate), "-C", "2", "-B", "16", "-X", "-b", str(encode.bitrate), "-o", "-", "-"]
        else:
            command = [settings.capture_device if v == "Mkchromecast.monitor" else v for v in command]
    stream_infra.FlaskServer.init_audio(
        adevice=encode.adevice, backend=backend, bitrate=encode.bitrate,
        buffer_size=max(8192, min(1024 * 1024, 2 * settings.chunk_size ** 2)),
        codec=settings.codec, command=command, producer=producer,
        media_type=media_type, platform=settings.platform, samplerate=str(sample_rate),
    )


def main(settings=None, cancel=None):
    settings = settings or Mkchromecast()
    pipeline = stream_infra.PipelineProcess(partial(_flask_init, settings),
                                            settings.host, settings.port, settings.platform)
    pipeline.start(timeout=settings.startup_timeout, cancel=cancel)
    return pipeline
