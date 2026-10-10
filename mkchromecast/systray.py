# This file is part of mkchromecast.
# brew install pyqt5 --with-python --without-python3

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
from urllib.request import urlopen

import mkchromecast
from mkchromecast import cast
from mkchromecast import colors
from mkchromecast import config
from mkchromecast import preferences
from mkchromecast import tray_threading
from mkchromecast.audio_devices import inputint, outputint
from mkchromecast.pulseaudio import remove_sink
from mkchromecast.utils import del_tmp, checkmktmp
from mkchromecast.version import __version__

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QThread, Qt
from PyQt5.QtWidgets import QWidget, QMessageBox

"""
We verify that pychromecast is installed
"""
try:
    import pychromecast

    chromecast = True
except ImportError:
    chromecast = False


class menubar(QtWidgets.QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.app = QtWidgets.QApplication.instance()
        self.app.setQuitOnLastWindowClosed(False)
        self.cast = None
        self.stopped = False
        self.played = False
        self.pcastfailed = False
        self.available_devices = []
        self._pending_device = None
        self._exiting = False
        self.scale_factor = 1
        self.config = config.Config(platform=settings.platform, read_only=True, debug=settings.debug)
        self.config.load_and_validate()
        self.google = {"black": "google", "blue": "google_b", "white": "google_w"}
        self.google_working = {"black": "google_working", "blue": "google_working_b", "white": "google_working_w"}
        self.google_nodev = {"black": "google_nodev", "blue": "google_nodev_b", "white": "google_nodev_w"}
        self._search = tray_threading.Search(settings)
        self._search_thread = QThread(self)
        self._search.moveToThread(self._search_thread)
        self._search.intReady.connect(self.onIntReady)
        self._search.failed.connect(self.show_error)
        self._search.finished.connect(self._search_thread.quit, Qt.DirectConnection)
        self._search_thread.started.connect(self._search._search_cast_)
        self._player = tray_threading.Player()
        self._play_thread = QThread(self)
        self._player.moveToThread(self._play_thread)
        self._player.pcastready.connect(self.pcastready)
        self._player.pcastfinished.connect(self._play_thread.quit, Qt.DirectConnection)
        self._play_thread.started.connect(self._player._play_cast_)
        self._play_thread.finished.connect(self._play_finished)
        self._updater = tray_threading.Updater()
        self._updater_thread = QThread(self)
        self._updater.moveToThread(self._updater_thread)
        self._updater.updateready.connect(self.updateready)
        self._updater.upcastfinished.connect(self._updater_thread.quit, Qt.DirectConnection)
        self._updater_thread.started.connect(self._updater._updater_)
        self.icon = QtGui.QIcon(self._icon_path(self.google[self.config.colors]))
        from mkchromecast.control_window import ControlPanel
        self.panel = ControlPanel(self)
        self.setCentralWidget(self.panel)
        self.setWindowTitle("MKChromecast 2.0")
        self.resize(600, 720)
        self.createUI()

    def _icon_path(self, name):
        from pathlib import Path
        extension = ".icns" if self.settings.platform == "Darwin" else ".png"
        return str(Path(__file__).parent / "resources" / (name + extension))

    def show_controls(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            self.exit_all()
            event.ignore()

    def show_error(self, message):
        self.panel.status.setText(message)
        if not self._exiting:
            self.tray.showMessage("Mkchromecast", message, QtWidgets.QSystemTrayIcon.Warning)

    def createUI(self):
        self.tray = QtWidgets.QSystemTrayIcon(self.icon)
        self.menu = QtWidgets.QMenu()
        self.ag = QtWidgets.QActionGroup(self)
        self.search_menu()
        self.separator_menu()
        self.populating_menu()
        self.separator_menu()
        self.stop_menu()
        self.volume_menu()
        self.resetaudio_menu()
        self.separator_menu()
        self.preferences_menu()
        self.update_menu()
        self.about_menu()
        self.exit_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        """
        This is for the search at launch
        """
        if self.config.search_at_launch:
            self.search_cast()


    def search_menu(self):
        self.menu.addAction("Open MKChromecast", self.show_controls)
        self.SearchAction = self.menu.addAction("Search For Media " "Streaming Devices")
        self.SearchAction.triggered.connect(self.search_cast)

    def stop_menu(self):
        self.StopCastAction = self.menu.addAction("Stop Streaming")
        self.StopCastAction.triggered.connect(self.stop_cast)

    def volume_menu(self):
        self.VolumeCastAction = self.menu.addAction("Volume")
        self.VolumeCastAction.triggered.connect(self.volume_cast)

    def separator_menu(self):
        self.menu.addSeparator()

    def populating_menu(self):
        if self.SearchAction.triggered.connect is True:
            self.cast_list()

    def resetaudio_menu(self):
        self.ResetAudioAction = self.menu.addAction("Reset Audio")
        self.ResetAudioAction.triggered.connect(self.reset_audio)

    def preferences_menu(self):
        self.preferencesAction = self.menu.addAction("Preferences...")
        self.preferencesAction.triggered.connect(self.preferences_show)

    def update_menu(self):
        self.updateAction = self.menu.addAction("Check For Updates...")
        self.updateAction.triggered.connect(self.update_show)

    def about_menu(self):
        self.AboutAction = self.menu.addAction("About Mkchromecast")
        self.AboutAction.triggered.connect(self.about_show)

    def exit_menu(self):
        exitAction = self.menu.addAction("Quit")
        exitAction.triggered.connect(self.exit_all)

    """
    These are methods for interacting with the mkchromecast objects
    """

    def onIntReady(self, available_devices: list):
        print("available_devices received")
        self.available_devices = available_devices
        self.panel.set_devices(available_devices)
        self.cast_list()

    def _set_generic_icon(self, icon_set):
        self.tray.setIcon(QtGui.QIcon(self._icon_path(icon_set[self.config.colors])))

    def set_icon_working(self):
        """docstring for fnamicon_working"""
        self._set_generic_icon(self.google_working)

    def set_icon_idle(self):
        """docstring for icon_idle"""
        self._set_generic_icon(self.google)

    def set_icon_nodev(self):
        """docstring for set_ic"""
        self._set_generic_icon(self.google_nodev)

    def search_cast(self):
        if self._search_thread.isRunning() or self._exiting:
            return
        self.set_icon_working()
        self.panel.search.setEnabled(False)
        self.panel.status.setText("Searching for devices…")
        self._search.cancel.clear()
        self._search_thread.start()

    def cast_list(self):
        self.set_icon_idle()

        if not self.available_devices:
            self.menu.clear()
            for old_action in self.ag.actions():
                self.ag.removeAction(old_action)
                old_action.deleteLater()
            self.search_menu()
            self.separator_menu()
            self.NodevAction = self.menu.addAction("No Streaming Devices Found.")
            self.set_icon_nodev()

            self.separator_menu()
            self.stop_menu()
            self.volume_menu()
            self.resetaudio_menu()
            self.separator_menu()
            self.preferences_menu()
            self.update_menu()
            self.about_menu()
            self.exit_menu()
        else:
            if self.config.notifications:
                self.tray.showMessage("Mkchromecast", "Media streaming devices found")
            self.menu.clear()
            for old_action in self.ag.actions():
                self.ag.removeAction(old_action)
                old_action.deleteLater()
            self.search_menu()
            self.separator_menu()
            print("Available Media Streaming Devices", self.available_devices)
            for index, device in enumerate(self.available_devices):
                # TODO(xsdg): self.ag isn't actually referenced from anywhere,
                # so just make it local.
                action = self.ag.addAction(
                    (QtWidgets.QAction(device.name, self, checkable=True))
                )

                # The receiver is a lambda function that passes clicked as
                # a boolean, and the clicked_item as an argument to the
                # self.clicked_cc() method. This last method, sets the correct
                # index and name of the chromecast to be used by
                # self.play_cast(). Credits to this question in stackoverflow:
                #
                # http://stackoverflow.com/questions/1464548/pyqt-qmenu-dynamically-populated-and-clicked
                receiver = lambda clicked, clicked_item=device: self.clicked_cc(
                    clicked_item
                )
                action.triggered.connect(receiver)

                self.menu.addAction(action)
            self.separator_menu()
            self.stop_menu()
            self.volume_menu()
            self.resetaudio_menu()
            self.separator_menu()
            self.preferences_menu()
            self.update_menu()
            self.about_menu()
            self.exit_menu()

    def clicked_cc(self, clicked_item):
        if self._exiting:
            return
        if self._play_thread.isRunning():
            self._pending_device = clicked_item
            self._player.stop()
            return
        self._start_device(clicked_item)

    def _start_device(self, device):
        try:
            args = self.panel.apply_args(self.settings.args)
            args.device_id = device.id
            args.name = None
            settings = mkchromecast.Mkchromecast(args)
            self._player.prepare(settings)
        except (Exception, SystemExit) as exc:
            self.show_error("Cannot start streaming: " + str(exc))
            return
        self.played = True
        self.stopped = False
        self.set_icon_working()
        self.panel.set_running(True, "Connecting to " + device.name + "…")
        self._play_thread.start()

    def pcastready(self, message):
        if message == "_play_cast_ success":
            self.cast = self._player.session.receiver.cast
            self.pcastfailed = False
            self.panel.status.setText("Streaming. Route application audio to the Mkchromecast device in your audio mixer.")
            self.set_icon_idle()
        else:
            self.pcastfailed = True
            self.set_icon_nodev()
            if not self._player.stop_requested:
                self.show_error(message)

    def _play_finished(self):
        self.cast = None
        self.played = False
        self.stopped = True
        self.panel.set_running(False, None if self.pcastfailed else "Streaming stopped.")
        self.set_icon_idle()
        if self._pending_device is not None and not self._exiting:
            device, self._pending_device = self._pending_device, None
            self._start_device(device)

    def stop_cast(self):
        self._pending_device = None
        self._player.stop()

    def volume_cast(self):
        if not self._play_thread.isRunning() or self.cast is None:
            return
        self.sl = QtWidgets.QSlider(Qt.Horizontal)
        self.sl.setRange(0, 100)
        self.sl.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        level = (round(self.cast.status.volume_level * 100)
                 if self.settings.receiver == "chromecast" else 20)
        self.sl.setValue(int(level))
        self.sl.valueChanged.connect(self.value_changed)
        self.sl.setWindowTitle("Device Volume")
        self.sl.resize(280, 70)
        self.sl.show()

    def value_changed(self, value):
        if self._play_thread.isRunning():
            self._player.commands.put(("volume", value / 100))

    def reset_audio(self):
        # The session restores only its own routing; do not unload other sessions.
        self.stop_cast()

    def preferences_show(self):
        self.p = preferences.preferences(self.scale_factor, self.settings)
        self.p.show()

    def updateready(self, message):
        print("update ready ?", message)
        updaterBox = QMessageBox()
        updaterBox.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        updaterBox.setIcon(QMessageBox.Information)
        # This option let you write rich text in pyqt5.
        updaterBox.setTextFormat(Qt.RichText)
        if message == "None":
            updaterBox.setText("No network connection detected!")
            updaterBox.setInformativeText(
                """
                    Verify that your computer is connected to your router,
                    and try again."""
            )
        elif message == "False":
            updaterBox.setText("<b>Your installation is up-to-date!</b>")
            updaterBox.setInformativeText(
                "<b>Mkchromecast</b> v"
                + __version__
                + " is currently the newest version available."
            )
        elif message == "error1":
            updaterBox.setText("Problems connecting to remote file server!")
            updaterBox.setInformativeText("""Try again later.""")
        else:
            updaterBox.setText("New version of Mkchromecast available!")
            download = '<a href="https://github.com/Ayylmao13337/mkchromecast2.0/releases/latest">'
            if self.settings.debug is True:
                print("Download URL:", download)
            updaterBox.setInformativeText(
                "You can " + download + "download it by clicking here</a>."
            )
        updaterBox.setStandardButtons(QMessageBox.Ok)
        updaterBox.exec_()

    def update_show(self):
        if not self._updater_thread.isRunning() and not self._exiting:
            self._updater_thread.start()

    def about_show(self):
        msgBox = QMessageBox()
        msgBox.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        self.about_icon = str(Path(__file__).with_name("resources") / "google.png")

        msgsettext = (
            '<center><img src="'
            + self.about_icon
            + '" "height="98" width="128" align="middle"> <br> <br>'
            + " <b>Mkchromecast</b> v"
            + __version__
        )
        msgBox.setText(msgsettext)
        msgBox.setInformativeText(
            """
        <p align='center'>
        <a href="http://mkchromecast.com/">Visit Mkchromecast's website.</a>
        <br>
        <br>
        <br>
        Created by: Muammar El Khatib.
        <br>
        <br>
        UX design: Claudia Vargas.
        <br>
        <br>
        <br>
        Copyright (c) 2017, Muammar El Khatib.
        <br>
        <br>
        This program comes with absolutely no warranty.
        <br>
        See the
        <a href=
        "https://github.com/muammar/mkchromecast/blob/master/LICENSE">
        MIT license</a> for details.
        </p>
                """
        )
        msgBox.exec_()

    def exit_all(self):
        self._exiting = True
        self.panel.process.kill()
        self._pending_device = None
        self._player.stop()
        self._search.cancel.set()
        self._await_shutdown()

    def _await_shutdown(self):
        if self.panel.process.state() != QtCore.QProcess.NotRunning or any(thread.isRunning() for thread in
               (self._play_thread, self._search_thread, self._updater_thread)):
            QtCore.QTimer.singleShot(100, self._await_shutdown)
        else:
            self.tray.hide()
            self.app.quit()

    def search_notification(self):
        self.tray.showMessage("Mkchromecast", "Searching for streaming devices")


def main(settings=None):
    settings = settings or mkchromecast.Mkchromecast()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = menubar(settings)
    window.show()
    signal.signal(signal.SIGINT, lambda *_: window.exit_all())
    signal.signal(signal.SIGTERM, lambda *_: window.exit_all())
    # Let Python service signals while Qt is idle.
    timer = QtCore.QTimer(window)
    timer.timeout.connect(lambda: None)
    timer.start(200)
    return app.exec_()
