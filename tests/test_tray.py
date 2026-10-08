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
