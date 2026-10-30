import struct
import tempfile
import unittest
from pathlib import Path
import zlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from swf_inventory import inventory, read_rect, load_swf


def tag(code, body=b""):
    n = len(body)
    if n < 63:
        return struct.pack("<H", (code << 6) | n) + body
    return struct.pack("<HI", (code << 6) | 63, n) + body


def fixture(compressed=False):
    # RECT nbits=15, xmin=0, xmax=400*20, ymin=0, ymax=300*20.
    rectbits = "01111" + "0" * 15 + format(8000, "015b") + "0" * 15 + format(6000, "015b")
    rect = int(rectbits.ljust((len(rectbits) + 7) // 8 * 8, "0"), 2).to_bytes((len(rectbits) + 7) // 8, "big")
    sprite = struct.pack("<HH", 5, 1) + tag(1) + tag(0)
    symbol = struct.pack("<HH", 1, 5) + b"Player\x00"
    body = rect + struct.pack("<HH", 24 * 256, 1) + tag(39, sprite) + tag(76, symbol) + tag(12, b"\x00") + tag(1) + tag(0)
    uncompressed = b"FWS" + bytes([8]) + struct.pack("<I", 8 + len(body)) + body
    if compressed:
        return b"CWS" + uncompressed[3:8] + zlib.compress(uncompressed[8:])
    return uncompressed


class SWFInventoryTests(unittest.TestCase):
    def test_rect(self):
        data = fixture()
        rect, pos = read_rect(data)
        self.assertEqual(rect, [0, 8000, 0, 6000])
        self.assertEqual(pos, 17)

    def test_fws_and_cws(self):
        with tempfile.TemporaryDirectory() as tmp:
            for compressed in (False, True):
                path = Path(tmp) / "test.swf"
                path.write_bytes(fixture(compressed))
                result = inventory(path)
                self.assertEqual(result["stage"]["width_px"], 400)
                self.assertEqual(result["stage"]["height_px"], 300)
                self.assertEqual(result["stage"]["frame_rate"], 24)
                self.assertEqual(result["stage"]["frame_count"], 1)
                self.assertEqual(result["tag_count_including_sprites"], 7)
                self.assertEqual(result["symbol_class"], [{"character_id": 5, "name": "Player"}])
                self.assertEqual(len(result["scripts"]), 1)
                self.assertEqual(result["characters"][0]["character_id"], 5)

    def test_invalid_length_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.swf"
            path.write_bytes(fixture()[:-1])
            with self.assertRaises(ValueError):
                load_swf(path)

    def test_invalid_signature_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.swf"
            path.write_bytes(b"BAD" + fixture()[3:])
            with self.assertRaises(ValueError):
                load_swf(path)


if __name__ == "__main__":
    unittest.main()
