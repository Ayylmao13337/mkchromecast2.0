"""Install a per-user desktop launcher for this Python environment."""
import os
from pathlib import Path
import sys


def quote_exec(value):
    # Desktop Entry Exec quoting, not shell quoting. Percent is a field code.
    value = str(value)
    if '\n' in value or '\r' in value:
        raise ValueError('Launcher paths cannot contain newlines')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return '"' + value.replace('%', '%%').replace('\\', '\\\\') + '"'


def install():
    if not sys.platform.startswith('linux'):
        raise ValueError('Desktop launcher installation supports Linux only')
    root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    applications = root / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    icon = Path(__file__).with_name('resources') / 'google.png'
    # Desktop value escaping is separate from Exec escaping.
    icon_value = str(icon).replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r')
    path = applications / 'mkchromecast.desktop'
    path.write_text('[Desktop Entry]\nType=Application\nName=MKChromecast 2.0\n'
                    'Comment=Share audio and screens with Chromecast\n'
                    f'Exec={quote_exec(sys.executable)} -m mkchromecast.cli --tray\n'
                    f'Icon={icon_value}\nTerminal=false\nCategories=AudioVideo;Audio;\n', encoding='utf-8')
    return path


def main():
    try:
        print('Installed launcher:', install())
        return 0
    except (OSError, ValueError) as exc:
        print('Cannot install launcher:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
