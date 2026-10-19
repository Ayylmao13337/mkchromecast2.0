import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from experimental.cast_streaming.build import instrument
from experimental.cast_streaming.probe import command, probe


class CastStreamingPrototypeTests(unittest.TestCase):
    def test_negotiated_does_not_claim_playback(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = probe([sys.executable, '-c', 'print("MKCAST_EVENT negotiated", flush=True)'], seconds=2)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(0, code)
        self.assertEqual(['starting', 'negotiated', 'closed'], [e['event'] for e in events])
        self.assertFalse(events[-1]['playback_confirmed'])

    def test_clean_exit_without_negotiation_is_failure(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, probe([sys.executable, '-c', 'pass'], seconds=2))

    def test_timeout_stops_real_helper(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = probe([sys.executable, '-c', 'import time; time.sleep(30)'], seconds=2, startup_timeout=1)
        event = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(1, code)
        self.assertEqual('negotiation_timeout', event['reason'])
        self.assertIsNotNone(event['returncode'])

    def test_command_preserves_trust_and_does_not_use_http(self):
        with tempfile.TemporaryDirectory() as root:
            media = Path(root) / 'test clip.mp4'
            media.write_bytes(b'fixture')
            args = command(sys.executable, '10.0.0.11', media)
            self.assertEqual(['10.0.0.11:8009', str(media)], args[-2:])
            self.assertNotIn('-d', args)
            self.assertNotIn('-a', args)
            with self.assertRaises(ValueError):
                command(sys.executable, 'not-an-ip; command', media)

    def test_patch_requires_exact_native_contract(self):
        needle = '  current_negotiation_ =\n      std::make_unique<SenderSession::ConfiguredSenders>(std::move(senders));'
        self.assertIn('MKCAST_EVENT negotiated', instrument(needle))
        with self.assertRaises(ValueError):
            instrument('changed upstream source')
