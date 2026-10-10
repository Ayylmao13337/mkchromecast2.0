"""Local, read-only screencast report. No receiver connection or capture."""
from importlib import metadata
import os
import platform
import shutil
import subprocess

from mkchromecast import screens
from mkchromecast.version import __version__


def collect(backend="auto", display=None):
    report = {
        "mkchromecast": __version__, "python": platform.python_version(),
        "platform": platform.system(),
        "session_type": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown"),
        "requested_backend": backend, "checks": [], "screens": [],
        "scope": "Local dependencies and screen inventory only; does not test receiver, network, GPU encoding or capture",
    }
    checks = report["checks"]
    try:
        resolved = screens.capture_backend(backend)
        report["capture_backend"] = resolved
    except ValueError as exc:
        checks.append(dict(name="desktop", ok=False, detail=str(exc)))
        return report
    if platform.system() != "Linux":
        checks.append(dict(name="screencast", ok=False, detail="Screen capture currently supports Linux only"))
        return report
    required = {"pactl": "Install pulseaudio-utils on Mint"}
    if resolved == "x11":
        required.update(ffmpeg="Install ffmpeg", xrandr="Install x11-xserver-utils on Mint")
    else:
        required.update({"gst-launch-1.0": "Install gstreamer1.0-tools",
                         "gst-inspect-1.0": "Install gstreamer1.0-tools"})
    if resolved == "cinnamon":
        required["gdbus"] = "Install libglib2.0-bin on Mint"
    for program, hint in required.items():
        present = shutil.which(program) is not None
        checks.append(dict(name=program, ok=present, detail="Found" if present else hint))
    if resolved != "x11" and shutil.which("gst-inspect-1.0"):
        from mkchromecast.screencast_wayland import _REQUIRED_GST_ELEMENTS
        elements = set(_REQUIRED_GST_ELEMENTS) | {"videoscale", "videorate", "audioresample", "queue"}
        if resolved == "cinnamon":
            elements.discard("pipewiresrc")
            elements.update(("shmsink", "shmsrc"))
        for element in sorted(elements):
            try:
                result = subprocess.run(["gst-inspect-1.0", element],
                                        capture_output=True, timeout=3)
                ok = result.returncode == 0
                detail = "Available" if ok else "Missing GStreamer element; see docs/DIAGNOSTICS.md"
            except (OSError, subprocess.TimeoutExpired):
                ok, detail = False, "GStreamer element inspection failed or timed out"
            checks.append(dict(name="gst:" + element, ok=ok, detail=detail))
    if shutil.which("pactl"):
        try:
            result = subprocess.run(["pactl", "info"], capture_output=True, timeout=3)
            ok = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        checks.append(dict(name="audio-server", ok=ok, detail="Reachable" if ok else
                           "PulseAudio/PipeWire audio server is not reachable from this session"))
    if shutil.which("pactl"):
        try:
            from mkchromecast.pulseaudio import list_sources
            report["audio_sources"] = list_sources()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            checks.append(dict(name="audio-sources", ok=False, detail="Cannot list audio sources; check the audio server"))
    if resolved == "wayland":
        report["screen_selection"] = "Portal picker opens when capture starts; not opened by diagnostics"
        checks.append(dict(name="portal-handshake", ok=None,
                           detail="Not tested; installed plugins do not prove portal ScreenCast support"))
    else:
        try:
            report["screens"] = screens.list_screens(backend, display)
            checks.append(dict(name="screen-inventory", ok=bool(report["screens"]), detail="Read without recording"))
        except (ValueError, RuntimeError) as exc:
            checks.append(dict(name="screen-inventory", ok=False, detail=str(exc)))
    report["packages"] = {}
    for name in ("PyChromecast", "Flask", "psutil"):
        try:
            report["packages"][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            report["packages"][name] = "not installed"
    return report
