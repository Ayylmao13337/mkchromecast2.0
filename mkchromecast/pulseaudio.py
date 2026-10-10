"""PulseAudio/pipewire-pulse routing, with per-session ownership."""
import json
import subprocess
import uuid


def _list_audio(kind):
    result = subprocess.run(['pactl', '-f', 'json', 'list', kind],
                            capture_output=True, text=True, timeout=3, check=True)
    value = json.loads(result.stdout)
    if not isinstance(value, list):
        raise ValueError('Audio server returned an invalid device list')
    return value


class AudioSink:
    def __init__(self):
        self.name = "Mkchromecast_" + uuid.uuid4().hex[:12]
        self.module = None
        self.previous_routes = {}

    @property
    def monitor(self):
        return self.name + ".monitor"

    def start(self):
        # Remember existing applications, but never move them automatically.
        sinks = {sink['index']: sink['name'] for sink in _list_audio('sinks')}
        self.previous_routes = {item['index']: sinks[item['sink']]
                                for item in _list_audio('sink-inputs') if item['sink'] in sinks}
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
        errors = []
        try:
            sinks = _list_audio('sinks')
            own = next((sink['index'] for sink in sinks if sink['name'] == self.name), None)
            available = {sink['name'] for sink in sinks}
            for item in _list_audio('sink-inputs'):
                original = self.previous_routes.get(item['index'])
                # Leave applications moved elsewhere by the user untouched.
                if own is not None and item['sink'] == own and original in available:
                    try:
                        subprocess.run(['pactl', 'move-sink-input', str(item['index']), original],
                                       capture_output=True, timeout=3, check=True)
                    except (OSError, subprocess.SubprocessError) as exc:
                        errors.append(str(exc))
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))
        finally:
            try:
                subprocess.run(["pactl", "unload-module", module], capture_output=True,
                               timeout=10, check=True)
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError('Audio routing cleanup: ' + '; '.join(errors))


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


def list_sources():
    """Read available microphones and output monitors without changing routing."""
    result = subprocess.run(['pactl', '-f', 'json', 'list', 'sources'],
                            capture_output=True, text=True, timeout=3, check=True)
    return [{'name': source['name'], 'description': source.get('description', source['name'])}
            for source in json.loads(result.stdout)]
