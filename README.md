# MKChromecast 2.0

Incremental modernization of [MKChromecast](https://github.com/muammar/mkchromecast),
retaining Python, PyChromecast, FFmpeg, the existing command builders, the Wayland
portal integration and Qt tray. This fork is **2.0.0a1**, a development alpha.
It is not yet a hardware-certified stable 2.0 release.

[Implementation status and release gates](docs/MODERNIZATION.md) ·
[Prioritized tasks](docs/ROADMAP.md) · [License](LICENSE)

For NVIDIA/Cinnamon X11 screen-capture flicker with Allow Flipping enabled,
an opt-in [experimental Cinnamon capture backend](docs/CINNAMON_CAPTURE.md)
is available via `--video --screencast --capture-backend cinnamon`.
It still needs validation on the target desktop and Chromecast.

## Install from this checkout

Requires Python 3.11 or newer on Linux or macOS. Windows is not supported.
Use native executables from your platform's package manager; historical bundled
macOS binaries are not included in the Python wheel.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
mkchromecast --help
```

Optional features:

```sh
python -m pip install '.[tray]'     # Qt system tray
python -m pip install '.[sonos]'    # Sonos adapter
python -m pip install '.[youtube]' # yt-dlp and its default extras
python -m pip install '.[dev]'     # tests, coverage, lint and build tools
```

System dependencies are separate from Python packages:

| Use | Required programs/services |
| --- | --- |
| File casting, FFmpeg audio, yt-dlp | `ffmpeg`; `ffprobe` for local media inspection |
| Linux desktop audio | PulseAudio or PipeWire's PulseAudio compatibility server, `pactl`; `parec` and a codec encoder for the default parec backend |
| Linux FFmpeg audio | FFmpeg with PulseAudio input; use `--encoder-backend ffmpeg` |
| Linux ALSA capture | FFmpeg with ALSA input and `--alsa-device`; no PulseAudio sink is created |
| macOS audio | BlackHole **16ch**, `SwitchAudioSource` from switchaudio-osx; FFmpeg with avfoundation is the preferred installation path for this alpha |
| Wayland screencast | PyGObject/Gio/GLib, xdg-desktop-portal and its desktop backend, PipeWire, GStreamer with pipewiresrc, x264enc, avenc_aac, h264parse, aacparse and mp4mux |
| YouTube | `yt-dlp` on PATH; a JavaScript runtime supported by your installed yt-dlp may also be required |

Subtitle burn-in needs FFmpeg's `subtitles` filter (libass). On macOS, use
Homebrew's `ffmpeg-full` build and select its executables on PATH:

```sh
brew install ffmpeg-full
export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
```

The regular Homebrew `ffmpeg` formula does not include all optional libraries.
See [Homebrew ffmpeg-full](https://formulae.brew.sh/formula/ffmpeg-full).

For Wayland, install your distribution's PyGObject packages and use a venv with
`--system-site-packages`, or build the optional `wayland` extra with the required
native development libraries. `pip install` alone does not install a portal or
PipeWire. The legacy macOS Node default is retained for compatibility, but needs
`webcast-osx-audio` and working native addons. Use `--encoder-backend ffmpeg` if
those are unavailable; they are not bundled in the wheel.

## Use

Discover stable IDs, then select an explicit receiver:

```sh
mkchromecast --discover
mkchromecast --device-id UUID --encoder-backend ffmpeg
mkchromecast --device-id UUID --video --input-file '/path/to/movie.mp4'
mkchromecast --device-id UUID --input-file '/path/to/music.flac' -c mp3
mkchromecast --device-id UUID --video --input-file movie.mkv --subtitles captions.srt --resolution 720p
mkchromecast --device-id UUID --video --screencast
mkchromecast --device-id UUID --video -y 'https://www.youtube.com/watch?v=VIDEO_ID'
mkchromecast --device-id UUID --source-url 'https://example.org/audio.mp3' --mtype audio/mpeg
mkchromecast --receiver sonos --discover
mkchromecast --receiver sonos --device-id RINCON_ID --encoder-backend ffmpeg -c mp3
mkchromecast --tray
```

For Linux desktop capture, select the printed `Mkchromecast_<session>` output in
your audio mixer (for example pavucontrol) for applications you want to cast.
Only the sink created by that session is removed on stop. macOS audio routing
restores the input and output devices observed before capture started.

`--control` enables `u`/`d` volume, `p` pause, `r` resume and `q` quit in a terminal.
Ctrl-C also stops casting. `--name` works when names are unique; duplicate names
require `--device-id`. The source address is selected using the route to the
receiver; `--host` overrides it and must be reachable from that receiver.
Discovery and streaming startup have explicit timeout options.

The receiver fetches `http://<source-address>:5000/stream`. Permit this port on
your local firewall and use a trusted LAN. This HTTP endpoint has no authentication
or TLS. Direct compatible MP4 files support HEAD, Range and buffered playback.
Live/transcoded streams permit one active consumer and do not support seeking.
Additional live clients receive HTTP 503 until the first disconnects.

## Behavior and limits

- Local video is inspected with ffprobe. Compatible H.264/AAC or MP3 MP4 can be
  served directly; other SDR inputs use fragmented MP4 with H.264/AAC. Subtitles
  are burned in with one combined filter chain. Use `--resolution 720p` or
  `1080p` when the receiver cannot decode the input dimensions.
- HDR requires a preconverted SDR file. Capability negotiation, automatic HDR
  tone mapping and adaptive quality are deferred.
- yt-dlp output is normalized by FFmpeg to MP3 audio or H.264/AAC MP4 video;
  a site's supported format or authentication requirements can still prevent
  playback. The video path currently selects a combined audio/video format.
- Sonos is optional and audio-only: MP3, AAC, FLAC or WAV. Playback targets the
  group's coordinator. Device generation/codec behavior still needs hardware QA.
- Screencast supports Linux X11 and Wayland. macOS screen capture is not supported.
  GPU codecs and legacy Node native addons require separate platform validation.
- `--segment-time` is rejected: the historical flag did not implement a working
  segmented stream. `--command` takes a complete FFmpeg argv string ending in
  `pipe:1`; you are responsible for matching its output to `--mtype`.
- `--hijack` remains opt-in with bounded retry intervals; it does not take over a
  different content URL. Completed finite media and receiver disconnect behavior
  require further device testing.
- Receiver connection/LOAD operations may take their bounded network timeout to
  cancel. SIGKILL/power loss cannot guarantee restoration of desktop audio routing.
  `--reset` explicitly removes MKChromecast sinks on Linux; do not use it while
  other MKChromecast sessions are active.

Configuration uses `mkchromecast.cfg` under `$XDG_CONFIG_HOME/mkchromecast` (or
`~/.config/mkchromecast`) on Linux and `~/Library/Application Support/mkchromecast`
on macOS. Existing `mkchromecast_beta.cfg` is read when the new file is absent.
Saving is atomic; invalid configuration reports an error instead of overwriting
it. Preferences apply to newly started tray sessions.

## Develop and verify

```sh
python -m pip install -e '.[dev,tray,sonos]'
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
python -m coverage run --source=mkchromecast -m unittest discover -s tests
python -m coverage report
python -m ruff check .
python -m build
```

Tests include real subprocess cleanup, real local HTTP HEAD/Range/startup,
FFmpeg transcoding and subtitle-path escaping, plus receiver/desktop mocks.
FFmpeg and optional Qt/GI tests clearly skip if their dependencies are missing.
The CI includes a separate job requiring GI. A CI definition is not evidence
that the matrix or physical hardware has passed; see the implementation status.

An opt-in hardware smoke test uses a **local file you supply** and interrupts
playback on the selected receiver:

```sh
python test.py --test-connect-to 'Living Room' --test-media-file /path/to/test.mp4
```

Historical packaging/DMG scripts and the `nodejs` subtree remain in the repository
for migration reference. Use the PEP 517 wheel build above for this alpha.
