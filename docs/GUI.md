# Desktop controls

Install the optional Qt dependency in your virtual environment:

```sh
python -m pip install '.[tray]'
mkchromecast --tray
```

The control window opens alongside the system tray icon. Click **Find devices**, select a receiver, choose **Audio** or **Screen and audio**, and click **Start streaming**. Screen sharing is offered on Linux with Chromecast receivers; Sonos remains audio-only.

For Cinnamon capture choose **Cinnamon (experimental)**. **Check setup / refresh screens** runs local diagnostics in a separate process and populates the screen selector without recording or connecting to a receiver. Select a screen after the check completes. On Wayland the system picker opens when sharing starts. Capture errors appear in the window as well as tray notifications.

Screen sharing defaults to 1080p at 25 FPS with software H.264. **Reduce streaming delay** enables the existing low-latency profile; it cannot eliminate Chromecast receiver buffering. Route application audio to the Mkchromecast sink using your desktop audio mixer. The controls are locked during streaming; stop before changing the stream settings.

**Audio preferences** opens the existing saved audio settings, now using a resizable layout. Screen settings currently last only for this application run. The volume button controls an active receiver. Closing the main window hides it to the tray when a system tray is available; **Open MKChromecast** reopens it. **Quit** stops the session and exits. Without a system tray, closing the window exits cleanly.

The GUI uses the existing discovery worker and CastSession lifecycle. It does not provide window capture, automatic reconnect, or a Cast Streaming transport. Cinnamon/NVIDIA capture and TV latency still require hardware testing.
