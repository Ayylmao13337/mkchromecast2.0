# Remaining 2.0 roadmap and issue-ready tasks

This backlog is ready to copy into GitHub issues. Entries below are proposals;
no remote issues have been created. P0 blocks stable release, P1 completes core
reliability, P2 improves platform support and maintainability.

## Completed foundation in 2.0.0a1

- Runtime packaging, feature extras, installed CLI and bundled UI resources.
- Explicit receiver/session/server ownership and removal of pickle/global kill IPC.
- Bounded discovery and UUID selection; optional Sonos adapter.
- Direct-file Range and HEAD, subprocess cleanup and streaming readiness/error IPC.
- FFmpeg subtitle/map/MIME fixes and yt-dlp normalization.
- Atomic config, tray worker/error/volume/reset fixes and a regression suite.

These are implemented, not hardware-certified. The following gates remain.

## Milestone 1 — hardware-qualified alpha

| Priority | Issue title | Acceptance criteria |
| --- | --- | --- |
| P0 | Run Linux/macOS and Python 3.11–3.14 CI matrix | Clean wheel install outside checkout, unit/integration suite, lint and build pass on every declared target; CI links attached |
| P0 | Validate Chromecast and Google TV playback matrix | Record model/firmware, source OS, codec, direct/transcode path; verify audio, MP4, subtitles, pause/resume, stop, volume and duplicate-name selection on an older Cast device and Google TV |
| P0 | Validate session cleanup under failure | Unplug receiver, deny portal, occupy port, kill encoder, interrupt startup and stop repeatedly; no orphan owned encoder/server, no unrelated process stopped, audio routing restored |
| P0 | Verify Sonos S1/S2 and grouped playback | Record supported MIME and device variants; coordinator playback, ownership-safe stop, volume and timeout behavior pass; reject unsupported combinations before routing starts |
| P0 | Exercise X11 and Wayland desktops | GNOME/KDE plus one wlroots portal where available; grant/deny/cancel/reconnect tests; verify audio/video sync and repeated portal fd acquisition |
| P0 | Validate macOS audio on Apple Silicon | Native FFmpeg, SwitchAudioSource and BlackHole 16ch; partial startup failure and repeated stop restore exact previous devices; document permissions |
| P1 | Run 8-hour stream and reconnect soak | Log CPU/RSS/fd/thread/process counts; no unbounded growth; clean teardown after network and encoder failures |

## Milestone 2 — reliable media and controls

| Priority | Issue title | Acceptance criteria |
| --- | --- | --- |
| P1 | Define receiver-aware media profiles | Probe codec/profile/level/fps/bitrate/audio channels; deterministic copy/transcode decision; bounded SDR output defaults verified per receiver class |
| P1 | Make lifecycle transitions and cancellation explicit | Reject session reuse after close; interrupt or bound discovery/connection/LOAD; race tests for stop during each acquisition phase; typed state/event model |
| P1 | Separate completion, interruption and reconnect | Finite media ends normally, pause never reconnects, foreign sessions stay untouched; opt-in reconnect has bounded retries and gives an actionable failure |
| P1 | Expand yt-dlp integration coverage | Audio/video URL fixtures, separate-stream merging policy, runtime/auth requirements, extractor failure and child-process cleanup; MIME verified from actual output |
| P1 | Exercise live HTTP reconnect and buffer limits | Real receiver disconnect/reconnect, transient double connections, backpressure, truncated responses and slow clients; document one-consumer behavior or implement a tested replacement |
| P1 | Add startup capability diagnostics | Check required codecs/input devices/tools before routing changes; one actionable error naming missing program, plugin or permission |
| P1 | Offer stream access tokens | Unpredictable per-session URL, exact endpoint validation, invalid/expired token tests; retain required receiver Range/CORS behavior |
| P1 | Validate terminal and Qt desktop interaction | PTY key tests and signal restoration; real desktop notifications, hot switching, volume, preferences and quit during startup/update/search |

## Milestone 3 — release engineering and follow-up

| Priority | Issue title | Acceptance criteria |
| --- | --- | --- |
| P1 | Define reproducible dependency/release policy | Tested constraints per supported Python/platform, automated dependency updates, wheel/sdist artifact checks and changelog/release procedure |
| P1 | Replace or retire native Node audio path | Compare FFmpeg behavior on macOS; decide migration/default, preserve settings compatibility, remove untested native addons only with migration documentation |
| P2 | Deliver native macOS distribution | arm64/x86_64 support decision, signed/notarized bundle, required permissions, repeatable build and install/uninstall test |
| P2 | Move settings and events to typed models | Preserve CLI/config compatibility while removing parser cache and dynamic attributes; type-check core modules without blanket ignores |
| P2 | Migrate optional tray to Qt 6 | Separate UI from adapters, validate Linux/macOS tray behavior and scaling; no headless dependency regression |
| P2 | Add structured observability | Session IDs, redacted diagnostics, explicit state and failure reason; support bundle excludes URLs/cookies/secrets |
| P2 | Design HDR and seekable transcoding | Explicit receiver support matrix and HDR/tone-map fixtures; design HLS/DASH/range semantics before implementation |

## Stable 2.0 release gate

All P0 tasks passed with attached evidence; supported OS/device/codec matrix
published; no remaining known critical lifecycle or routing defects; documented
limitations and migration; reproducible artifacts; changelog and manual rollback.
A larger rewrite is not part of this roadmap. Each milestone should be reviewed
and released as a small series of changes with behavior tests.
