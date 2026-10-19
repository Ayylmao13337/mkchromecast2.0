# Cast Streaming protocol prototype (not live screen sharing)

This isolated developer experiment builds the pinned Open Screen standalone
sender and adds a Python process supervisor. It sends a **completed media file**
as a mirroring session rather than using MKChromecast's HTTP media LOAD. It does
not yet consume Cinnamon frames or measure live desktop delay. The normal app,
GUI and HTTP defaults are unchanged.

## Build gate

The implementation is present; native compilation, upstream unit tests, local
receiver streaming and physical-device playback must pass before claiming a
working transport. The Codex workspace lacks pkg-config and native development
libraries, so native builds run in the dedicated GitHub workflow. Check its
result; the existence of code or a downloaded artifact is not validation.

On Linux, install prerequisites using your package manager (Mint/Ubuntu example):

```sh
sudo apt install git python3 build-essential pkg-config ffmpeg \
  libavcodec-dev libavformat-dev libavutil-dev libswresample-dev \
  libopus-dev libvpx-dev libsdl2-dev
python experimental/cast_streaming/build.py /path/to/new-build-directory
```

Choose a new directory. The script downloads the native toolchain/dependencies
and may take substantial disk space and time. It pins Open Screen to
`8978b74badf042795c07fcf99d0a53dccbd3dcf6` and depot_tools to
`b184a46054cc2ca5e4eff2ebf4de3dff7603b6f0`. Open Screen's DEPS pins transitive
sources; system-library versions are recorded in `mkcast-build.json`. System
packages are not hermetic, and support across Mint versions remains unverified.
A narrowly checked source edit emits `MKCAST_EVENT negotiated` only after
OnNegotiated validates required senders. This is OFFER/ANSWER acceptance, NOT
proof that frames were decoded or displayed.

## File-based physical receiver probe

Stop existing casting first. Prepare a synthetic clip (no screen/audio capture):

```sh
ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=30 \
  -f lavfi -i sine=frequency=440:sample_rate=48000 \
  -t 20 -c:v libx264 -pix_fmt yuv420p -c:a aac /tmp/mkcast-fixture.mp4
python experimental/cast_streaming/probe.py \
  --sender /path/to/new-build-directory/openscreen/out/mkcast/cast_sender \
  --receiver 10.0.0.11 --file /tmp/mkcast-fixture.mp4 --dry-run
```

Remove `--dry-run` to explicitly connect to that receiver and launch its
mirroring app. The fixture includes an audible tone. The address is the IP from
the user's reported device and may change; verify before connecting. The helper
uses VP8/Opus, an 8 Mbps ceiling, no looping and the upstream Google certificate
trust store. It does not disable authentication, inject a developer certificate,
or invoke the legacy Android RTP hack.

The supervisor prints JSON `starting`, `negotiated` and `closed` events with a
bounded diagnostic tail. It stops the helper on timeout or Ctrl-C, allowing
upstream a graceful shutdown before forced termination. A successful exit means
only that negotiation was observed and the helper exited cleanly. Always check
whether video/tone actually played. Do not interpret `starting` as ready. A
wrong/unpatched binary will time out rather than inventing readiness.

## Remaining gates

1. Green native build and upstream tests on the pinned sources.
2. Local Open Screen receiver integration (explicit development trust confined
   to that test environment), then positive physical receiver playback and stop.
3. Replace the file input with timestamped bounded live Cinnamon video/audio;
   add media-ready/error/closed IPC beyond the prototype log marker.
4. Test actual end-to-end delay and sync against the measured HTTP baseline:
   about 0.39 s local preview and one observed 1.628 s PC-to-TV sample.
5. Only then add an optional user-facing Cast Streaming transport.

Source contracts:
- https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/standalone_sender/main.cc
- https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/standalone_sender/looping_file_cast_agent.cc
- https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/docs/external_libraries.md
