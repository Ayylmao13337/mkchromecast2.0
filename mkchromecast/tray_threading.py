"""Qt workers with explicit settings and no module-global receiver state."""
import threading
import queue

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from packaging.version import Version, InvalidVersion
import requests

from mkchromecast.session import CastSession, receiver_for
from mkchromecast.version import __version__


class Search(QObject):
    finished = pyqtSignal()
    intReady = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.cancel = threading.Event()

    @pyqtSlot()
    def _search_cast_(self):
        receiver = None
        try:
            receiver = receiver_for(self.settings)
            receiver.initialize_cast(cancel=self.cancel)
            self.intReady.emit(receiver.available_devices)
        except Exception as exc:
            self.failed.emit(str(exc))
            self.intReady.emit([])
        finally:
            try:
                if receiver is not None:
                    receiver.close()
            finally:
                self.finished.emit()


class Player(QObject):
    pcastfinished = pyqtSignal()
    pcastready = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.session = None
        self.commands = queue.Queue()
        self.stop_requested = False

    def prepare(self, settings):
        self.commands = queue.Queue()
        self.stop_requested = False
        self.session = CastSession(settings)

    def stop(self):
        self.stop_requested = True
        if self.session:
            self.session.cancel.set()

    @pyqtSlot()
    def _play_cast_(self):
        try:
            self.session.start()
            self.pcastready.emit("_play_cast_ success")
            while not self.session.cancel.wait(.25):
                self.session.check()
                while not self.commands.empty():
                    action, value = self.commands.get_nowait()
                    if action == "volume":
                        self.session.receiver.set_volume(value)
        except Exception as exc:
            self.pcastready.emit(str(exc))
        finally:
            if self.session:
                self.session.close()
            self.pcastfinished.emit()


url = "https://api.github.com/repos/Ayylmao13337/mkchromecast2.0/releases/latest"


class Updater(QObject):
    upcastfinished = pyqtSignal()
    updateready = pyqtSignal(str)

    @pyqtSlot()
    def _updater_(self):
        try:
            response = requests.get(url, timeout=(5, 10))
            if response.status_code == 404:
                self.updateready.emit("False")
                return
            response.raise_for_status()
            version = response.json()["tag_name"]
            self.updateready.emit(version if Version(version.lstrip("v")) > Version(__version__) else "False")
        except (requests.RequestException, ValueError, KeyError, InvalidVersion):
            self.updateready.emit("error1")
        finally:
            self.upcastfinished.emit()
