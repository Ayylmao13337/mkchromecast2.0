"""PulseAudio/pipewire-pulse routing, with per-session ownership."""
import json
import subprocess
import uuid


class AudioSink:
    def __init__(self):
        self.name = "Mkchromecast_" + uuid.uuid4().hex[:12]
        self.module = None

    @property
    def monitor(self):
        return self.name + ".monitor"

    def start(self):
        result = subprocess.run(
            ["pactl", "load-module", "module-null-sink", "sink_name=" + self.name,
             "sink_properties=device.description=" + self.name,
             "rate=44100", "channels=2"], capture_output=True, text=True,
            timeout=15, check=True)
        module = result.stdout.strip()
        if not module.isdigit():
            raise RuntimeError("pactl did not return a valid module ID")
        self.module = module
        return self

    def close(self):
        if self.module is None:
            return
        module, self.module = self.module, None
        subprocess.run(["pactl", "unload-module", module], capture_output=True,
                       timeout=10, check=True)


# Compatibility helpers for external users of the old module. Normal sessions
# own their AudioSink directly; reset is an explicit user action.
_legacy_sink = None


def create_sink():
    global _legacy_sink
    if _legacy_sink is None:
        _legacy_sink = AudioSink().start()
    return _legacy_sink


def remove_sink():
    global _legacy_sink
    if _legacy_sink is not None:
        sink, _legacy_sink = _legacy_sink, None
        sink.close()


def check_sink():
    return _legacy_sink is not None


def get_sink_list():
    result = subprocess.run(["pactl", "-f", "json", "list", "modules"],
                            capture_output=True, text=True, timeout=15, check=True)
    return [m["index"] for m in json.loads(result.stdout)
            if m.get("name") == "module-null-sink"
            and "sink_name=Mkchromecast" in m.get("argument", "")]


def reset_sinks():
    for module in get_sink_list():
        subprocess.run(["pactl", "unload-module", str(module)], capture_output=True,
                       timeout=10, check=True)
