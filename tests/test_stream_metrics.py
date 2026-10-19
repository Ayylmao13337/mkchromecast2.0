import struct
import unittest
from mkchromecast.stream_metrics import StreamMetrics


def box(kind, data=b''):
    return struct.pack('>I4s', 8 + len(data), kind) + data


class MetricsTests(unittest.TestCase):
    def test_split_headers_and_payload_are_not_stored(self):
        now = [0.0]
        metrics = StreamMetrics(lambda: now[0])
        data = box(b'ftyp', b'isom') + box(b'mdat', b'moofmdat' * 100)
        now[0] = .2
        for byte in data:
            metrics.feed(bytes([byte]))
            self.assertLessEqual(len(metrics.header), 16)
        self.assertEqual(1, metrics.boxes)
        self.assertEqual(.2, metrics.first)
        now[0] = .3
        metrics.feed(box(b'mdat', b'next'))
        self.assertAlmostEqual(.1, metrics.max_gap)
        self.assertEqual(len(data) + 12, metrics.bytes)

    def test_extended_size_and_invalid_input(self):
        metrics = StreamMetrics()
        metrics.feed(struct.pack('>I4sQ', 1, b'mdat', 20) + b'data')
        self.assertEqual(1, metrics.boxes)
        metrics.feed(b'\x00' * 8)
        self.assertTrue(metrics.disabled)
        metrics.feed(b'anything')
        self.assertEqual(1, metrics.boxes)
