"""Bounded-memory MP4 output cadence measurement; never measures TV latency."""
import json
import time


class StreamMetrics:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = self.reported = clock()
        self.header = bytearray()
        self.remaining = 0
        self.kind = None
        self.disabled = False
        self.boxes = self.bytes = 0
        self.first = self.previous = None
        self.max_gap = 0.0

    def feed(self, data):
        self.bytes += len(data)
        view = memoryview(data)
        while view and not self.disabled:
            if self.remaining:
                consumed = min(self.remaining, len(view))
                self.remaining -= consumed
                view = view[consumed:]
                if self.remaining == 0:
                    self._complete()
                continue
            target = 16 if len(self.header) >= 8 and int.from_bytes(self.header[:4], 'big') == 1 else 8
            count = min(target - len(self.header), len(view))
            self.header.extend(view[:count])
            view = view[count:]
            if len(self.header) < target:
                continue
            size = int.from_bytes(self.header[:4], 'big')
            if size == 1 and len(self.header) == 8:
                continue
            if size == 1:
                size = int.from_bytes(self.header[8:16], 'big')
            if size < len(self.header):
                self.disabled = True  # Unknown-length/invalid boxes: telemetry only.
                break
            self.kind = bytes(self.header[4:8])
            self.remaining = size - len(self.header)
            self.header.clear()
            if not self.remaining:
                self._complete()

    def _complete(self):
        if self.kind != b'mdat':
            return
        now = self.clock()
        self.boxes += 1
        if self.first is None:
            self.first = now - self.started
        if self.previous is not None:
            self.max_gap = max(self.max_gap, now - self.previous)
        self.previous = now

    def report(self, final=False):
        now = self.clock()
        if not final and now - self.reported < 5:
            return
        self.reported = now
        print('STREAM_METRICS ' + json.dumps(dict(
            scope='encoder output before HTTP send; NOT capture-to-TV latency',
            elapsed_s=round(now - self.started, 3), bytes=self.bytes,
            complete_media_boxes=self.boxes, first_media_box_s=self.first,
            max_media_box_gap_s=round(self.max_gap, 3), parser_disabled=self.disabled,
            final=final)), flush=True)
