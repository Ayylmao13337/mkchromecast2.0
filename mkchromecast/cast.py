"""Google Cast adapter; discovery and connections belong to the caller."""
from dataclasses import dataclass
import time
import threading
import zeroconf

import pychromecast

from mkchromecast import colors, utils
from mkchromecast.constants import OpMode
from mkchromecast.version import __version__


@dataclass(frozen=True)
class AvailableDevice:
    index: int
    name: str
    type: str
    id: str = ""
    host: str = ""

    def __str__(self):
        return f"{self.index} \t{self.type} \t{self.name} \t{self.id}"


def print_available_devices(devices):
    print("Index  Type  Name  ID")
    for device in devices:
        print(device)


class Casting:
    def __init__(self, mkcc):
        self.mkcc = mkcc
        self.title = "Mkchromecast v" + __version__
        self.ip = mkcc.host
        self.cast = None
        self.plan = None
        self._browser = None
        self._zeroconf = None
        self._chromecasts = []
        self._by_id = {}
        self._devices = []
        self._owns_media = False

    def initialize_cast(self, cancel=None):
        self.close()
        self._zeroconf = zeroconf.Zeroconf()
        changed = threading.Event()
        listener = pychromecast.SimpleCastListener(lambda *_: changed.set())
        self._browser = pychromecast.CastBrowser(listener, self._zeroconf)
        self._browser.start_discovery()
        deadline = time.monotonic() + self.mkcc.discovery_timeout
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise RuntimeError("Discovery cancelled")
            changed.wait(min(.1, max(0, deadline - time.monotonic())))
            changed.clear()
            if self.mkcc.device_id and any(str(k) == self.mkcc.device_id for k in self._browser.devices):
                break
        self._by_id = {str(k): v for k, v in self._browser.devices.copy().items()}
        self._devices = [AvailableDevice(i, c.friendly_name, "Gcast", identity, c.host or "")
                         for i, (identity, c) in enumerate(sorted(self._by_id.items()))]

    @property
    def available_devices(self):
        return list(self._devices)

    def select_a_device(self):
        print_available_devices(self.available_devices)
        while True:
            try:
                self.index = int(input("Select device index: "))
                if 0 <= self.index < len(self._devices):
                    return
            except ValueError:
                pass
            print("Please enter an index shown above.")

    def input_device(self, write_to_pickle=False):
        self.mkcc.device_id = self._devices[self.index].id

    def get_devices(self):
        if not self._devices:
            raise RuntimeError("No Chromecast devices found")
        if self.mkcc.device_id:
            selected = next((d for d in self._devices if d.id == self.mkcc.device_id), None)
            if selected is None:
                raise ValueError("The selected Chromecast is no longer available")
        elif self.mkcc.device_name:
            matches = [d for d in self._devices if d.name == self.mkcc.device_name]
            if len(matches) != 1:
                raise ValueError("Device name is missing or ambiguous; select a --device-id")
            selected = matches[0]
        elif self.mkcc.select_device and self.mkcc.operation != OpMode.TRAY:
            self.select_a_device()
            selected = self._devices[self.index]
        else:
            selected = self._devices[0]
        self.cast = pychromecast.get_chromecast_from_cast_info(
            self._by_id[selected.id], self._zeroconf,
            tries=self.mkcc.tries if self.mkcc.tries is not None else 3, timeout=10)
        self._chromecasts.append(self.cast)
        self.cast_to = selected.name
        self.cast.wait(timeout=30)
        self.ip = self.mkcc.host or utils.address_for_receiver(self.cast.socket_client.host)
        self.mkcc.host = self.ip
        return selected

    def play_cast(self):
        if self.mkcc.debug is True:
            print("def play_cast(self):")
        if not self.cast:
            print(colors.warning("Calling get_devices before proceeding with play_cast"))
            self.get_devices()
            if not self.cast:
                raise Exception("Internal error, self.cast was not set.")
        localip = self.ip

        try:
            print(
                colors.options("The IP of ")
                + colors.success(self.cast_to)
                + colors.options(" is:")
                + " "
                + self.cast.socket_client.host  # valid since at least v3.0.0
            )
        except TypeError:
            print(
                colors.options("The IP of ")
                + colors.success(self.cast_to.player_name)
                + colors.options(" is:")
                + " "
                + self.cast_to.ip_address
            )

        if self.mkcc.host is None:
            print(colors.options("Your local IP is:") + " " + localip)
        else:
            print(colors.options("Your manually entered local IP is:") + " " + localip)

        media_controller = self.cast.media_controller

        from mkchromecast.media import AUDIO_TYPES
        plan = getattr(self, "plan", None)
        media_type = (plan.media_type if plan is not None else
                      self.mkcc.mtype or ("video/mp4" if self.mkcc.videoarg else AUDIO_TYPES[self.mkcc.codec]))
        play_url = (self.mkcc.source_url if self.mkcc.operation == OpMode.SOURCE_URL
                    else utils.http_url(localip, self.mkcc.port))
        media_controller.play_media(
            play_url, media_type, title=self.title, stream_type=plan.stream_type if plan is not None else "LIVE",
        )

        # play_media(autoplay=True) starts playback once the device fetches the
        # stream and establishes a media session. That handshake is async and,
        # for a cold start (e.g. a Wayland screencast: portal grant + GStreamer
        # / x264 init + buffering), can take well over the few seconds we used
        # to sleep blindly. Wait for the session to actually become active
        # instead. Issuing play() before a session exists raises RequestFailed
        # and previously crashed the whole cast even though the stream was fine.
        self._owns_media = True
        media_controller.block_until_active(timeout=30.0)

        print(" ")
        print(colors.important("Cast media controller status"))
        print(" ")
        print(self.cast.status)
        print(" ")

        if media_controller.status.player_is_playing:
            # autoplay already started playback; nothing more to do.
            pass
        elif media_controller.is_active:
            media_controller.play()
        else:
            print(colors.warning(
                "The cast device did not establish a media session in time. "
                "If playback does not start on its own, please retry the cast."))

    def pause(self):
        self.cast.media_controller.pause()

    def play(self):
        self.cast.media_controller.play()

    def set_volume(self, value):
        return self.cast.set_volume(max(0.0, min(1.0, value)))

    def volume_up(self):
        return self.cast.set_volume(min(1.0, self.cast.status.volume_level + 0.1))

    def volume_down(self):
        return self.cast.set_volume(max(0.0, self.cast.status.volume_level - 0.1))

    def stop_cast(self):
        if not self.cast or not self._owns_media:
            return
        self._owns_media = False
        # Do not quit another sender's app/media if the receiver was taken over.
        content_id = self.cast.media_controller.status.content_id
        expected = (self.mkcc.source_url if self.mkcc.operation == OpMode.SOURCE_URL
                    else utils.http_url(self.ip, self.mkcc.port))
        if content_id == expected:
            self.cast.media_controller.stop()

    def close(self):
        errors = []
        try:
            self.stop_cast()
        except Exception as exc:
            errors.append(exc)
        if self._browser is not None:
            try:
                self._browser.stop_discovery()
            except Exception as exc:
                errors.append(exc)
            self._browser = None
        for cast in self._chromecasts:
            try:
                cast.disconnect(timeout=5)
            except Exception as exc:
                errors.append(exc)
        if self._zeroconf is not None:
            self._zeroconf.close()
            self._zeroconf = None
        self._chromecasts = []
        self._by_id = {}
        self._devices = []
        self.cast = None
        if errors and self.mkcc.debug:
            print("Cast cleanup:", errors)
