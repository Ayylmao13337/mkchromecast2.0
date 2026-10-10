# Screen selection and local diagnostics

These commands are available on the experimental `feature/cinnamon-capture`
branch. Neither listing screens nor collecting diagnostics starts a recording,
connects to a Chromecast, creates an audio sink, or changes NVIDIA settings.

## Choose a screen on Cinnamon X11

```sh
mkchromecast --list-screens --capture-backend cinnamon
```

The table shows the ID, name provided by Cinnamon, size, position and whether
each monitor is primary. IDs are Cinnamon's zero-based monitor indices. Use the
ID shown on your own machine; do not assume a particular connector is index 0.

```sh
mkchromecast --device-id 'YOUR-DEVICE-ID' --video --screencast \
  --capture-backend cinnamon --screen 1 --resolution 1080p --low-latency
```

`--screen primary` explicitly selects the primary monitor. Omitting `--screen`
keeps Cinnamon's existing primary-monitor behavior. Re-list after changing the
monitor layout: indices may change. A selected monitor disappearing, changing
geometry or being reassigned causes capture to stop rather than silently switch
to another area. Window selection is not implemented yet.

## Choose a screen on ordinary X11

```sh
mkchromecast --list-screens
mkchromecast --device-id 'YOUR-DEVICE-ID' --video --screencast \
  --screen DP-0 --resolution 1080p --low-latency
```

Use an output name from the first command, such as `HDMI-0` or `DP-0`, or
`primary`. This path needs `xrandr` (`sudo apt install x11-xserver-utils` on Mint).
Inactive/disconnected outputs are excluded. `--display` is honored by both
screen discovery and FFmpeg.

Explicit selection captures the **whole selected monitor** at its actual offset,
then scales and pads to the requested output size. A 1920x1200 screen therefore
fits into 1920x1080 with side borders instead of losing its bottom 120 pixels.
The original top-left-region behavior is retained when no `--screen` is given
on X11. Layout changes are checked approximately every three seconds and stop
the cast with an error. Negative X11 offsets are rejected with an explanation.

This does not fix NVIDIA's x11grab flipping artifact; use the Cinnamon backend
for the compositor-capture experiment. Wayland keeps its portal screen picker:
omit `--screen`. `--list-screens` explains this rather than querying XWayland and
presenting an incorrect physical-monitor list.

## Collect a diagnostic report

For the Cinnamon experiment:

```sh
mkchromecast --diagnose --capture-backend cinnamon
```

For automatic X11/Wayland selection:

```sh
mkchromecast --diagnose
```

The JSON report includes MKChromecast/Python versions, desktop/session type,
selected capture backend, required executable availability, relevant GStreamer
elements, audio-server reachability, screen inventory and core package versions.
Commands have bounded timeouts. Errors are reported as failed checks, with
installation hints where appropriate. Exit status 1 means a required check
failed; `ok: null` means a check was not performed.

For missing GStreamer components on Mint:

```sh
sudo apt install libglib2.0-bin gstreamer1.0-tools gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav pulseaudio-utils
```

The report deliberately does not discover receivers or include a media URL,
device UUID, full environment dump, or raw `pactl info` output. It does contact
the selected desktop/audio services to inspect them. It cannot certify successful
capture, NVENC GPU availability, network connectivity, A/V sync or TV playback.
Wayland's permission dialog is not opened: portal negotiation is explicitly
reported as untested. A green local report is not hardware certification.

Screencast errors also print the matching diagnostic command. When reporting a
failure, include the short error and this report rather than the whole injected
JavaScript program.

Automated coverage includes the reported dual-monitor xrandr layout, nonzero
offset capture, real FFmpeg scaling/padding, layout-change detection, the
Cinnamon screen-selection lifecycle, and CLI isolation from casting/settings
initialization. Actual screen selection still needs a desktop hardware test.
