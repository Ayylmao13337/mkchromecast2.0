# This file is part of mkchromecast.

import configparser
import os
import pathlib
import tempfile
from typing import Optional

# NOTE: Can't import mkchromecast because that would create a circular dependency.

# Section name.
SETTINGS = "settings"

# Field names.
BACKEND = "backend"
CODEC = "codec"
BITRATE = "bitrate"
SAMPLERATE = "samplerate"
NOTIFICATIONS = "notifications"
COLORS = "colors"
SEARCH_AT_LAUNCH = "search_at_launch"
ALSA_DEVICE = "alsa_device"


def _default_config_path(platform: str) -> pathlib.Path:
    config_dir: pathlib.PurePath
    if platform == "Darwin":
        config_dir = pathlib.PosixPath(
            "~/Library/Application Support/mkchromecast")
    else:  # Linux
        xdg_config_home = pathlib.PosixPath(
            os.environ.get("XDG_CONFIG_HOME", "~/.config"))
        config_dir = xdg_config_home / "mkchromecast"

    return (config_dir / "mkchromecast.cfg").expanduser()


class Config:
    """This represents a configuration, as backed by a config on disk.

    To use without updating settings, you can either use the `load_and_validate`
    method directly, or use it as a context manager, which will call that
    function.

    The context manager usage will _also_ consider saving updated files back to
    disk (depending on whether the instance is specified as read-only or not).
    That is the only supported way to write updated values to disk.
    """

    def __init__(self,
                 platform: str,
                 config_path: Optional[os.PathLike] = None,
                 read_only: bool = False,
                 debug: bool = False):
        self._debug = debug
        self._platform = platform
        self._read_only = read_only

        if config_path:
            self._config_path = pathlib.Path(config_path)
        else:
            self._config_path = _default_config_path(self._platform)

        self._config = configparser.ConfigParser()

        self._default_conf = {
            CODEC: "mp3",
            BITRATE: 192,
            SAMPLERATE: 44100,
            NOTIFICATIONS: False,
            COLORS: "black",
            SEARCH_AT_LAUNCH: False,
            ALSA_DEVICE: None,
        }

        if self._platform == "Darwin":
            self._default_conf[BACKEND] = "node"
        else:
            self._default_conf[BACKEND] = "parec"

    def __enter__(self):
        """Parses config file and returns self"""
        self.load_and_validate()

        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.validate()
            self._maybe_write_config()

    def load_and_validate(self) -> None:
        """Loads config from disk and validates that no settings are missing.

        Missing settings receive defaults in memory. A successful writable
        context exit persists them atomically.
        """
        self._config.clear()
        source = self._config_path
        legacy = source.with_name("mkchromecast_beta.cfg")
        if not source.exists() and source.name == "mkchromecast.cfg" and legacy.exists():
            source = legacy
        self._config.read(source)
        if not self._config.has_section(SETTINGS):
            self._config.add_section(SETTINGS)
        for key, value in self._default_conf.items():
            if not self._config.has_option(SETTINGS, key):
                setattr(self, key, value)
        self.validate()

    def validate(self) -> None:
        from mkchromecast.constants import ALL_CODECS, backend_options_for_platform
        if self.backend not in backend_options_for_platform(self._platform):
            raise ValueError(f"Unsupported audio backend in configuration: {self.backend}")
        if self.codec not in ALL_CODECS:
            raise ValueError(f"Unsupported codec in configuration: {self.codec}")
        if self.bitrate <= 0 or not 22050 <= self.samplerate <= 192000:
            raise ValueError("Configuration bitrate/sample rate is out of range")
        if self.colors not in {"black", "blue", "white"}:
            raise ValueError("Configuration icon color must be black, blue or white")
        # Force ConfigParser's boolean validation, too.
        _ = self.notifications, self.search_at_launch
        if self.backend == "node" and self.codec != "mp3":
            raise ValueError("The node backend only supports mp3")
        if self.codec == "opus":
            self.samplerate = 48000

    def write_defaults(self) -> None:
        self._config.clear()
        self._config.add_section(SETTINGS)
        for key, value in self._default_conf.items():
            setattr(self, key, value)
        self._maybe_write_config()

    def _maybe_write_config(self) -> None:
        if self._read_only:
            return
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._config_path.parent,
                prefix=".mkchromecast-", delete=False,
            ) as output:
                temporary = pathlib.Path(output.name)
                self._config.write(output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self._config_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    # TODO(xsdg): Refactor this to avoid code duplication.  Sadly,
    # functools.partialmethod doesn't work with properties.
    @property
    def backend(self) -> str:
        return self._config.get(SETTINGS, BACKEND)

    @backend.setter
    def backend(self, value: str) -> None:
        self._config.set(SETTINGS, BACKEND, value)

    @property
    def codec(self) -> str:
        return self._config.get(SETTINGS, CODEC)

    @codec.setter
    def codec(self, value: str) -> None:
        self._config.set(SETTINGS, CODEC, value)

    @property
    def bitrate(self) -> int:
        return self._config.getint(SETTINGS, BITRATE)

    @bitrate.setter
    def bitrate(self, value: int) -> None:
        self._config.set(SETTINGS, BITRATE, str(value))

    @property
    def samplerate(self) -> int:
        return self._config.getint(SETTINGS, SAMPLERATE)

    @samplerate.setter
    def samplerate(self, value: int) -> None:
        self._config.set(SETTINGS, SAMPLERATE, str(value))

    @property
    def notifications(self) -> bool:
        return self._config.getboolean(SETTINGS, NOTIFICATIONS)

    @notifications.setter
    def notifications(self, value: bool) -> None:
        self._config.set(SETTINGS, NOTIFICATIONS, str(value))

    @property
    def colors(self) -> str:
        return self._config.get(SETTINGS, COLORS)

    @colors.setter
    def colors(self, value: str) -> None:
        self._config.set(SETTINGS, COLORS, value)

    @property
    def search_at_launch(self) -> bool:
        return self._config.getboolean(SETTINGS, SEARCH_AT_LAUNCH)

    @search_at_launch.setter
    def search_at_launch(self, value: bool) -> None:
        self._config.set(SETTINGS, SEARCH_AT_LAUNCH, str(value))

    @property
    def alsa_device(self) -> Optional[str]:
        stored_value = self._config.get(SETTINGS, ALSA_DEVICE)
        if stored_value == "None":
            return None

        return stored_value

    @alsa_device.setter
    def alsa_device(self, value: Optional[str]) -> None:
        self._config.set(SETTINGS, ALSA_DEVICE, str(value))
