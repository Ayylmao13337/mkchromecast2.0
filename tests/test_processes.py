import subprocess
import sys
import unittest
from mkchromecast.processes import OwnedPipeline, PipelineError


def command(code):
    return [sys.executable, '-c', code]


class ProcessTests(unittest.TestCase):
    def test_producer_bytes_and_eof(self):
        pipeline = OwnedPipeline(command('import sys; sys.stdout.buffer.write(sys.stdin.buffer.read().upper())'),
                                 producer=command('print("hello")'))
        self.addCleanup(pipeline.close)
        data = b''
        while chunk := pipeline.read(1024):
            data += chunk
        self.assertEqual(b'HELLO\n', data)
        pipeline.close()
        self.assertTrue(all(p.poll() is not None for p in pipeline.processes))

    def test_failure_is_reported_with_redacted_diagnostics(self):
        pipeline = OwnedPipeline(command('import sys; print("bad https://example.com/token", file=sys.stderr); sys.exit(7)'))
        self.addCleanup(pipeline.close)
        with self.assertRaisesRegex(PipelineError, 'status 7') as caught:
            pipeline.read(1024)
        self.assertNotIn('https://example.com/token', str(caught.exception))

    def test_close_only_terminates_owned_children(self):
        unrelated = subprocess.Popen(command('import time; time.sleep(30)'))
        self.addCleanup(unrelated.wait)
        self.addCleanup(unrelated.terminate)
        pipeline = OwnedPipeline(command('import time; time.sleep(30)'))
        self.addCleanup(pipeline.close)
        pipeline.close()
        pipeline.close()
        self.assertIsNone(unrelated.poll())
        self.assertTrue(all(p.poll() is not None for p in pipeline.processes))

    def test_failed_encoder_launch_cleans_producer(self):
        from unittest.mock import patch
        spawned = []
        original = subprocess.Popen
        def track(*args, **kwargs):
            result = original(*args, **kwargs)
            spawned.append(result)
            return result
        with patch('mkchromecast.processes.subprocess.Popen', side_effect=track):
            with self.assertRaises(PipelineError):
                OwnedPipeline(['mkchromecast-missing-fixture'], producer=command('import time; time.sleep(30)'))
        self.assertEqual(1, len(spawned))
        self.assertIsNotNone(spawned[0].poll())
