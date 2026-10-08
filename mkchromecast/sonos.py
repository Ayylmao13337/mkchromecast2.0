"""Optional Sonos receiver adapter, targeting group coordinators."""
from types import SimpleNamespace

from mkchromecast import utils
from mkchromecast.cast import AvailableDevice, print_available_devices
from mkchromecast.constants import OpMode


class SonosCasting:
    def __init__(self, settings):
        self.mkcc = settings
        self.cast = None
        self.plan = None
        self._zones = {}
        self._uri = None
        self.ip = settings.host

    def initialize_cast(self, cancel=None):
        try:
            import soco
        except ImportError:
            raise RuntimeError("Sonos requires the optional dependency: pip install 'mkchromecast[sonos]'") from None
        zones = soco.discover(timeout=self.mkcc.discovery_timeout) or set()
        if cancel is not None and cancel.is_set():
            raise RuntimeError("Discovery cancelled")
        self._zones = {zone.uid: zone for zone in zones}

    @property
    def available_devices(self):
        return [AvailableDevice(i, zone.player_name, "Sonos", uid, zone.ip_address)
                for i, (uid, zone) in enumerate(sorted(self._zones.items()))]

    def get_devices(self):
        devices = self.available_devices
        if self.mkcc.device_id:
            devices = [d for d in devices if d.id == self.mkcc.device_id]
        elif self.mkcc.device_name:
            devices = [d for d in devices if d.name == self.mkcc.device_name]
            if len(devices) > 1:
                raise ValueError("Sonos name is ambiguous; use --device-id")
        if not devices:
            raise RuntimeError("No matching Sonos devices found")
        if self.mkcc.select_device and not self.mkcc.device_id and not self.mkcc.device_name:
            print_available_devices(devices)
            while True:
                try:
                    index = int(input("Select device index: "))
                    selected = next(d for d in devices if d.index == index)
                    break
                except (ValueError, StopIteration):
                    print("Enter an index shown above")
        else:
            selected = devices[0]
        self.cast = self._zones[selected.id].group.coordinator
        self.cast_to = selected.name
        self.ip = self.mkcc.host or utils.address_for_receiver(self.cast.ip_address)
        self.mkcc.host = self.ip
        return selected

    def play_cast(self):
        if self.plan.media_type not in {"audio/mpeg", "audio/aac", "audio/flac", "audio/wav"}:
            raise ValueError("This Sonos adapter supports MP3, AAC, FLAC and WAV audio")
        uri = self.mkcc.source_url if self.mkcc.operation == OpMode.SOURCE_URL else utils.http_url(self.ip, self.mkcc.port)
        self.cast.play_uri(uri, title="Mkchromecast", force_radio=self.plan.stream_type == "LIVE", timeout=10)
        self._uri = uri

    def pause(self):
        self.cast.pause(timeout=10)

    def play(self):
        self.cast.play(timeout=10)

    def set_volume(self, value):
        self.cast.volume = round(max(0.0, min(1.0, value)) * 100)

    def volume_up(self):
        self.cast.volume = min(100, self.cast.volume + 10)
        return self.cast.volume / 100

    def volume_down(self):
        self.cast.volume = max(0, self.cast.volume - 10)
        return self.cast.volume / 100

    def stop_cast(self):
        if self.cast is not None and self._uri:
            current = self.cast.get_current_track_info(timeout=10).get("uri", "")
            if current == self._uri or current == self._uri.replace("http:", "x-rincon-mp3radio:", 1):
                self.cast.stop(timeout=10)
            self._uri = None

    def close(self):
        try:
            self.stop_cast()
        finally:
            self.cast = None
            self._zones = {}
