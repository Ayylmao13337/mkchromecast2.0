"""Media descriptions shared by the receiver and HTTP server."""
from dataclasses import dataclass
from pathlib import Path

from mkchromecast import utils
from mkchromecast.constants import OpMode

AUDIO_TYPES = {
    "mp3": "audio/mpeg", "aac": "audio/aac", "ogg": "audio/ogg",
    "opus": "audio/ogg", "wav": "audio/wav", "flac": "audio/flac",
}


@dataclass(frozen=True)
class MediaPlan:
    media_type: str
    stream_type: str = "LIVE"
    direct_file: str | None = None
    copy_video: bool = False


def plan_media(settings) -> MediaPlan:
    if getattr(settings, "command", None):
        return MediaPlan(settings.mtype or "video/mp4")
    if settings.operation == OpMode.SOURCE_URL:
        media_type = settings.mtype or ("video/mp4" if settings.videoarg else
                                        AUDIO_TYPES.get(settings.codec))
        if not media_type:
            raise ValueError("Specify a supported audio codec for --source-url")
        return MediaPlan(media_type)
    if settings.operation == OpMode.YOUTUBE:
        return MediaPlan("video/mp4" if settings.videoarg else "audio/mpeg")
    if settings.operation == OpMode.INPUT_FILE and settings.input_file:
        info = utils.probe_media(settings.input_file)
        streams = info.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if settings.videoarg:
            if video is None:
                raise ValueError("The input contains no video stream")
            compatible = (video.get("codec_name") == "h264"
                          and video.get("pix_fmt") == "yuv420p"
                          and video.get("level", 999) <= 41
                          and video.get("width", 99999) <= 1920
                          and video.get("height", 99999) <= 1080)
            # Unsupported HDR needs a deliberate tone-mapping profile, never silently discard it.
            if video.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
                raise ValueError("HDR input requires a tone-mapped SDR file; automatic HDR conversion is not yet supported")
            direct = (compatible and audio is not None
                      and audio.get("codec_name") in {"aac", "mp3"}
                      and Path(settings.input_file).suffix.lower() in {".mp4", ".m4v"}
                      and not any((settings.subtitles, settings.resolution, settings.seek, settings.loop)))
            if direct:
                return MediaPlan("video/mp4", "BUFFERED", str(Path(settings.input_file).resolve()), True)
            return MediaPlan("video/mp4", copy_video=compatible)
        if audio is None:
            raise ValueError("The input contains no audio stream; use --video for video")
    if settings.videoarg:
        return MediaPlan(settings.mtype or "video/mp4")
    return MediaPlan(AUDIO_TYPES[settings.codec])


def youtube_commands(settings):
    """yt-dlp extracts; FFmpeg normalizes bytes to the declared media type."""
    producer = ["yt-dlp", "--no-playlist", "--no-progress", "-f",
                "best[ext=mp4]/best" if settings.videoarg else "bestaudio/best",
                "-o", "-", "--", settings.youtube_url]
    encoder = ["ffmpeg", "-nostdin", "-loglevel", "warning", "-i", "pipe:0"]
    if settings.videoarg:
        encoder += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                    "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-vf", "scale=w='min(1920,iw)':h='min(1080,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                    "-c:a", "aac", "-ac", "2", "-f", "mp4",
                    "-movflags", "frag_keyframe+empty_moov", "pipe:1"]
    else:
        encoder += ["-vn", "-c:a", "libmp3lame", "-b:a", f"{settings.bitrate}k",
                    "-ac", "2", "-ar", str(settings.samplerate), "-f", "mp3", "pipe:1"]
    return producer, encoder
