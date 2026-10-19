# Cast Streaming integration assessment

Status: source investigation and proposed module boundary, **not implemented**.
The implemented `--low-latency` option still sends fragmented MP4 over HTTP.
It must not be described as Chromium-style mirroring or guaranteed to match
Chromium latency.

## Source snapshot inspected

Open Screen commit **8978b74badf042795c07fcf99d0a53dccbd3dcf6**, inspected
2026-10-09. These are pinned references, not assumptions about a future release:

- [Project/build setup](https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/README.md)
- [Standalone sender/receiver guide](https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/docs/USING.md)
- [Python binding](https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/standalone_sender/bindings/python/python_bindings.cc)
- [Sender bridge contract](https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/standalone_sender/bindings/python/sender_bridge.h)
- [Binding build dependencies](https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/standalone_sender/bindings/python/BUILD.gn)
- [Streaming protocol](https://github.com/chromium/openscreen/blob/8978b74badf042795c07fcf99d0a53dccbd3dcf6/cast/protocol/streaming_session_protocol.md)

## Findings that affect the implementation

Open Screen provides Cast application control and realtime media streaming.
The existing examples negotiate a mirroring session rather than asking a media
player to fetch an HTTP URL. This is the appropriate protocol family to evaluate
for parity with Chromium screen sharing.

There is now a pybind11 module named `cast_sender`, exposing `CastRuntime`,
`StreamConfig`, `CastSender.stream_video()` and `teardown()`. However:

- `StreamConfig` takes a **file_path**, not raw live frames or an audio callback.
  Piping a growing MP4 into the file example is not a demonstrated live solution.
- `stream_video()` schedules work asynchronously. Its successful return is not
  evidence of a connected receiver or successful media negotiation. Production
  integration needs ready/error/closed events.
- The GN binding target is marked `testonly = true`. It links FFmpeg libraries,
  Opus and VPX plus Open Screen dependencies; it is not a drop-in Python runtime
  dependency for MKChromecast's wheel.
- Building requires depot_tools/gclient, GN/Ninja and the native toolchain and
  libraries. The standalone sender/receiver guide supports Linux/macOS, and
  explicitly notes missing Windows platform support.
- The bridge supports official Google-signed receiver trust by default. Developer
  certificates are for a deliberately configured local test receiver; a normal
  Chromecast integration should preserve the default authentication.

This revision was inspected, not compiled or connected to a real receiver in
this workspace. Build reproducibility and target-device compatibility are open
gates. No native dependency or experimental transport selector has been silently
added to the installed application's defaults.

## Proposed incremental boundary

Keep Python's discovery, CLI, tray and session lifecycle. Add an optional native
**helper process**, isolated from the Python UI, for Cast Streaming. Its ownership
and lifecycle should match the existing PipelineProcess pattern, but its output
goes directly to the receiver rather than the HTTP server.

| Component | Responsibility |
| --- | --- |
| Python session | Select device, own capture/audio resources, cancel and report errors |
| Capture adapter | Supply timestamped primary-monitor frames through local IPC; retain the Cinnamon lease |
| Native helper | Own mirroring app launch, TLS/control, OFFER/ANSWER negotiation, encoding, RTP/feedback and shutdown |
| Session status IPC | Distinguish starting, negotiated, sending, failed and closed; report queue depth and dropped frames |

The helper should own the mirroring app/control connection for this transport.
Do not concurrently call the existing `Casting.play_cast()` media LOAD method,
which targets HTTP playback. Discovery can still supply the receiver address.

For a first live-input prototype, bridge the existing Cinnamon SHM video through
GStreamer `shmsrc`/`appsink` into the helper, with PulseAudio/PipeWire audio on
the same monotonic timeline. Open Screen's live sender API and encoder interface
must be evaluated directly; its file-oriented Python binding is insufficient.
Use bounded queues and receiver feedback. Do not drop arbitrary encoded H.264
packets to catch up. Keep file/URL casting on the current implementation.

## Ordered implementation tasks and acceptance gates

1. **P0 — Reproducible native build:** pin the inspected revision, build sender
   and local receiver in Linux CI; record native versions, licenses and artifacts.
   Gate: repeatable build and upstream sender/receiver tests pass.
2. **P0 — Controlled session prototype:** send a synthetic/file fixture through
   the example to a local receiver and then a physical Chromecast. Capture
   negotiation/error/close events. Gate: positive media readiness, not merely
   a successful function return; cancellation and receiver loss terminate cleanly.
3. **P1 — Live-frame adapter:** add timestamped raw video/audio ingestion and
   feedback-aware scheduling. Gate: bounded memory/queues, no growing files,
   predictable stop and preserved A/V sync under simulated slow consumption.
4. **P1 — Python helper-process integration:** versioned JSON control messages
   plus private frame transport; parent-death cleanup, timeouts and real errors.
   Gate: reuse selected device/capture ownership without launching HTTP playback.
5. **P1 — Hardware comparison:** compare to Chromium on the same Chromecast,
   desktop, resolution and network. Gate: report median/tail display delay,
   packet-loss behavior, A/V sync, CPU/GPU cost and 30-minute stability.
6. **P2 — Optional distribution:** package supported native builds; expose a
   transport option only after readiness and failure handling work. Keep HTTP
   available for media playback and incompatible receivers.

This sequence extends the existing project rather than rewriting it. The next
Cast Streaming work item is a native build/session prototype, not replacing
all PyChromecast or FFmpeg functionality.
