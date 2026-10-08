"""macOS audio routing with restoration of the actual previous devices."""
from pathlib import Path
import shutil
import subprocess


class AudioRouter:
    def __init__(self):
        self.binary = shutil.which("SwitchAudioSource")
        self.modern = self.binary is not None
        if not self.binary:
            helper = Path(__file__).resolve().parent.parent / "bin/audiodevice"
            if helper.is_file():
                self.binary = str(helper)
        self.previous = {}

    def _get(self, kind):
        command = ([self.binary, "-c", "-t", kind] if self.modern else [self.binary, kind])
        return subprocess.run(command, capture_output=True, text=True,
                              check=True, timeout=10).stdout.strip()

    def _set(self, kind, name):
        command = ([self.binary, "-t", kind, "-s", name] if self.modern else
                   [self.binary, kind, name])
        subprocess.run(command, capture_output=True, check=True, timeout=10)

    def start(self):
        if not self.binary:
            raise RuntimeError("macOS audio requires SwitchAudioSource (switchaudio-osx) and BlackHole 16ch")
        # Snapshot both before changing either. Restore even after a partial failure.
        self.previous = {kind: self._get(kind) for kind in ("input", "output")}
        if not all(self.previous.values()):
            raise RuntimeError("Could not determine the current macOS audio devices")
        try:
            self._set("input", "BlackHole 16ch")
            self._set("output", "BlackHole 16ch")
        except BaseException:
            self.close()
            raise
        return self

    def close(self):
        previous, self.previous = self.previous, {}
        errors = []
        for kind, name in previous.items():
            try:
                self._set(kind, name)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("Could not restore macOS audio: " + "; ".join(errors))


_legacy_router = None


def inputdev():
    global _legacy_router
    if _legacy_router is None:
        _legacy_router = AudioRouter().start()


def outputdev():
    inputdev()


def inputint():
    global _legacy_router
    if _legacy_router:
        router, _legacy_router = _legacy_router, None
        router.close()


def outputint():
    inputint()
