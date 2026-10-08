from functools import partial
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen, Request

from mkchromecast.stream_infra import FlaskServer, PipelineProcess
from mkchromecast.processes import PipelineError


def init_fixture(path):
    FlaskServer.init_video(8192, 'video/mp4', direct_file=path)


def fail_init():
    raise RuntimeError('fixture startup failure')


class HTTPTests(unittest.TestCase):
    def setUp(self):
        FlaskServer._app = None
        self.addCleanup(self.reset)

    def reset(self):
        FlaskServer.close()
        FlaskServer._app = None

    def test_head_does_not_start_encoder(self):
        FlaskServer.init_video(8192, 'video/mp4', command=['ffmpeg'])
        with patch('mkchromecast.stream_infra.OwnedPipeline') as process:
            response = FlaskServer._app.test_client().head('/stream')
            self.assertEqual(200, response.status_code)
            process.assert_not_called()

    def test_fd_forwarding_and_disconnect_cleanup(self):
        for fds in ((), [7]):
            with self.subTest(fds=fds):
                FlaskServer._app = None
                FlaskServer.init_video(8192, 'video/mp4', command=['ffmpeg'], pass_fds=fds)
                with patch('mkchromecast.stream_infra.OwnedPipeline') as process:
                    process.return_value.read.side_effect = [b'data', b'']
                    response = FlaskServer._app.test_client().get('/stream', buffered=False)
                    process.assert_called_once_with(['ffmpeg'], producer=None, pass_fds=fds)
                    response.close()
                    process.return_value.close.assert_called_once()
                    self.assertFalse(FlaskServer._active)

    def test_live_slot_is_released_and_second_client_is_rejected(self):
        FlaskServer.init_video(8192, 'video/mp4', command=[sys.executable, '-c', 'print("data")'])
        client = FlaskServer._app.test_client()
        first = client.get('/stream', buffered=False)
        self.assertEqual(503, client.get('/stream').status_code)
        first.close()
        second = client.get('/stream')
        self.assertEqual(200, second.status_code)
        second.close()

    def test_missing_encoder_returns_actionable_error(self):
        FlaskServer.init_video(8192, 'video/mp4', command=['mkchromecast-missing-fixture'])
        self.assertEqual(503, FlaskServer._app.test_client().get('/stream').status_code)
        self.assertIn('Required program', FlaskServer._errors.get_nowait())


class SpawnServerTests(unittest.TestCase):
    def test_real_http_head_and_range_and_port_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.mp4'
            path.write_bytes(b'0123456789')
            process = PipelineProcess(partial(init_fixture, str(path)), '127.0.0.1', 0, 'Linux')
            self.addCleanup(process.close)
            process.start(timeout=10)
            url = f'http://127.0.0.1:{process.port}/stream'
            with urlopen(Request(url, method='HEAD'), timeout=3) as response:
                self.assertEqual('10', response.headers['Content-Length'])
                self.assertEqual(b'', response.read())
            with urlopen(Request(url, headers={'Range': 'bytes=2-5'}), timeout=3) as response:
                self.assertEqual(206, response.status)
                self.assertEqual(b'2345', response.read())
            process.check()
            process.close()
            self.assertFalse(process._proc.is_alive())
            import socket
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', process.port))

    def test_startup_failure_is_reported_and_reaped(self):
        process = PipelineProcess(fail_init, '127.0.0.1', 0, 'Linux')
        with self.assertRaisesRegex(PipelineError, 'fixture startup failure'):
            process.start(timeout=10)
        self.assertFalse(process._proc.is_alive())

    def test_cancelled_start_is_reaped(self):
        cancel = threading.Event()
        cancel.set()
        process = PipelineProcess(fail_init, '127.0.0.1', 0, 'Linux')
        with self.assertRaisesRegex(PipelineError, 'cancelled'):
            process.start(timeout=10, cancel=cancel)
        self.assertFalse(process._proc.is_alive())
