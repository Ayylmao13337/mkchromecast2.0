"""Read-only monitor discovery and explicit X11 capture selection."""
import os
import re
import subprocess
import time

from mkchromecast.screencast_wayland import is_wayland_session


def capture_backend(requested="auto"):
    if requested == "cinnamon":
        if is_wayland_session() or "cinnamon" not in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
            raise ValueError("Cinnamon capture requires a Cinnamon X11 session")
        return "cinnamon"
    return "wayland" if is_wayland_session() else "x11"


def parse_xrandr(text):
    screens = []
    for line in text.splitlines():
        match = re.match(r"^(\S+) connected (primary )?(\d+)x(\d+)([+-]\d+)([+-]\d+)\b", line)
        if match:
            name, primary, width, height, x, y = match.groups()
            screens.append(dict(id=name, primary=bool(primary), width=int(width),
                                height=int(height), x=int(x), y=int(y)))
    return screens


def list_screens(backend="auto", display=None):
    backend = capture_backend(backend)
    if backend == "wayland":
        raise ValueError("Wayland screen selection uses the portal picker when capture starts; --screen is not supported")
    if backend == "cinnamon":
        from mkchromecast.screencast_cinnamon import CinnamonCaptureSession
        return CinnamonCaptureSession(25)._call("list")
    command = ["xrandr", "--current"]
    if display:
        command.extend(["--display", display])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=True)
    except FileNotFoundError:
        raise ValueError("Screen selection needs xrandr; on Mint install x11-xserver-utils") from None
    except subprocess.TimeoutExpired:
        raise ValueError("xrandr timed out reading the X11 display") from None
    except subprocess.CalledProcessError as exc:
        raise ValueError("Cannot list X11 screens: " + (exc.stderr or "xrandr failed").strip()[-500:]) from None
    screens = parse_xrandr(result.stdout)
    if not screens:
        raise ValueError("No active X11 screens found; check DISPLAY and the desktop session")
    return screens


def choose_screen(screens, selector):
    if selector == "primary":
        matches = [screen for screen in screens if screen["primary"]]
    else:
        matches = [screen for screen in screens if screen["id"] == selector]
    if len(matches) != 1:
        available = ", ".join(screen["id"] for screen in screens)
        raise ValueError(f"Screen {selector!r} is not available. Available IDs: {available}")
    return matches[0]


class X11ScreenSelection:
    def __init__(self, selector, display=None):
        self.selector = selector
        self.display = display
        self.selected = choose_screen(list_screens("auto", display), selector)
        if self.selected["x"] < 0 or self.selected["y"] < 0:
            raise ValueError("X11 capture requires non-negative screen offsets; reposition the screen or use Cinnamon capture")
        self._next_check = time.monotonic() + 3

    @property
    def geometry(self):
        return tuple(self.selected[key] for key in ("x", "y", "width", "height"))

    def check(self):
        if time.monotonic() < self._next_check:
            return
        self._next_check = time.monotonic() + 3
        current = choose_screen(list_screens("auto", self.display), self.selector)
        if any(current[key] != self.selected[key] for key in ("id", "x", "y", "width", "height")):
            raise ValueError("Selected screen changed; restart screen sharing")
