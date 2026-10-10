import io
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch, Mock

from mkchromecast import cli, diagnostics, screens, video
from mkchromecast.pipeline_builder import Video
from tools.benchmark_screencast import settings_for
from tests.test_video import _make_stub_mkcc


XRANDR = '''Screen 0: minimum 8 x 8, current 3840 x 1200, maximum 32767 x 32767
HDMI-0 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis)
   1920x1080 119.88* 60.00
DP-0 connected 1920x1200+1920+0 (normal left inverted right x axis y axis)
DP-1 connected (normal left inverted right x axis y axis)
DP-2 disconnected (normal left inverted right x axis y axis)
'''


class ScreenTests(unittest.TestCase):
    def test_two_monitors_and_inactive_outputs(self):
        found = screens.parse_xrandr(XRANDR)
        self.assertEqual([s['id'] for s in found], ['HDMI-0', 'DP-0'])
        self.assertEqual(screens.choose_screen(found, 'primary')['id'], 'HDMI-0')
        self.assertEqual(screens.choose_screen(found, 'DP-0')['x'], 1920)
        with self.assertRaisesRegex(ValueError, 'Available IDs'):
            screens.choose_screen(found, 'not-connected')

    def test_secondary_screen_captures_full_area_and_scales_output(self):
        with patch.object(screens, 'list_screens', return_value=screens.parse_xrandr(XRANDR)):
            selected = screens.X11ScreenSelection('DP-0', ':2')
        settings = settings_for()
        settings.display = ':2'
        settings.x11_capture = selected.geometry
        command = Video(settings).command
        self.assertIn(':2+1920,0', command)
        self.assertEqual(command[command.index('-s') + 1], '1920x1200')
        self.assertIn('scale=1280:720', command[command.index('-vf') + 1])

    def test_geometry_change_stops_capture(self):
        before = screens.parse_xrandr(XRANDR)
        after = screens.parse_xrandr(XRANDR.replace('1920x1200+1920+0', '1280x720+1920+0'))
        with patch.object(screens, 'list_screens', side_effect=[before, after]):
            selected = screens.X11ScreenSelection('DP-0')
            selected._next_check = 0
            with self.assertRaisesRegex(ValueError, 'restart screen sharing'):
                selected.check()

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_full_tall_screen_gets_side_borders_not_cropped(self):
        settings = settings_for(size='720p')
        settings.x11_capture = (1920, 0, 1920, 1200)
        command = Video(settings).command
        scale = command[command.index('-vf') + 1]
        frame = subprocess.run([
            'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=1920x1200',
            '-vf', scale, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1',
        ], capture_output=True, check=True, timeout=10).stdout
        self.assertEqual(len(frame), 1280 * 720 * 3)
        def pixel(x, y):
            offset = (y * 1280 + x) * 3
            return frame[offset:offset + 3]
        self.assertEqual(pixel(0, 360), b'\0\0\0')
        self.assertGreater(pixel(100, 360)[0], 240)
        self.assertEqual(pixel(1279, 360), b'\0\0\0')

    def test_explicit_display_is_forwarded_without_shell(self):
        with patch.object(screens, 'capture_backend', return_value='x11'), patch.object(
                screens.subprocess, 'run', return_value=Mock(stdout=XRANDR)) as run:
            screens.list_screens('auto', ':7')
        self.assertEqual(run.call_args.args[0], ['xrandr', '--current', '--display', ':7'])
        self.assertEqual(run.call_args.kwargs['timeout'], 3)

    def test_wayland_does_not_probe_xrandr(self):
        with patch.object(screens, 'capture_backend', return_value='wayland'), patch.object(
                screens.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'portal picker'):
                screens.list_screens()
            run.assert_not_called()

    def test_x11_selection_is_wired_to_server_health(self):
        settings = _make_stub_mkcc()
        settings.screen = 'DP-0'
        settings.resolution = '1080p'
        with patch.object(video.screencast_wayland, 'is_wayland_session', return_value=False), patch.object(
                screens, 'list_screens', return_value=screens.parse_xrandr(XRANDR)), patch.object(
                video.stream_infra.FlaskServer, 'init_video') as init:
            video._flask_init(settings)
        self.assertIn(':0+1920,0', init.call_args.kwargs['command'])
        self.assertTrue(callable(init.call_args.kwargs['health_check']))

    def test_list_cli_does_not_initialize_cast_or_settings(self):
        with patch.object(screens, 'list_screens', return_value=screens.parse_xrandr(XRANDR)), patch.object(
                cli, 'Mkchromecast') as settings, patch('mkchromecast.session.CastSession') as cast, patch(
                'sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(cli.main(['--list-screens']), 0)
        settings.assert_not_called()
        cast.assert_not_called()
        self.assertIn('DP-0', output.getvalue())

    def test_diagnose_cli_is_read_only_and_reports_failure(self):
        report = {'checks': [{'name': 'test', 'ok': False}]}
        with patch.object(diagnostics, 'collect', return_value=report), patch.object(cli, 'Mkchromecast') as settings, patch(
                'mkchromecast.session.CastSession') as cast, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(cli.main(['--diagnose', '--capture-backend', 'cinnamon']), 1)
        self.assertEqual(json.loads(output.getvalue()), report)
        settings.assert_not_called()
        cast.assert_not_called()

    def test_diagnostics_missing_tools_does_not_start_processes(self):
        with patch.object(diagnostics.platform, 'system', return_value='Linux'), patch.object(
                screens, 'capture_backend', return_value='x11'), patch.object(
                diagnostics.shutil, 'which', return_value=None), patch.object(
                screens, 'list_screens', side_effect=ValueError('No display')), patch.object(
                diagnostics.subprocess, 'run') as run:
            report = diagnostics.collect()
        self.assertFalse(next(c['ok'] for c in report['checks'] if c['name'] == 'ffmpeg'))
        run.assert_not_called()

    def test_cinnamon_diagnostics_checks_shm_not_pipewire(self):
        with patch.object(diagnostics.platform, 'system', return_value='Linux'), patch.object(
                screens, 'capture_backend', return_value='cinnamon'), patch.object(
                diagnostics.shutil, 'which', return_value='/bin/tool'), patch.object(
                screens, 'list_screens', return_value=[{'id': '0'}]), patch.object(
                diagnostics.subprocess, 'run', return_value=Mock(returncode=0, stdout='[]')) as run:
            report = diagnostics.collect('cinnamon')
        names = {check['name'] for check in report['checks']}
        self.assertIn('gst:shmsrc', names)
        self.assertNotIn('gst:pipewiresrc', names)
        self.assertTrue(all(call.args[0][0] in {'gst-inspect-1.0', 'pactl'} for call in run.call_args_list))
