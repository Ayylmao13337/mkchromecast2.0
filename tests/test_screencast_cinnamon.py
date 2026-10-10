import json
import ctypes
import ctypes.util
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch, Mock

from mkchromecast import Mkchromecast, _arg_parsing, video
from mkchromecast import screencast_cinnamon as capture
from tests.test_video import _make_stub_mkcc


class CinnamonTests(unittest.TestCase):
    def test_cli_rejects_unsupported_combinations(self):
        for extra in ([], ['--video', '--screencast', '--fps', '29.97'],
                      ['--video', '--screencast', '--fps', '61'],
                      ['--video', '--screencast', '--vcodec', 'h264_nvenc']):
            with self.subTest(extra=extra), patch('platform.system', return_value='Linux'):
                with self.assertRaises(ValueError):
                    Mkchromecast(_arg_parsing.Parser.parse_args(['--capture-backend', 'cinnamon', *extra]))

    def test_cli_accepts_opt_in(self):
        with patch('platform.system', return_value='Linux'):
            settings = Mkchromecast(_arg_parsing.Parser.parse_args(
                ['--video', '--screencast', '--capture-backend', 'cinnamon']))
        self.assertEqual(settings.capture_backend, 'cinnamon')

    def test_preflight_rejects_wrong_desktop_and_wayland(self):
        for desktop, wayland in [('GNOME', False), ('X-Cinnamon', True)]:
            with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': desktop}), patch.object(
                    capture.screencast_wayland, 'is_wayland_session', return_value=wayland):
                with self.assertRaises(capture.CinnamonError):
                    capture.preflight()

    def test_missing_dependency_is_actionable(self):
        with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'X-Cinnamon'}), patch.object(
                capture.screencast_wayland, 'is_wayland_session', return_value=False), patch.object(
                capture.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(capture.CinnamonError, 'gstreamer1.0-plugins-bad'):
                capture.preflight()

    def test_eval_preserves_strings_and_reports_errors(self):
        payload = {'value': 'false, true, "quoted"'}
        with patch.object(capture.subprocess, 'run', return_value=Mock(
                stdout='(true, ' + repr(json.dumps(payload)) + ')')) as run:
            self.assertEqual(payload, capture._evaluate('1'))
            self.assertNotIn('shell', run.call_args.kwargs)
        for output in ("(false, '{}')", '(true, ' + repr('{"error":"busy"}') + ')', 'invalid'):
            with patch.object(capture.subprocess, 'run', return_value=Mock(stdout=output)):
                with self.assertRaises(capture.CinnamonError):
                    capture._evaluate('1')

    def test_partial_start_is_stopped_and_private_directory_removed(self):
        session = capture.CinnamonCaptureSession(25)
        paths = []
        def call(action, **kwargs):
            if action == 'start':
                paths.append(Path(session._directory.name))
                self.assertEqual(paths[-1].stat().st_mode & 0o777, 0o700)
                self.assertIn('perms=384', kwargs['pipeline'])
                raise capture.CinnamonError('fixture')
        with patch.object(session, '_call', side_effect=call) as calls:
            with self.assertRaisesRegex(capture.CinnamonError, 'fixture'):
                session.open()
            session.close()
        self.assertEqual([c.args[0] for c in calls.call_args_list], ['start', 'stop'])
        self.assertFalse(paths[0].exists())

    def test_dbus_error_shows_stderr_without_dumping_script(self):
        error = subprocess.CalledProcessError(1, ['gdbus', 'PRIVATE_SCRIPT'],
                                               stderr='Error: service unavailable')
        with patch.object(capture.subprocess, 'run', side_effect=error):
            with self.assertRaises(capture.CinnamonError) as caught:
                capture._evaluate('PRIVATE_SCRIPT')
        self.assertIn('service unavailable', str(caught.exception))
        self.assertNotIn('PRIVATE_SCRIPT', str(caught.exception))
        with patch.object(capture.subprocess, 'run', side_effect=subprocess.TimeoutExpired(
                ['gdbus', 'PRIVATE_SCRIPT'], 5)):
            with self.assertRaisesRegex(capture.CinnamonError, '^Cinnamon D-Bus call timed out after 5 seconds$'):
                capture._evaluate('PRIVATE_SCRIPT')

    def test_real_glib_parses_complete_script_without_changing_it(self):
        library = ctypes.util.find_library('glib-2.0')
        if not library:
            self.skipTest('GLib is not installed')
        lib = ctypes.CDLL(library)
        lib.g_variant_parse.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        lib.g_variant_parse.restype = ctypes.c_void_p
        lib.g_variant_get_string.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.g_variant_get_string.restype = ctypes.c_char_p
        lib.g_variant_unref.argtypes = [ctypes.c_void_p]
        lib.g_error_free.argtypes = [ctypes.c_void_p]
        session = capture.CinnamonCaptureSession(25)
        with patch.object(capture, '_evaluate') as evaluate:
            session._call('start', fps=25, pipeline='shmsink socket-path="/tmp/quoted path/frames"')
        script = evaluate.call_args.args[0]
        with patch.object(capture.subprocess, 'run', return_value=Mock(stdout="(true, 'true')")) as run:
            capture._evaluate(script)
        argument = run.call_args.args[0][-1]
        error = ctypes.c_void_p()
        value = lib.g_variant_parse(b's', argument.encode(), None, None, ctypes.byref(error))
        try:
            self.assertTrue(value, 'gdbus argument must be valid GVariant string syntax')
            self.assertEqual(lib.g_variant_get_string(value, None).decode(), script)
        finally:
            if value:
                lib.g_variant_unref(value)
            if error:
                lib.g_error_free(error)

    def test_heartbeat_failure_is_not_silenced(self):
        session = capture.CinnamonCaptureSession(25)
        with patch.object(session, '_call', side_effect=capture.CinnamonError('lost recorder')):
            with self.assertRaisesRegex(capture.CinnamonError, 'lost recorder'):
                session.check()

    def test_integration_owns_capture_and_reuses_stream_pipeline(self):
        settings = _make_stub_mkcc()
        settings.capture_backend = 'cinnamon'
        settings.capture_device = 'owned-sink.monitor'
        settings.resolution = None
        session = Mock()
        session.open.return_value = '/private/frames'
        with patch.object(capture, 'CinnamonCaptureSession', return_value=session), patch.object(
                video.stream_infra.FlaskServer, 'init_video') as init:
            video._flask_init(settings)
        args = init.call_args.kwargs
        self.assertIn('shmsrc', args['command'])
        self.assertNotIn('x11grab', args['command'])
        self.assertIn('device=owned-sink.monitor', args['command'])
        self.assertEqual(args['cleanup'], session.close)
        self.assertEqual(args['health_check'], session.check)

    def test_init_failure_closes_capture(self):
        settings = _make_stub_mkcc()
        settings.capture_backend = 'cinnamon'
        session = Mock()
        session.open.side_effect = capture.CinnamonError('fixture')
        with patch.object(capture, 'CinnamonCaptureSession', return_value=session):
            with self.assertRaises(capture.CinnamonError):
                video._flask_init(settings)
        session.close.assert_called_once()

    @unittest.skipUnless(shutil.which('node'), 'Node needed for compositor lifecycle harness')
    def test_javascript_lifecycle(self):
        subprocess.run(['node', str(Path(__file__).with_name('cinnamon_capture_harness.js'))],
                       check=True, timeout=10, capture_output=True)
