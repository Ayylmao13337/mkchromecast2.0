#!/usr/bin/env python3
"""Run regression tests and, only when requested, one real receiver smoke test."""
import argparse
from pathlib import Path
import time
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-connect-to', help='Unique friendly name of a real Chromecast')
    parser.add_argument('--test-media-file', help='Local MP4 used by the opt-in hardware test')
    parser.add_argument('--test-duration', type=float, default=15)
    args = parser.parse_args()
    if bool(args.test_connect_to) != bool(args.test_media_file):
        parser.error('--test-connect-to and --test-media-file must be supplied together')
    if not 0 < args.test_duration <= 300:
        parser.error('--test-duration must be between 0 and 300 seconds')
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / 'tests'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        return 1
    if args.test_connect_to:
        from mkchromecast import Mkchromecast, _arg_parsing
        from mkchromecast.session import CastSession
        settings = Mkchromecast(_arg_parsing.Parser.parse_args([
            '--video', '--input-file', args.test_media_file, '--name', args.test_connect_to]))
        session = CastSession(settings)
        try:
            session.start()
            deadline = time.monotonic() + args.test_duration
            observed_playing = False
            while time.monotonic() < deadline:
                session.check()
                observed_playing |= session.receiver.cast.media_controller.status.player_is_playing
                time.sleep(.25)
            if not observed_playing:
                raise RuntimeError('Receiver did not report PLAYING during the smoke test')
            print('Hardware smoke test passed: receiver reported PLAYING')
        finally:
            session.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
