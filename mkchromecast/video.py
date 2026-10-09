# This file is part of mkchromecast.

"""
Google Cast device has to point out to http://ip:5000/stream
"""

from functools import partial
from dataclasses import replace
import os

import mkchromecast
from mkchromecast import colors
from mkchromecast import pipeline_builder
from mkchromecast import screencast_wayland
from mkchromecast import stream_infra
from mkchromecast import utils
from mkchromecast.constants import OpMode

# The streaming child owns this portal session and closes it on teardown.
_active_wayland_session = None


def wayland_screencast_preflight(mkcc):
    """Main-process precondition check for Wayland screencast.

    Runs in the *main* process before any cast is attempted. If we're about to
    do a Wayland screencast but GStreamer (or a required element) is missing,
    print an actionable message and terminate cleanly here — rather than letting
    the forked streaming child fail later while the main process casts to a dead
    stream. The portal handshake itself must stay in the child (the PipeWire fd
    is only valid there), so only this pure capability check pre-flights early.
    """
    if not (mkcc.operation == OpMode.SCREENCAST
            and screencast_wayland.is_wayland_session()):
        return

    available, missing = screencast_wayland.gstreamer_screencast_available()
    if not available:
        print(colors.error(
            "Wayland screencast needs GStreamer, but these are missing: "
            + ", ".join(missing) + "."))
        print(colors.warning(
            "Install the GStreamer pieces (on Arch: gst-plugins-base, "
            "gst-plugins-good, gst-plugins-bad, gst-plugins-ugly, gst-libav, "
            "and the PipeWire GStreamer plugin)."))
        utils.terminate()


def _build_video_settings(mkcc, wayland_capture):
    # TODO(xsdg): Passing args in one-by-one to facilitate refactoring
    # the Mkchromecast object so that it has argument groups instead of just a
    # giant set of uncoordinated and conflicting arguments.
    return pipeline_builder.VideoSettings(
        display=mkcc.display,
        fps=mkcc.fps,
        input_file=mkcc.input_file,
        loop=mkcc.loop,
        operation=mkcc.operation,
        resolution=mkcc.resolution,
        screencast=mkcc.screencast,
        seek=mkcc.seek,
        subtitles=mkcc.subtitles,
        user_command=mkcc.command,
        vcodec=mkcc.vcodec,
        youtube_url=mkcc.youtube_url,
        wayland_capture=wayland_capture,
        copy_video=getattr(mkcc, "copy_video", False),
    )


def _flask_init(mkcc=None):
    global _active_wayland_session
    mkcc = mkcc or mkchromecast.Mkchromecast()

    if getattr(mkcc, "direct_file", None):
        stream_infra.FlaskServer.init_video(
            chunk_size=65536, direct_file=mkcc.direct_file, media_type="video/mp4")
        return

    if (mkcc.operation == OpMode.SCREENCAST
            and getattr(mkcc, "capture_backend", "auto") == "cinnamon"):
        from mkchromecast.screencast_cinnamon import CinnamonCaptureSession
        capture = CinnamonCaptureSession(mkcc.fps, mkcc.resolution)
        try:
            socket_path = capture.open()
            settings = replace(_build_video_settings(mkcc, None), cinnamon_capture=socket_path)
            command = pipeline_builder.Video(settings).command
            command = ["device=" + getattr(mkcc, "capture_device", "Mkchromecast.monitor")
                       if value == "device=Mkchromecast.monitor" else value for value in command]
            if mkcc.debug:
                print(f":::cinnamon::: pipeline_builder command: {command}")
            stream_infra.FlaskServer.init_video(
                chunk_size=mkcc.chunk_size, command=command,
                media_type="video/mp4", cleanup=capture.close, health_check=capture.check,
            )
        except BaseException:
            capture.close()
            raise
        return

    if (mkcc.operation == OpMode.SCREENCAST
            and screencast_wayland.is_wayland_session()):
        try:
            _active_wayland_session = (
                screencast_wayland.PortalScreenCastSession())
            node = _active_wayland_session.open()
        except screencast_wayland.PortalError as exc:
            if _active_wayland_session is not None:
                _active_wayland_session.close()
                _active_wayland_session = None
            print(colors.error(f"Wayland screencast failed: {exc}"))
            print(colors.warning(
                "Ensure xdg-desktop-portal (with a backend such as "
                "xdg-desktop-portal-gnome, -kde, or -wlr) and PipeWire are "
                "installed and running."))
            utils.terminate()
            return

        def command_factory():
            # A fresh PipeWire fd per /stream request: the portal fd is
            # single-use, and the Chromecast may reconnect, so each gst spawn
            # needs its own fd to attach to the shared monitor node.
            fd = _active_wayland_session.open_pipewire_fd()
            os.set_inheritable(fd, True)
            try:
                command = pipeline_builder.Video(
                    _build_video_settings(mkcc, (fd, node))).command
                command = ["device=" + getattr(mkcc, "capture_device", "Mkchromecast.monitor")
                           if v == "device=Mkchromecast.monitor" else v for v in command]
            except BaseException:
                os.close(fd)
                raise
            if mkcc.debug is True:
                print(f":::gst::: pipeline_builder command: {command}")
            return command, [fd]

        stream_infra.FlaskServer.init_video(
            chunk_size=mkcc.chunk_size,
            command_factory=command_factory,
            media_type=(mkcc.mtype or "video/mp4"),
            cleanup=_active_wayland_session.close,
        )
        return

    builder = pipeline_builder.Video(_build_video_settings(mkcc, None))
    if mkcc.debug is True:
        print(f":::ffmpeg::: pipeline_builder command: {builder.command}")

    stream_infra.FlaskServer.init_video(
        chunk_size=mkcc.chunk_size,
        command=[getattr(mkcc, "capture_device", "Mkchromecast.monitor")
                 if v == "Mkchromecast.monitor" else v for v in builder.command],
        media_type=(mkcc.mtype or "video/mp4"),
    )


def main(mkcc=None, cancel=None):
    mkcc = mkcc or mkchromecast.Mkchromecast()
    if getattr(mkcc, "capture_backend", "auto") == "cinnamon":
        from mkchromecast.screencast_cinnamon import preflight
        preflight()
    wayland_screencast_preflight(mkcc)
    if (mkcc.operation == OpMode.SCREENCAST
            and screencast_wayland.is_wayland_session() and mkcc.vcodec != "libx264"):
        raise ValueError("Wayland capture currently supports --vcodec libx264 only")
    if mkcc.backend == "node" and not getattr(mkcc, "direct_file", None):
        raise ValueError("The node video compatibility option requires a directly playable MP4; use ffmpeg")
    pipeline = stream_infra.PipelineProcess(partial(_flask_init, mkcc), mkcc.host,
                                            mkcc.port, mkcc.platform)
    pipeline.start(timeout=mkcc.startup_timeout, cancel=cancel)
    return pipeline
