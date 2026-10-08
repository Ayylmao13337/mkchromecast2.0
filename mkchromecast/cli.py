"""Command-line adapter for the shared casting session."""
import signal
import sys
import threading

from mkchromecast import Mkchromecast, _arg_parsing
from mkchromecast.constants import OpMode
from mkchromecast.version import __version__


def main(argv=None):
    session = None
    stopped = threading.Event()
    previous = {}

    def stop_signal(_number, _frame):
        stopped.set()
        if session is not None:
            session.cancel.set()

    try:
        args = _arg_parsing.Parser.parse_args(argv)
        settings = Mkchromecast(args)
        if settings.operation == OpMode.VERSION:
            print("mkchromecast " + __version__)
            return 0
        if settings.operation == OpMode.RESET:
            if settings.platform == "Linux":
                from mkchromecast.pulseaudio import reset_sinks
                reset_sinks()
            else:
                raise ValueError("Audio routing is restored automatically on stop; select the desired device in macOS Sound settings")
            return 0
        if settings.operation == OpMode.TRAY:
            from mkchromecast.systray import main as tray_main
            return tray_main(settings)
        from mkchromecast.session import CastSession, receiver_for
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, stop_signal)
        if settings.operation == OpMode.DISCOVER:
            receiver = receiver_for(settings)
            try:
                receiver.initialize_cast(cancel=stopped)
                from mkchromecast.cast import print_available_devices
                print_available_devices(receiver.available_devices)
            finally:
                receiver.close()
            return 0
        session = CastSession(settings)
        session.start()
        if settings.control:
            if not sys.stdin.isatty():
                raise ValueError("--control requires an interactive terminal")
            print("u/d: volume; p/r: pause/resume; q: quit")
            import select
            import termios
            import tty
            terminal_state = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            try:
                while not stopped.is_set():
                    session.check()
                    readable, _, _ = select.select([sys.stdin], [], [], .25)
                    if not readable:
                        continue
                    key = sys.stdin.read(1)
                    if key in {"q", "\x03", "\x04"}:
                        break
                    if key == "u":
                        session.receiver.volume_up()
                    elif key == "d":
                        session.receiver.volume_down()
                    elif key == "p":
                        session.pause()
                    elif key == "r":
                        session.resume()
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, terminal_state)
        else:
            print("Casting. Press Ctrl-C to stop.")
            while not stopped.wait(.25):
                session.check()
        return 0
    except KeyboardInterrupt:
        return 130
    except (Exception,) as exc:
        print(f"mkchromecast: {exc}", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
