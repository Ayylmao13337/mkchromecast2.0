"""Validated, atomic GUI preferences independent of audio configuration."""
import json
import os
import tempfile
from mkchromecast.config import _default_config_path


def load(platform):
    try:
        value = json.loads(_default_config_path(platform).with_name('desktop.json').read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save(platform, value):
    path = _default_config_path(platform).with_name('desktop.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(value, stream)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def error_help(message):
    text = message.lower()
    if any(word in text for word in ('missing', 'not installed', 'no such file', 'gstreamer')):
        return 'Required software may be missing. Run Check setup and install the packages listed there.'
    if any(word in text for word in ('cinnamon', 'capture', 'screen', 'xrandr')):
        return 'Check the capture method and refresh the screen list. A disconnected screen must be selected again.'
    if any(word in text for word in ('pactl', 'pulse', 'audio', 'source')):
        return 'Refresh the audio sources and check the desktop sound settings.'
    if any(word in text for word in ('connect', 'receiver', 'chromecast', 'timed out', 'network')):
        return 'Check that the receiver is on the same network, then use Retry connection or Find devices.'
    return 'Run Check setup for local checks. You can select and copy the technical details below.'
