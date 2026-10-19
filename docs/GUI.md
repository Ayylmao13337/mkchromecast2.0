# Desktop controls

Install the optional Qt dependency in your virtual environment:

```sh
python -m pip install '.[tray]'
mkchromecast --tray
```

The control window opens alongside the system tray icon. Click **Find devices**, select a receiver, choose **Audio** or **Screen and audio**, and click **Start streaming**. Screen sharing is offered on Linux with Chromecast receivers; Sonos remains audio-only.

For Cinnamon capture choose **Cinnamon (experimental)**. **Check setup / refresh screens** runs local diagnostics in a separate process and populates the screen selector without recording or connecting to a receiver. Select a screen after the check completes. On Wayland the system picker opens when sharing starts. Capture errors appear in the window as well as tray notifications.

Screen sharing defaults to 1080p at 25 FPS with software H.264. **Reduce streaming delay** enables the existing low-latency profile; it cannot eliminate Chromecast receiver buffering. Route application audio to the Mkchromecast sink using your desktop audio mixer. The controls are locked during streaming; stop before changing the stream settings.

**Audio preferences** opens the existing saved audio settings, now using a resizable layout. Screen sharing mode, capture backend, screen, audio source, resolution, FPS and low latency are saved automatically in desktop.json alongside the audio configuration. Corrupt files fall back to defaults. Saved devices that disappear remain visibly unavailable; choose another device instead of silently capturing a different source. The volume button controls an active receiver. Closing the main window hides it to the tray when a system tray is available; **Open MKChromecast** reopens it. **Quit** stops the session and exits. Without a system tray, closing the window exits cleanly.

The GUI uses the existing discovery worker and CastSession lifecycle. It does not provide window capture or a Cast Streaming transport. Cinnamon/NVIDIA capture and TV latency still require hardware testing.


## Audio sources and interrupted sessions

**Check setup / refresh screens** also reads PulseAudio/PipeWire sources. Select an output monitor to capture that output, a microphone to capture microphone input, or **Application routing (audio mixer)** to keep the dedicated Mkchromecast sink. Explicit sources do not change desktop routing. The active source name appears in the status line.

For the dedicated sink, applications already running at stream startup have their original output remembered. On shutdown they are moved back only if they still use this session's sink and the original output still exists. Applications started later, or whose original output disappeared, follow the audio server's fallback when the sink is removed. User changes to other outputs are respected. Cleanup failures are displayed.

A lost Chromecast control connection is reported in the window. **Retry connection** stops and cleans up the old session before starting a new one; it never creates two concurrent sessions. PyChromecast may restore the control connection itself, but that does not guarantee playback has resumed. Retry is also available after a startup or capture failure. There is no new automatic replay policy.

## Linux Mint menu launcher

With the project's virtual environment active, run:

```sh
python -m mkchromecast.desktop_install
```

This installs a launcher in your user's applications directory, pointing at the current Python environment. Search the Mint menu for **MKChromecast 2.0**. Keep the virtual environment in place; rerun the command if you move or recreate it. No administrator privileges are needed.

To update the test branch, close the program, then run from your checkout:

```sh
source .venv/bin/activate
git pull --ff-only origin feature/cinnamon-capture
python -m pip install '.[tray]'
```

The launcher continues to use the updated environment. Updates are manual; no code is downloaded or installed automatically by the GUI.
