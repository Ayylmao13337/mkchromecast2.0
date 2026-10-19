# Experimental low-latency screencasting

Add `--low-latency` to a `--video --screencast` command. It works with the
existing X11/FFmpeg path and the Cinnamon/Wayland GStreamer paths. It does not
change file playback or become the default. It is still HTTP media streaming,
not Chromium's Cast Streaming mirroring protocol.

```sh
mkchromecast --device-id 'YOUR-DEVICE-ID' --video --screencast \
  --capture-backend cinnamon --fps 25 --resolution 1080p --low-latency
```

Omit `--capture-backend cinnamon` to use automatic X11/Wayland capture. To compare
profiles, stop the cast and run the same command without `--low-latency`.
Keep resolution, FPS, capture backend and receiver fixed for that comparison.

## What changes

| Setting | Default | Low latency |
| --- | --- | --- |
| FFmpeg keyframe interval | Up to 60 frames (2.4 s at 25 FPS) | Approximately 0.5 s, rounded up to a whole frame |
| FFmpeg MP4 fragmentation | At video keyframes | At keyframes or a 250 ms duration boundary |
| FFmpeg B frames | Encoder's existing policy | Explicitly disabled |
| FFmpeg output flushing | Existing default | Flush after packets |
| GStreamer keyframe interval | Approximately 2 s | Approximately 0.5 s |
| GStreamer fragment target | 1000 ms | 250 ms |
| GStreamer pre-encoder raw queue | No additional queue | At most two queued raw frames; drop oldest on overload |
| GStreamer post-encoder queues | Element defaults | 250 ms limit, backpressure; never drop compressed packets |

The preset and bitrate policy remain the same to isolate fragmentation effects.
More keyframes can increase bandwidth or reduce quality at a fixed bitrate.
Shorter fragments can make playback more sensitive to network jitter. At very
low FPS even one frame may exceed the target interval. Encoded queues are not
an end-to-end latency bound: the receiver, network and other elements can buffer.

`--chunk-size` is not the main fix: our HTTP relay uses `os.read`, which returns
available bytes without waiting for its whole requested chunk to fill. Likewise,
FFmpeg's `-bufsize 20000k` is a rate-control setting, not proof of a fixed two-second
delay. The current receiver LOAD already specifies `LIVE`; that alone does not
turn the media player into Chromium's mirroring receiver.

## Reproducible local measurement

From an installed development checkout with FFmpeg and ffprobe on PATH:

```sh
python -m tools.benchmark_screencast --seconds 8 --resolution 720p --fps 25
```

This uses the **actual production FFmpeg encoder/mux settings**, replacing only
the capture inputs with realtime synthetic video and a tone. It parses complete
MP4 `mdat` boxes, reports their arrival times, inspects the codecs and decodes
the full result with FFmpeg. It does not record your desktop or contact a TV.

Example measured in the development Linux container on 2026-10-09 using
FFmpeg 6.1.1, libx264, 720p/25 FPS, eight seconds per profile:

| Profile | Median completed-media-fragment interval | Output bytes | Full decode |
| --- | ---: | ---: | --- |
| Default | 2.409 s | 4,110,035 | Passed, H.264 + AAC |
| Low latency | 0.254 s | 4,298,072 | Passed, H.264 + AAC |

Raw results: [low-latency-benchmark.jsonl](low-latency-benchmark.jsonl).
These are **output cadence measurements, not input-to-TV latency**. The last
partial-duration fragment is excluded from the interval statistic. FFmpeg's
startup read-rate burst means first-fragment arrival is not a reliable screen
latency measurement. This small synthetic sample cannot predict a particular
GPU, desktop, Wi-Fi connection or Chromecast's playback buffer.

The dedicated GStreamer CI test covers both profiles with SHM video, synthetic
audio, two consecutive connections and H.264/AAC decoding. It does not measure
the real compositor or the TV. NVENC command generation remains available on
the X11 path, but no NVIDIA hardware was available for this verification.

## Hardware acceptance when convenient

Compare the two profiles on the same capture backend. Display a running
millisecond timer on the PC and photograph the PC and TV in the same frame,
or film both screens together. Take several samples after playback settles;
the difference measures display delay, not pure keyboard/mouse latency.
Also check five-minute stability, audio sync and stop/reconnect behavior.

Chromium comparison must use the same receiver/network and comparable video
resolution. A faster Cast Streaming transport is a separate investigation:
[Cast Streaming integration assessment](CAST_STREAMING.md).

## Cinnamon: compare 250 ms and 100 ms fragments

For a TV delay of several seconds that barely changes with resolution/FPS, first
measure output cadence instead of assuming the encoder is too slow. The optional
`--stream-metrics` prints `STREAM_METRICS` JSON every approximately five seconds
when data arrives, plus a final summary on stream closure. It observes complete
MP4 media boxes before HTTP transmission, without opening a second capture or
receiver connection, and retains only a box header rather than video frames.
`first_media_box_s` starts when HTTP consumption begins (not at capture startup).
`max_media_box_gap_s` is the largest observed gap between completed media boxes;
audio/video boxes may alternate, so this is not a video frame interval. HTTP
backpressure can also affect these numbers. No output while stalled is itself
useful; the summary is emitted only when reading resumes or closes.

Compare the same screen, FPS and resolution, stopping one run before the next:

```sh
mkchromecast --device-id YOUR_DEVICE_ID --video --screencast \
  --capture-backend cinnamon --resolution 1080p --fps 60 \
  --low-latency --stream-metrics --cinnamon-fragment-ms 250

mkchromecast --device-id YOUR_DEVICE_ID --video --screencast \
  --capture-backend cinnamon --resolution 1080p --fps 60 \
  --low-latency --stream-metrics --cinnamon-fragment-ms 100
```

The experimental 100 ms profile reduces mux fragment duration, encoded queue
limits and the keyframe interval (approximately 100 ms, rounded to whole frames).
It never drops encoded video packets. More frequent keyframes can reduce quality
at the fixed bitrate. Revert to 250 ms if playback becomes unstable. The default
profile is unchanged. These flags currently target Cinnamon only.

For end-to-end comparison, display a running stopwatch on the PC and photograph
both the PC and TV in the same shot. Repeat several times after startup settles.
Compare the displayed times and note freezes/audio sync. Short media-box gaps
alone do NOT prove low TV delay. If the TV remains 2–3 seconds behind despite fast
output, investigate receiver buffering/Cast Streaming rather than claiming an
encoder tuning success. Cast Streaming is still a separate, unimplemented path.

## Compare local playback with the TV

`--local-preview` uses the production Cinnamon capture, H.264/AAC encoding and
HTTP pipeline, but binds only to `127.0.0.1` on an automatically allocated port.
It does not discover or connect to a Chromecast. It opens ffplay with reduced
buffering flags and muted audio. Close the player or press Ctrl-C to release the
capture, HTTP server, player and private audio sink. Install Mint's `ffmpeg`
package if ffplay is missing. Do not run local preview and casting together:
Cinnamon capture supports one owned recorder at a time.

1. In a terminal with the virtual environment active, start the source clock:
   `python -m mkchromecast.latency_clock` (requires the tray/Qt extra).
2. Put that clock on the primary/captured monitor.
3. In another activated terminal, start:

```sh
mkchromecast --local-preview --video --screencast \
  --capture-backend cinnamon --screen primary --resolution 1080p --fps 60 \
  --low-latency --cinnamon-fragment-ms 250 --stream-metrics
```

4. Move the preview onto the other monitor. Do not capture its own window.
   Let it settle for at least ten seconds. Photograph both clocks in the same
   shot and subtract the delayed time from the source time. Take several samples.
   Screen refresh and camera exposure limit accuracy; the millisecond digits
   are for readability, not a promise of millisecond accuracy.
5. Stop local preview, keep the clock running and cast with the same settings
   (remove `--local-preview`, add your `--device-id`). Photograph the PC clock
   and TV copy together. Compare with the local measurements.

The local delay includes capture, encoding/muxing, loopback HTTP, ffplay decoding,
its buffering and local display latency. It is not a pure encoder measurement.
A fast local preview plus a slow TV strengthens the case for investigating the
network/receiver path. A slow local preview alone does not prove slow capture:
ffplay may buffer too. Muted playback still processes audio, but this comparison
is visual only and cannot establish audio sync. No automated TV latency estimate
or Cast Streaming implementation is included.
