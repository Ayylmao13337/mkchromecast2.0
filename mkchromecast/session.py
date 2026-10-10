"""One resource owner shared by the CLI and the tray."""
import threading
import time

from mkchromecast.constants import OpMode
from mkchromecast.media import plan_media


def receiver_for(settings):
    if settings.receiver == "sonos":
        from mkchromecast.sonos import SonosCasting
        return SonosCasting(settings)
    from mkchromecast.cast import Casting
    return Casting(settings)


class CastSession:
    def __init__(self, settings):
        self.settings = settings
        self.receiver = receiver_for(settings)
        self.pipeline = None
        self.sink = None
        self.router = None
        self.cancel = threading.Event()
        self.state = "idle"
        self.last_error = None
        self.cleanup_errors = []
        self._closed = False
        self._next_retry = 0
        self._retry_delay = 1
        self._last_check = 0

    def start(self):
        self.state = "preparing"
        try:
            plan = plan_media(self.settings)
            self.settings.direct_file = plan.direct_file
            self.settings.copy_video = plan.copy_video
            self.receiver.initialize_cast(cancel=self.cancel)
            self.receiver.get_devices()
            self.receiver.plan = plan
            self._check_cancelled()
            capture = self.settings.operation in {OpMode.AUDIOCAST, OpMode.TRAY, OpMode.SCREENCAST}
            self.settings.capture_device = "Mkchromecast.monitor"
            if capture and self.settings.platform == "Linux" and not self.settings.adevice:
                from mkchromecast.pulseaudio import AudioSink
                source = getattr(self.settings, "audio_source", None)
                if source:
                    from mkchromecast.pulseaudio import list_sources
                    if source not in {item['name'] for item in list_sources()}:
                        raise ValueError("Selected audio source is no longer available; refresh audio sources")
                    self.settings.capture_device = source
                else:
                    self.sink = AudioSink().start()
                    self.settings.capture_device = self.sink.monitor
                    print(f"Select {self.sink.name} in your audio mixer to route application audio")
            if capture and self.settings.platform == "Darwin":
                from mkchromecast.audio_devices import AudioRouter
                self.router = AudioRouter()
                self.router.start()
            if self.settings.operation != OpMode.SOURCE_URL:
                if self.settings.operation == OpMode.YOUTUBE:
                    from mkchromecast.audio import main
                elif self.settings.videoarg:
                    from mkchromecast.video import main
                elif self.settings.backend == "node" and capture:
                    from mkchromecast.node import stream_audio as main
                else:
                    from mkchromecast.audio import main
                self.pipeline = main(self.settings, cancel=self.cancel)
            self._check_cancelled()
            self.state = "connecting"
            self.receiver.play_cast()
            self._check_cancelled()
            self.state = "playing"
            return self
        except BaseException as exc:
            self.last_error = str(exc)
            self.close()
            self.state = "failed"
            raise

    def _check_cancelled(self):
        if self.cancel.is_set():
            raise RuntimeError("Casting cancelled")

    def check(self):
        if self.pipeline:
            self.pipeline.check()
        # Reconnect remains explicitly opt-in, never grows new monitoring threads.
        now = time.monotonic()
        if self.state != "playing" or not self.settings.hijack or self.settings.receiver != "chromecast" or now < self._next_retry:
            return
        if now - self._last_check < 1:
            return
        self._last_check = now
        from mkchromecast import utils
        controller = self.receiver.cast.media_controller
        expected = (self.settings.source_url if self.settings.operation == OpMode.SOURCE_URL
                    else utils.http_url(self.settings.host, self.settings.port))
        if controller.status.content_id not in (None, "", expected):
            # Another sender owns playback now. Do not take it back.
            return
        if controller.is_active:
            self._retry_delay = 1
            return
        self._next_retry = now + self._retry_delay
        self._retry_delay = min(30, self._retry_delay * 2)
        self.receiver.play_cast()

    def pause(self):
        self.receiver.pause()
        if (self.pipeline and self.settings.videoarg
                and getattr(self.settings, "capture_backend", "auto") != "cinnamon"):
            self.pipeline.pause()
        self.state = "paused"

    def resume(self):
        if (self.pipeline and self.settings.videoarg
                and getattr(self.settings, "capture_backend", "auto") != "cinnamon"):
            self.pipeline.resume()
        self.receiver.play()
        self.state = "playing"

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.cancel.set()
        self.state = "stopping"
        # Every cleanup is attempted, even if receiver/network restoration fails.
        errors = []
        for resource in (self.pipeline, self.receiver, self.router, self.sink):
            if resource is not None:
                try:
                    resource.close()
                except Exception as exc:
                    errors.append(str(exc))
        self.state = "idle"
        self.cleanup_errors = errors
        if errors:
            self.last_error = "; ".join(errors)
            print("Cleanup warning:", self.last_error)
