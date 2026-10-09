"""Opt-in Cinnamon 6.4 compositor capture, without changing recorder settings.

The recorder writes raw I420 frames to a private GStreamer shared-memory socket.
Encoding and audio run in our existing streaming subprocess, not Cinnamon.
org.Cinnamon.Eval is a version-specific bridge, not a portable screencast API.
"""
import ast
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from mkchromecast import resolution, screencast_wayland


class CinnamonError(RuntimeError):
    pass


def preflight():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "cinnamon" not in desktop or screencast_wayland.is_wayland_session():
        raise CinnamonError("--capture-backend cinnamon requires a Cinnamon X11 session")
    missing = [name for name in ("gdbus", "gst-launch-1.0", "gst-inspect-1.0")
               if shutil.which(name) is None]
    if not missing:
        elements = set(screencast_wayland._REQUIRED_GST_ELEMENTS) - {"pipewiresrc"}
        elements.update(("shmsink", "shmsrc", "videoscale", "videorate", "audioresample", "queue"))
        for element in sorted(elements):
            try:
                result = subprocess.run(["gst-inspect-1.0", element],
                                        capture_output=True, timeout=5)
            except subprocess.TimeoutExpired as exc:
                raise CinnamonError(f"GStreamer inspection timed out: {element}") from exc
            if result.returncode:
                missing.append(element)
    if missing:
        raise CinnamonError(
            "Cinnamon capture is missing: " + ", ".join(missing) +
            ". On Mint install libglib2.0-bin gstreamer1.0-tools "
            "gstreamer1.0-plugins-base gstreamer1.0-plugins-good "
            "gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav")


def _evaluate(script):
    """Call the existing session API; never enable a disabled Eval interface."""
    try:
        result = subprocess.run([
            "gdbus", "call", "--session", "--dest", "org.Cinnamon",
            "--object-path", "/org/Cinnamon", "--method", "org.Cinnamon.Eval",
            script,
        ], capture_output=True, text=True, timeout=5, check=True)
        # gdbus prints a (boolean, string) GVariant. Only translate its leading
        # boolean; never replace text inside the JSON payload.
        output = result.stdout.strip()
        if output.startswith("(true,"):
            output = "(True," + output[len("(true,"):]
        elif output.startswith("(false,"):
            output = "(False," + output[len("(false,"):]
        success, payload = ast.literal_eval(output)
        if not success:
            raise CinnamonError("Cinnamon rejected the capture bridge: " + payload)
        response = json.loads(payload)
        if isinstance(response, dict) and "error" in response:
            raise CinnamonError(response["error"])
        return response
    except (subprocess.SubprocessError, OSError, ValueError, SyntaxError) as exc:
        raise CinnamonError(
            "Cannot use Cinnamon's capture API. This experimental backend targets "
            "Cinnamon 6.4 on X11; see docs/CINNAMON_CAPTURE.md. " + str(exc)) from exc


class CinnamonCaptureSession:
    """One owned recorder with a 20-second compositor-side orphan lease.

    check() runs in the HTTP server's main loop, not a background heartbeat:
    stopping/killing that process therefore expires the lease automatically.
    """

    def __init__(self, fps, output_resolution=None):
        self.fps = int(float(fps))
        if self.fps != float(fps) or not 1 <= self.fps <= 60:
            raise CinnamonError("Cinnamon capture requires integer FPS from 1 to 60")
        self.width, self.height = map(int, resolution.resolution(output_resolution or "1080p", True).split("x"))
        self._token = uuid.uuid4().hex
        self._directory = None
        self._attempted = False
        self._next_check = 0
        self._script = files("mkchromecast").joinpath("resources/cinnamon-capture.js").read_text()

    def _call(self, action, **kwargs):
        config = json.dumps(dict(action=action, token=self._token, **kwargs))
        # Preserve Error.message, which Cinnamon's JSON.stringify(Error) loses.
        return _evaluate("(() => { try { " + self._script +
                         "\nreturn mkchromecastCapture(" + config +
                         "); } catch (e) { return {error: String(e.message || e)}; } })()")

    def open(self):
        if self._directory is not None:
            raise CinnamonError("Capture session already opened")
        # Private 0700 directory and 0600 SHM; no desktop stream on a LAN port.
        self._directory = tempfile.TemporaryDirectory(prefix="mkchromecast-cinnamon-")
        socket_path = str(Path(self._directory.name) / "frames")
        # gst-launch syntax uses quoted strings, not shell quoting.
        escaped_path = socket_path.replace("\\", "\\\\").replace('"', '\\"')
        size = max(32 * 1024 * 1024, self.width * self.height * 6)
        pipeline = (
            "queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 leaky=downstream ! "
            "videoconvert ! videoscale ! "
            f"video/x-raw,format=I420,width={self.width},height={self.height},pixel-aspect-ratio=1/1 ! "
            f'shmsink socket-path="{escaped_path}" shm-size={size} perms=384 '
            "wait-for-connection=false sync=false"
        )
        self._attempted = True
        try:
            self._call("start", fps=self.fps, pipeline=pipeline)
            deadline = time.monotonic() + 5
            while not Path(socket_path).exists():
                if time.monotonic() >= deadline:
                    raise CinnamonError("Cinnamon did not create the capture socket")
                time.sleep(.05)
            self.check()
            return socket_path
        except BaseException:
            self.close()
            raise

    def check(self):
        now = time.monotonic()
        if now >= self._next_check:
            self._call("heartbeat")
            self._next_check = now + 4

    def close(self):
        if self._attempted:
            self._attempted = False
            try:
                self._call("stop")
            except CinnamonError as exc:
                # The compositor-side lease still expires after a failed stop.
                print(f"Cinnamon capture cleanup: {exc}; orphan lease expires within 20 seconds")
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
