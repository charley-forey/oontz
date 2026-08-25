"""The share card, as a PNG, from the standard library alone.

An og:image has to be a raster. SVG is ignored by X, Facebook, LinkedIn, iMessage,
Slack and Discord, so the card this site has drawn since cycle 17 has never once been
seen by anybody - the markup was right and the format was unreadable.

Nothing here needs a dependency. A PNG is a signature, a few length-tagged chunks, and
zlib-compressed scanlines; the card itself is rectangles, and the text is rectangles
too. That is the same trade the engine already makes for WAV in oontz.js - hand-write
the container, keep the deploy free of everything else.

Indexed colour (type 3), not truecolour: the card uses six colours, so one byte a pixel
is a third of the data to deflate and the palette costs 18 bytes.

    python web/landing/png.py     # writes /tmp/card.png to look at
"""
import struct
import zlib

W, H = 1200, 630                                 # what every platform expects

# palette indices, in the site's own colours
BG, FG, DIM, OFF, RED, TEAL = range(6)
PALETTE = [(0x07, 0x09, 0x0b),                   # --bg
           (0xf4, 0xf9, 0xfc),                   # --bright
           (0x46, 0x54, 0x5f),                   # --dim
           (0x1b, 0x23, 0x2b),                   # an empty step
           (0xff, 0x3b, 0x3b),                   # the kick
           (0x22, 0xe0, 0xd0)]                   # the hat


def _chunk(typ, data):
    return (struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))


def png(w, h, pixels, palette=PALETTE):
    """pixels: a bytearray of w*h palette indices. Returns the PNG bytes."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)                            # filter 0 (none) on every row
        raw += pixels[y * w:(y + 1) * w]
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + _chunk(b"PLTE", b"".join(struct.pack("BBB", *c) for c in palette))
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + _chunk(b"IEND", b""))
# ponytail: filter 0 only. Adaptive filtering wins little on flat rectangles;
# revisit if a card ever passes ~100KB.


# A 5x7 font, one int per column, low 7 bits top-to-bottom. Enough for a title and
# the "140 bpm · a minor · 4:32 · by someone" line, which is all this card says.
FONT = {
    " ": (0, 0, 0, 0, 0),
    "A": (0x7E, 0x11, 0x11, 0x11, 0x7E), "B": (0x7F, 0x49, 0x49, 0x49, 0x36),
    "C": (0x3E, 0x41, 0x41, 0x41, 0x22), "D": (0x7F, 0x41, 0x41, 0x22, 0x1C),
    "E": (0x7F, 0x49, 0x49, 0x49, 0x41), "F": (0x7F, 0x09, 0x09, 0x09, 0x01),
    "G": (0x3E, 0x41, 0x49, 0x49, 0x7A), "H": (0x7F, 0x08, 0x08, 0x08, 0x7F),
    "I": (0x00, 0x41, 0x7F, 0x41, 0x00), "J": (0x20, 0x40, 0x41, 0x3F, 0x01),
    "K": (0x7F, 0x08, 0x14, 0x22, 0x41), "L": (0x7F, 0x40, 0x40, 0x40, 0x40),
    "M": (0x7F, 0x02, 0x0C, 0x02, 0x7F), "N": (0x7F, 0x04, 0x08, 0x10, 0x7F),
    "O": (0x3E, 0x41, 0x41, 0x41, 0x3E), "P": (0x7F, 0x09, 0x09, 0x09, 0x06),
    "Q": (0x3E, 0x41, 0x51, 0x21, 0x5E), "R": (0x7F, 0x09, 0x19, 0x29, 0x46),
    "S": (0x46, 0x49, 0x49, 0x49, 0x31), "T": (0x01, 0x01, 0x7F, 0x01, 0x01),
    "U": (0x3F, 0x40, 0x40, 0x40, 0x3F), "V": (0x1F, 0x20, 0x40, 0x20, 0x1F),
    "W": (0x7F, 0x20, 0x18, 0x20, 0x7F), "X": (0x63, 0x14, 0x08, 0x14, 0x63),
    "Y": (0x03, 0x04, 0x78, 0x04, 0x03), "Z": (0x61, 0x51, 0x49, 0x45, 0x43),
    "0": (0x3E, 0x51, 0x49, 0x45, 0x3E), "1": (0x00, 0x42, 0x7F, 0x40, 0x00),
    "2": (0x42, 0x61, 0x51, 0x49, 0x46), "3": (0x21, 0x41, 0x45, 0x4B, 0x31),
    "4": (0x18, 0x14, 0x12, 0x7F, 0x10), "5": (0x27, 0x45, 0x45, 0x45, 0x39),
    "6": (0x3C, 0x4A, 0x49, 0x49, 0x30), "7": (0x01, 0x71, 0x09, 0x05, 0x03),
    "8": (0x36, 0x49, 0x49, 0x49, 0x36), "9": (0x06, 0x49, 0x49, 0x29, 0x1E),
    ".": (0x00, 0x60, 0x60, 0x00, 0x00), ",": (0x00, 0x50, 0x30, 0x00, 0x00),
    ":": (0x00, 0x36, 0x36, 0x00, 0x00), "-": (0x08, 0x08, 0x08, 0x08, 0x08),
    "_": (0x40, 0x40, 0x40, 0x40, 0x40), "/": (0x20, 0x10, 0x08, 0x04, 0x02),
    "'": (0x00, 0x05, 0x03, 0x00, 0x00), "!": (0x00, 0x00, 0x5F, 0x00, 0x00),
    "?": (0x02, 0x01, 0x51, 0x09, 0x06), "(": (0x00, 0x1C, 0x22, 0x41, 0x00),
    ")": (0x00, 0x41, 0x22, 0x1C, 0x00), "+": (0x08, 0x08, 0x3E, 0x08, 0x08),
    "#": (0x14, 0x7F, 0x14, 0x7F, 0x14), "·": (0x00, 0x00, 0x08, 0x00, 0x00),
    "&": (0x36, 0x49, 0x55, 0x22, 0x50), "%": (0x23, 0x13, 0x08, 0x64, 0x62),
    "*": (0x14, 0x08, 0x3E, 0x08, 0x14), "=": (0x14, 0x14, 0x14, 0x14, 0x14),
    "[": (0x00, 0x7F, 0x41, 0x41, 0x00), "]": (0x00, 0x41, 0x41, 0x7F, 0x00),
    '"': (0x00, 0x07, 0x00, 0x07, 0x00), "@": (0x3E, 0x41, 0x5D, 0x55, 0x1E),
}


class Card(object):
    """A framebuffer of palette indices with the two primitives the card needs."""

    def __init__(self, w=W, h=H, bg=BG):
        self.w, self.h = w, h
        self.px = bytearray([bg]) * (w * h)

    def rect(self, x, y, w, h, idx):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes([idx]) * (x1 - x0)
        for yy in range(y0, y1):
            self.px[yy * self.w + x0:yy * self.w + x1] = row

    def text(self, s, x, y, scale, idx):
        """Draw s at (x, y). Returns the x it finished at, so lines can chain."""
        for ch in s:
            cols = FONT.get(ch) or FONT.get(ch.upper()) or FONT["?"]
            for cx, bits in enumerate(cols):
                for cy in range(7):
                    if bits >> cy & 1:
                        self.rect(x + cx * scale, y + cy * scale, scale, scale, idx)
            x += 6 * scale                       # 5 columns and a gap
        return x

    def bytes(self):
        return png(self.w, self.h, self.px)


def width_of(s, scale):
    return len(s) * 6 * scale


def fit(s, scale, limit):
    """Trim to what actually fits, so a long title cannot run off the card."""
    n = max(1, limit // (6 * scale))
    return s if len(s) <= n else s[:max(1, n - 1)] + "…".replace("…", ".")


def strip(card, pat, y, colour, x0=80, cell=52, pitch=66):
    """16 steps of a pattern, the same shape the terminal draws."""
    for i in range(16):
        ch = pat[i % len(pat)] if pat else "."
        card.rect(x0 + i * pitch, y, cell, cell,
                  colour if ch not in ".-" else OFF)


def card(title, sub, kick, hat, footer="the whole song is this readable. oontz.sh"):
    """The share card: what it is, the numbers, and its actual drums."""
    c = Card()
    c.text(fit(title.upper(), 10, W - 160), 80, 92, 10, FG)
    c.text(fit(sub, 4, W - 160), 80, 205, 4, DIM)
    strip(c, kick, 300, RED)
    strip(c, hat, 380, TEAL)
    c.text(fit(footer, 4, W - 160), 80, 520, 4, DIM)
    return c.bytes()


def demo():
    """One runnable check. asserts only. Run: python web/landing/png.py"""
    # the container
    b = png(2, 2, bytearray([0, 1, 1, 0]), [(0, 0, 0), (255, 255, 255)])
    assert b.startswith(b"\x89PNG\r\n\x1a\n"), "signature"
    for tag in (b"IHDR", b"PLTE", b"IDAT", b"IEND"):
        assert tag in b, tag
    # every chunk's stored CRC must match a recomputed one, and the scanlines must
    # decompress to exactly h rows of (1 filter byte + w pixels)
    i, seen = 8, []
    while i < len(b):
        n = struct.unpack(">I", b[i:i + 4])[0]
        typ, data = b[i + 4:i + 8], b[i + 8:i + 8 + n]
        crc = struct.unpack(">I", b[i + 8 + n:i + 12 + n])[0]
        assert crc == zlib.crc32(typ + data) & 0xffffffff, ("crc", typ)
        seen.append(typ)
        if typ == b"IDAT":
            raw = zlib.decompress(data)
            assert len(raw) == 2 * (2 + 1), len(raw)
            assert raw[0] == 0 and raw[3] == 0, "each row must carry filter 0"
        i += 12 + n
    assert seen == [b"IHDR", b"PLTE", b"IDAT", b"IEND"], seen

    # the primitives
    c = Card(10, 10)
    c.rect(2, 2, 3, 3, 1)
    assert c.px.count(1) == 9, c.px.count(1)
    c.rect(-5, -5, 3, 3, 2)                      # off-canvas must clip, not wrap
    assert c.px.count(2) == 0, "a rect off the top-left leaked"
    c2 = Card(60, 20)
    c2.text("A", 0, 0, 1, 1)
    assert 0 < c2.px.count(1) < 5 * 7, "the font table is not wired"

    # every character the subtitle can produce must have a glyph, or a real card
    # raises deep inside a crawler request
    for ch in "0123456789abcdefgh#· :.-/minorajby":
        assert FONT.get(ch) or FONT.get(ch.upper()), "no glyph for %r" % ch

    # a real card, including the awkward inputs
    big = card("x" * 80, "140 bpm · f# minor · 4:32 · by someone", "x...x...x...x..x", "..x.x")
    assert len(big) > 1000 and big.startswith(b"\x89PNG"), len(big)
    assert card("", "", "", "").startswith(b"\x89PNG"), "an empty card must still render"
    return "png ok · %d bytes for a full card" % len(big)


if __name__ == "__main__":
    print(demo())
    with open("card.png", "wb") as f:
        f.write(card("warehouse litany", "132 bpm · a minor · 4:12 · by anon",
                     "X...x...X...x..x", "..x...x...x.x.x."))
    print("wrote card.png")
