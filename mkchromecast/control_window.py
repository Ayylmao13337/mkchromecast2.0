"""Qt controls for the existing tray/session controller."""
import copy
import json
import sys

from PyQt5 import QtCore, QtWidgets

from mkchromecast import gui_settings
from mkchromecast.screencast_wayland import is_wayland_session


class ControlPanel(QtWidgets.QWidget):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.process = QtCore.QProcess(self)
        self.process.finished.connect(self._diagnosed)
        self.process.errorOccurred.connect(self._diagnostic_error)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QtWidgets.QLabel("MKChromecast 2.0")
        font = title.font()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        self.status = QtWidgets.QLabel("Choose a device, then start streaming.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.status)
        row = QtWidgets.QHBoxLayout()
        self.devices = QtWidgets.QComboBox()
        self.devices.setMinimumContentsLength(24)
        self.devices.setAccessibleName("Streaming device")
        row.addWidget(self.devices, 1)
        self.search = QtWidgets.QPushButton("Find devices")
        self.search.clicked.connect(controller.search_cast)
        row.addWidget(self.search)
        layout.addLayout(row)
        self.options = QtWidgets.QGroupBox("Stream settings")
        form = QtWidgets.QFormLayout(self.options)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItem("Audio", False)
        if controller.settings.platform == "Linux" and controller.settings.receiver != "sonos":
            self.mode.addItem("Screen and audio", True)
        form.addRow("Share", self.mode)
        self.backend = QtWidgets.QComboBox()
        self.backend.addItem("Automatic (X11 / Wayland)", "auto")
        self.backend.addItem("Cinnamon (experimental)", "cinnamon")
        form.addRow("Capture", self.backend)
        self.screen = QtWidgets.QComboBox()
        form.addRow("Screen", self.screen)
        self.resolution = QtWidgets.QComboBox()
        self.resolution.addItems(["720p", "1080p"])
        self.resolution.setCurrentText("1080p")
        form.addRow("Resolution", self.resolution)
        self.fps = QtWidgets.QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(25)
        form.addRow("Frames per second", self.fps)
        self.latency = QtWidgets.QCheckBox("Reduce streaming delay")
        self.latency.setToolTip("Smaller video fragments. Chromecast buffering still adds delay.")
        form.addRow("Low latency", self.latency)
        self.audio = QtWidgets.QComboBox()
        self.audio.addItem("Application routing (audio mixer)", None)
        self.audio.setEnabled(controller.settings.platform == "Linux")
        form.addRow("Audio source", self.audio)
        layout.addWidget(self.options)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.backend.currentIndexChanged.connect(self._reset_screens)
        self._reset_screens()
        self._mode_changed()
        row = QtWidgets.QHBoxLayout()
        self.start = QtWidgets.QPushButton("Start streaming")
        self.start.setEnabled(False)
        self.start.clicked.connect(self._start)
        self.stop = QtWidgets.QPushButton("Stop")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(controller.stop_cast)
        row.addWidget(self.start)
        row.addWidget(self.stop)
        self.retry = QtWidgets.QPushButton("Retry connection")
        self.retry.setEnabled(False)
        self.retry.clicked.connect(controller.retry_connection)
        row.addWidget(self.retry)
        layout.addLayout(row)
        self.check = QtWidgets.QPushButton("Check setup / refresh screens")
        self.check.clicked.connect(self.diagnose)
        layout.addWidget(self.check)
        self.report = QtWidgets.QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("Local checks appear here. No recording or receiver connection is started.")
        layout.addWidget(self.report)
        actions = QtWidgets.QHBoxLayout()
        for label, callback in (("Audio preferences", controller.preferences_show),
                                ("Volume", controller.volume_cast),
                                ("Quit", controller.exit_all)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        footer = QtWidgets.QLabel("Closing this window keeps MKChromecast in the system tray. Use Quit to exit.")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self._restore()
        for combo in (self.mode, self.backend, self.screen, self.resolution, self.audio):
            combo.currentIndexChanged.connect(self._save)
        self.fps.valueChanged.connect(self._save)
        self.latency.toggled.connect(self._save)

    def _restore(self):
        saved = gui_settings.load(self.controller.settings.platform)
        for widget, key in ((self.mode, "mode"), (self.backend, "backend")):
            index = widget.findData(saved.get(key))
            if index >= 0:
                widget.setCurrentIndex(index)
        if saved.get("resolution") in ("720p", "1080p"):
            self.resolution.setCurrentText(saved["resolution"])
        fps = saved.get("fps", 25)
        self.fps.setValue(fps if type(fps) is int and 1 <= fps <= 60 else 25)
        self.latency.setChecked(saved.get("latency") is True)
        for widget, key in ((self.screen, "screen"), (self.audio, "audio")):
            value = saved.get(key)
            if isinstance(value, str) and widget.findData(value) < 0:
                widget.addItem(value + " (saved; refresh to verify)", value)
            index = widget.findData(value)
            if index >= 0:
                widget.setCurrentIndex(index)

    def _save(self, *_):
        try:
            gui_settings.save(self.controller.settings.platform, dict(
                mode=self.mode.currentData(), backend=self.backend.currentData(),
                screen=self.screen.currentData(), audio=self.audio.currentData(),
                resolution=self.resolution.currentText(), fps=self.fps.value(),
                latency=self.latency.isChecked()))
        except OSError as exc:
            self.report.setPlainText("Could not save settings: " + str(exc))

    def _reset_screens(self):
        self.screen.clear()
        portal = self.backend.currentData() == "auto" and is_wayland_session()
        self.screen.addItem("Choose when sharing starts" if portal else "Primary screen", None if portal else "primary")

    def _mode_changed(self):
        for widget in (self.backend, self.screen, self.resolution, self.fps, self.latency):
            widget.setEnabled(bool(self.mode.currentData()))

    def set_devices(self, devices):
        selected = self.devices.currentData()
        selected_id = getattr(selected, "id", None)
        self.devices.clear()
        for device in devices:
            self.devices.addItem(device.name, device)
            if device.id == selected_id:
                self.devices.setCurrentIndex(self.devices.count() - 1)
        self.search.setEnabled(True)
        self.start.setEnabled(bool(devices) and not self.controller._play_thread.isRunning())
        self.status.setText("Choose a device, then start streaming." if devices else "No devices found. Check that both devices use the same network.")

    def apply_args(self, original):
        args = copy.copy(original)
        sharing = bool(self.mode.currentData())
        args.video = sharing
        args.screencast = sharing
        args.capture_backend = self.backend.currentData() if sharing else "auto"
        args.screen = self.screen.currentData() if sharing else None
        args.low_latency = sharing and self.latency.isChecked()
        if sharing:
            args.fps = str(self.fps.value())
            args.resolution = self.resolution.currentText()
            args.vcodec = "libx264"
            args.alsa_device = None
        return args

    def _start(self):
        device = self.devices.currentData()
        if device is not None:
            self.controller.clicked_cc(device)

    def set_running(self, running, message=None):
        self.options.setEnabled(not running)
        self.devices.setEnabled(not running)
        self.start.setEnabled(not running and self.devices.count() > 0)
        self.stop.setEnabled(running)
        if message:
            self.status.setText(message)

    def diagnose(self):
        if self.process.state() != QtCore.QProcess.NotRunning:
            return
        self._checked_backend = self.backend.currentData()
        args = ["-m", "mkchromecast.cli", "--diagnose", "--capture-backend", self._checked_backend]
        if self.controller.settings.args.display:
            args.extend(["--display", self.controller.settings.args.display])
        self.check.setEnabled(False)
        self.report.setPlainText("Checking local dependencies and screens…")
        self.process.start(sys.executable, args)

    def _diagnostic_error(self, error):
        if error == QtCore.QProcess.FailedToStart:
            self.report.setPlainText("Could not start diagnostics: " + self.process.errorString())
            self.check.setEnabled(True)

    def _diagnosed(self, *_):
        self.check.setEnabled(True)
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        try:
            report = json.loads(raw)
            lines = [report["scope"], ""]
            for check in report["checks"]:
                state = "OK" if check["ok"] is True else "FAIL" if check["ok"] is False else "NOT TESTED"
                lines.append(f"{state} — {check['name']}: {check['detail']}")
            self.report.setPlainText("\n".join(lines))
            audio = self.audio.currentData()
            self.audio.blockSignals(True)
            self.audio.clear()
            self.audio.addItem("Application routing (audio mixer)", None)
            for source in report.get("audio_sources", []):
                self.audio.addItem(source["description"], source["name"])
            index = self.audio.findData(audio)
            if index < 0 and audio:
                self.audio.addItem(audio + " (unavailable — choose another)", audio)
                index = self.audio.count() - 1
            self.audio.setCurrentIndex(max(index, 0))
            self.audio.blockSignals(False)
            if self.backend.currentData() == self._checked_backend:
                selected = self.screen.currentData()
                self.screen.blockSignals(True)
                self._reset_screens()
                for screen in report.get("screens", []):
                    self.screen.addItem(f"{screen['id']} — {screen['width']} × {screen['height']}", screen['id'])
                index = self.screen.findData(selected)
                if index < 0 and selected:
                    self.screen.addItem(selected + " (unavailable — choose another)", selected)
                    index = self.screen.count() - 1
                if index >= 0:
                    self.screen.setCurrentIndex(index)
                self.screen.blockSignals(False)
        except (ValueError, KeyError, TypeError):
            error = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
            self.report.setPlainText(error or raw or "Diagnostics stopped before returning a report.")
