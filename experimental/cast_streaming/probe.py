"""Bounded file-based Cast Streaming probe; not live desktop capture."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time


def command(sender, receiver, media):
    sender, media = Path(sender).resolve(), Path(media).resolve()
    if not sender.is_file() or not os.access(sender, os.X_OK):
        raise ValueError('Build cast_sender first; provide its executable path')
    if not media.is_file():
        raise ValueError('Input must be a completed regular media file, not a pipe or URL')
    address = ipaddress.ip_address(receiver)
    if address.is_unspecified or address.is_multicast:
        raise ValueError('Receiver must be a unicast IP address')
    endpoint = f'[{address}]:8009' if address.version == 6 else f'{address}:8009'
    # Upstream owns app launch, authentication, negotiation and RTP transport.
    # No developer certificate, Android hack or HTTP LOAD is injected.
    return [str(sender), '-n', '-v', '-c', 'vp8', '-m', '8000000', endpoint, str(media)]


def event(state, **fields):
    print(json.dumps(dict(event=state, **fields)), flush=True)


def probe(argv, seconds=30, startup_timeout=20):
    if not 1 <= seconds <= 300 or not 1 <= startup_timeout <= 120:
        raise ValueError('Invalid probe duration or startup timeout')
    started = time.monotonic()
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    negotiated = False
    pending = bytearray()
    tail = []
    reason = 'duration_complete'
    try:
        event('starting', pid=process.pid, scope='file fixture; no live capture')
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                elapsed = time.monotonic() - started
                if not negotiated and elapsed >= startup_timeout:
                    reason = 'negotiation_timeout'
                    break
                if elapsed >= seconds:
                    break
                if not selector.select(.1):
                    if process.poll() is not None:
                        reason = 'process_exited'
                        break
                    continue
                data = os.read(process.stdout.fileno(), 4096)
                if not data:
                    reason = 'process_exited'
                    break
                pending.extend(data)
                while b'\n' in pending:
                    raw, _, pending = pending.partition(b'\n')
                    line = raw.decode(errors='replace')[-2048:]
                    tail.append(line)
                    tail = tail[-20:]
                    if 'MKCAST_EVENT negotiated' in line and not negotiated:
                        negotiated = True
                        event('negotiated', elapsed_s=round(elapsed, 3),
                              note='OFFER/ANSWER accepted; does not prove decoded or displayed frames')
                if len(pending) > 8192:
                    pending = pending[-4096:]
    except KeyboardInterrupt:
        reason = 'cancelled'
    finally:
        if reason == 'process_exited':
            process.wait(timeout=3)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        process.stdout.close()
    event('closed', reason=reason, negotiated=negotiated, returncode=process.returncode,
          playback_confirmed=False, diagnostic_tail=tail)
    if reason == 'cancelled':
        return 130
    return 0 if negotiated and process.returncode == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sender', required=True, type=Path)
    parser.add_argument('--receiver', required=True, help='Explicit receiver IP; port 8009')
    parser.add_argument('--file', required=True, type=Path)
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        argv = command(args.sender, args.receiver, args.file)
        if args.dry_run:
            event('dry_run', argv=argv, receiver_contacted=False)
            return 0
        return probe(argv, args.seconds)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        event('failed', error=str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
