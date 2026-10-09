# Experimental Cinnamon capture

This backend targets **Linux Mint, Cinnamon 6.4, X11**. It is an opt-in prototype,
not yet a hardware-verified fix. It was motivated by an RTX 3070 / NVIDIA
580.173.02 report: X11 capture showed intermittent wallpaper with Allow Flipping
enabled; Cinnamon's built-in recording was clean, even while the cast was not.
The same user reproduced the failure in a local FFmpeg x11grab recording.

## Install and test on Linux Mint

These commands use a separate checkout so your existing installation stays available.
Choose a different directory name if `mkchromecast-cinnamon-test` already exists.

```sh
sudo apt update
sudo apt install git python3-venv ffmpeg pulseaudio-utils libglib2.0-bin \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
git clone --branch feature/cinnamon-capture https://github.com/Ayylmao13337/mkchromecast2.0.git mkchromecast-cinnamon-test
cd mkchromecast-cinnamon-test
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
mkchromecast --help
```

Stop the built-in recording used for the earlier experiment. Leave NVIDIA's
Allow Flipping enabled, and use your actual Chromecast UUID below:

```sh
nvidia-settings -a AllowFlipping=1
mkchromecast --device-id 'YOUR-DEVICE-ID' --video --screencast \
  --capture-backend cinnamon --fps 25 --resolution 1080p --debug
```

Use `mkchromecast --discover` if you need the device ID. Route the application's
audio to the MKChromecast output shown in the terminal/audio mixer, as with
normal screen sharing. Press Ctrl-C to stop.

To compare against the existing capture path, stop casting and run the same
command without `--capture-backend cinnamon`. The NVIDIA setting is never
changed by MKChromecast. To return to the previously successful workaround:

```sh
nvidia-settings -a AllowFlipping=0
```

For future testing, open a terminal in this test directory and run
`. .venv/bin/activate` before launching MKChromecast.

## What it does

1. Calls Cinnamon's `org.Cinnamon.Eval` session D-Bus interface to instantiate a
   separate `Cinnamon.Recorder` using the compositor's stage capture.
2. Captures the **primary monitor**, including its actual X/Y offset. Scales to
   the requested resolution with aspect-ratio padding and converts to I420.
3. Passes raw frames through GStreamer's `shmsink`/`shmsrc` inside a private 0700
   temporary directory with 0600 shared-memory permissions. No new network
   listener or growing video file is used.
4. Encodes H.264 and mixes PulseAudio/PipeWire audio as AAC in the streaming
   subprocess. The existing fragmented-MP4 HTTP and Chromecast paths are reused.

The normal Cinnamon recorder, its keyboard shortcut, and its GSettings are not
changed. No extension installation, PyGObject dependency, or unsafe-mode switch
is required. The backend fails if Cinnamon's Eval API is unavailable; it does
not change security settings to enable it.

Each session has a unique ownership token. Normal shutdown closes its recorder
and removes its temporary directory. A compositor-side lease expires within
approximately 20 seconds if the streaming process crashes or is killed. Only
the owner can refresh or stop that recorder. Monitor geometry changes and
recorder failures stop the cast with an error. After a hard kill, temporary
filesystem remnants may remain, but the lease stops capture. A hard kill can
also leave GStreamer shared-memory remnants; log out/in if necessary.

## Limitations and verification

- Prototype for the Cinnamon **6.4 API**, inspected at tag 6.4.14. Eval and
  Recorder are desktop-specific interfaces, not a stable cross-desktop portal.
- Captures the primary monitor; no monitor picker yet. Restart casting after
  changing primary monitor or resolution.
- Integer FPS from 1 to 60; H.264 software encoding only. `h264_nvenc` and ALSA
  input are rejected for this backend. Try 15 FPS or 720p if CPU usage is high.
- Receiver pause does not suspend the capture process, so its ownership lease
  stays alive. Stop casting to stop desktop capture.
- Cinnamon 6.4's recorder cleanup assumes a filename even for a custom output
  sink. This can emit GLib/Gtk recent-file warnings on stop; no video file is
  intended. This upstream behavior needs verification on the target desktop.
- Unit tests exercise configuration, D-Bus error handling, partial-start cleanup,
  token ownership, expiry, monitor changes and integration. The JavaScript
  lifecycle harness uses a fake compositor.
- A dedicated Linux CI test uses real GStreamer SHM transport, two consecutive
  readers, H.264/AAC muxing and FFmpeg decoding. Synthetic video/audio do **not**
  verify Cinnamon, real audio sync, NVIDIA flipping, or Chromecast playback.

Hardware acceptance: test windowed and fullscreen video for at least five
minutes with Allow Flipping enabled, check audio sync, stop/restart the cast,
then verify the ordinary Cinnamon recorder still works. Retest at 119.88 Hz.
If it fails, include the terminal error, Cinnamon version, whether the TV starts
playing, and whether the original wallpaper artifact returns.

Implementation references:

- [Cinnamon 6.4.14 recorder](https://github.com/linuxmint/cinnamon/blob/6.4.14/src/cinnamon-recorder.c)
- [Cinnamon D-Bus Eval](https://github.com/linuxmint/cinnamon/blob/6.4.14/js/ui/cinnamonDBus.js)
- [Built-in recorder](https://github.com/linuxmint/cinnamon/blob/6.4.14/js/ui/screenRecorder.js)
