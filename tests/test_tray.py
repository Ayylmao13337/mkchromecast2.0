import importlib.util
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PyQt5'), 'Optional tray dependency missing')
class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}))
        self.enterContext(patch('platform.system', return_value='Linux'))
        from mkchromecast import Mkchromecast, _arg_parsing
        self.settings = Mkchromecast(_arg_parsing.Parser.parse_args(['--tray']))

    def test_preferences_reset_and_lossless_bitrate(self):
        from mkchromecast.preferences import preferences
        widget = preferences(1, self.settings)
        self.addCleanup(widget.close)
        widget.onActivatedcc('flac')
        self.assertEqual('None', widget.qcbitrate.currentText())
        widget.onActivatedbt('None')
        widget.reset_configuration()
        self.assertEqual('mp3', widget.config.codec)
        self.assertEqual('mp3', widget.qccodec.currentText())
        self.assertEqual('192', widget.qcbitrate.currentText())

    def test_tray_volume_accepts_float_receiver_level(self):
        from mkchromecast.systray import menubar
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        window.cast = Mock()
        window.cast.status.volume_level = .37
        with patch.object(window._play_thread, 'isRunning', return_value=True):
            window.volume_cast()
            self.assertEqual(37, window.sl.value())
            window.sl.close()

    def test_search_finishes_even_if_adapter_creation_fails(self):
        from mkchromecast.tray_threading import Search
        worker = Search(self.settings)
        finished, errors = [], []
        worker.finished.connect(lambda: finished.append(True))
        worker.failed.connect(errors.append)
        with patch('mkchromecast.tray_threading.receiver_for', side_effect=RuntimeError('fixture')):
            worker._search_cast_()
        self.assertEqual([True], finished)
        self.assertEqual(['fixture'], errors)

    def test_control_panel_screen_settings_reach_session(self):
        from mkchromecast.systray import menubar
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        panel = window.panel
        panel.mode.setCurrentIndex(1)
        panel.backend.setCurrentIndex(1)
        panel.screen.addItem('Second monitor', '1')
        panel.screen.setCurrentIndex(1)
        panel.latency.setChecked(True)
        from types import SimpleNamespace
        device = SimpleNamespace(id='receiver-id', name='Living room')
        with patch.object(window._player, 'prepare') as prepare, patch.object(window._play_thread, 'start'):
            window._start_device(device)
        settings = prepare.call_args.args[0]
        self.assertTrue(settings.screencast)
        self.assertEqual('cinnamon', settings.capture_backend)
        self.assertEqual('1', settings.screen)
        self.assertTrue(settings.low_latency)
        self.assertEqual('receiver-id', settings.device_id)
        self.assertFalse(panel.options.isEnabled())
        window._play_finished()
        self.assertTrue(panel.options.isEnabled())
        panel.mode.setCurrentIndex(0)
        args = panel.apply_args(self.settings.args)
        self.assertFalse(args.video)
        self.assertFalse(args.low_latency)
        self.assertIsNone(args.screen)
        self.assertEqual('auto', args.capture_backend)
        self.assertFalse(self.settings.args.screencast)

    def test_diagnostics_updates_screens_without_starting_session(self):
        import json
        from mkchromecast.systray import menubar
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        panel = window.panel
        report = {'scope': 'Local checks only', 'checks': [
            {'name': 'ffmpeg', 'ok': False, 'detail': 'Install ffmpeg'}],
            'screens': [{'id': 'DP-0', 'width': 1920, 'height': 1200}]}
        with patch.object(panel, 'process') as process, patch.object(window._player, 'prepare') as prepare:
            process.state.return_value = 0
            panel.diagnose()
            process.start.assert_called_once()
            process.readAllStandardOutput.return_value = json.dumps(report).encode()
            panel._diagnosed()
            self.assertIn('FAIL', panel.report.toPlainText())
            self.assertGreaterEqual(panel.screen.findData('DP-0'), 0)
            prepare.assert_not_called()

    def test_screen_mode_not_offered_on_macos(self):
        from mkchromecast.systray import menubar
        self.settings.platform = 'Darwin'
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        self.assertEqual(1, window.panel.mode.count())

    def test_gui_preferences_survive_restart_and_invalid_fps_is_safe(self):
        from mkchromecast.systray import menubar
        from mkchromecast import gui_settings
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        panel = window.panel
        panel.mode.setCurrentIndex(1)
        panel.backend.setCurrentIndex(1)
        panel.screen.addItem('External', '1')
        panel.screen.setCurrentIndex(1)
        panel.latency.setChecked(True)
        panel.fps.setValue(30)
        saved = gui_settings.load('Linux')
        self.assertEqual('1', saved['screen'])
        saved['fps'] = 'corrupt'
        gui_settings.save('Linux', saved)
        other = menubar(self.settings)
        self.addCleanup(other.tray.hide)
        self.addCleanup(other.close)
        self.assertEqual('cinnamon', other.panel.backend.currentData())
        self.assertEqual('1', other.panel.screen.currentData())
        self.assertTrue(other.panel.latency.isChecked())
        self.assertEqual(25, other.panel.fps.value())

    def test_retry_waits_for_current_session_to_stop(self):
        from types import SimpleNamespace
        from mkchromecast.systray import menubar
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        device = SimpleNamespace(id='id', name='TV')
        window._last_device = device
        with patch.object(window._play_thread, 'isRunning', return_value=True), patch.object(
                window._player, 'stop') as stop, patch.object(window, '_start_device') as start:
            window.retry_connection()
            stop.assert_called_once()
            start.assert_not_called()
            window._play_finished()
            start.assert_called_once_with(device)

    def test_missing_saved_screen_is_not_silently_replaced(self):
        import json
        from mkchromecast.systray import menubar
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        panel = window.panel
        panel.screen.addItem('Old monitor', 'gone')
        panel.screen.setCurrentIndex(panel.screen.count() - 1)
        panel._checked_backend = panel.backend.currentData()
        with patch.object(panel, 'process') as process:
            process.readAllStandardOutput.return_value = json.dumps(
                {'scope': 'Local', 'checks': [], 'screens': []}).encode()
            panel._diagnosed()
        self.assertEqual('gone', panel.screen.currentData())
        self.assertIn('unavailable', panel.screen.currentText())

    def test_connection_notice_keeps_retry_available(self):
        from mkchromecast.systray import menubar
        window = menubar(self.settings)
        self.addCleanup(window.tray.hide)
        self.addCleanup(window.close)
        window.connection_changed(False)
        self.assertIn('lost', window.panel.status.text())
        self.assertTrue(window.panel.retry.isEnabled())
        window.connection_changed(True)
        self.assertIn('restored', window.panel.status.text())
