"""Draws the default pixel-art frog frames into crammphibian/assets/frog/.

These are placeholders until the real mascot is ready. To use your own art, just
replace the PNGs in crammphibian/assets/frog/ (same file names); this script is
only needed if you want to tweak the default frog.

    python tools/draw_frog.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "crammphibian" / "assets" / "frog"
S = 32  # sprite size in pixels

C = {
    "line": (30, 66, 38, 255),
    "body": (104, 196, 98, 255),
    "shade": (63, 150, 72, 255),
    "light": (160, 226, 132, 255),
    "belly": (226, 244, 186, 255),
    "white": (255, 255, 255, 255),
    "pupil": (28, 32, 30, 255),
    "blush": (247, 152, 172, 255),
    "mouth": (120, 40, 56, 255),
    "tongue": (240, 112, 128, 255),
    "tear": (110, 186, 255, 255),
    "pad": (88, 170, 84, 255),
    "pad_dark": (56, 128, 64, 255),
}


def ell(cx, cy, rx, ry):
    return {(x, y) for x in range(S) for y in range(S)
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0}


def base_shape(squash=0):
    body = ell(16, 21 + squash, 12.5, 8.8 - squash)
    head_l = ell(10, 11.5 + squash, 5.2, 5.2)
    head_r = ell(22, 11.5 + squash, 5.2, 5.2)
    feet = ell(8.5, 29, 4.2, 2) | ell(23.5, 29, 4.2, 2)
    return body | head_l | head_r | feet, body


def draw(face: str, squash: int = 0) -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    px = img.load()
    shape, body = base_shape(squash)
    for x, y in shape:
        px[x, y] = C["body"]
    # bottom-right shading and a top-left shine give it volume
    for x, y in shape:
        if (x, y + 2) not in shape or (x + 2, y) not in shape and y > 16:
            px[x, y] = C["shade"]
    for x, y in ell(16, 25 + squash, 7.5, 4.5 - squash / 2) & shape:
        px[x, y] = C["belly"]
    for x, y in [(6, 15), (7, 14), (7, 15), (8, 14)]:
        if (x, y + squash) in shape:
            px[x, y + squash] = C["light"]
    # outline: any empty pixel touching the shape
    for x in range(S):
        for y in range(S):
            if (x, y) in shape:
                continue
            if any((x + dx, y + dy) in shape for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                px[x, y] = C["line"]

    q = squash
    eyes = [(10, 11 + q), (22, 11 + q)]

    def put(x, y, c):
        if 0 <= x < S and 0 <= y < S:
            px[x, y] = C[c]

    def open_eyes(dx=0, dy=0):
        for ex, ey in eyes:
            for x, y in ell(ex, ey + 0.5, 3.6, 3.6):
                put(x, y, "white")
            for x in (ex - 1 + dx, ex + dx):
                for y in (ey - 1 + dy, ey + dy, ey + 1 + dy):
                    put(x, y, "pupil")
            put(ex - 1 + dx, ey - 1 + dy, "white")  # sparkle

    def closed_eyes(shape_="line"):
        for ex, ey in eyes:
            if shape_ == "happy":  # ^ ^
                for x, y in [(ex - 2, ey + 1), (ex - 1, ey), (ex, ey), (ex + 1, ey + 1)]:
                    put(x, y, "line")
            else:  # -  -
                for x in range(ex - 2, ex + 2):
                    put(x, ey + 1, "line")

    def blush(strong=False):
        for x, y in [(6, 18 + q), (7, 18 + q), (24, 18 + q), (25, 18 + q)]:
            put(x, y, "blush")
        if strong:
            for x, y in [(5, 18 + q), (26, 18 + q)]:
                put(x, y, "blush")

    m = 18 + q  # mouth row
    if face in ("idle", "blink", "sleep"):
        (open_eyes() if face == "idle" else closed_eyes())
        blush()
        for x in range(13, 19):
            put(x, m, "mouth")
        put(12, m - 1, "mouth")
        put(19, m - 1, "mouth")
    elif face == "talk":
        open_eyes()
        blush()
        for x in range(13, 19):
            put(x, m - 1, "mouth")
        for x in range(13, 19):
            put(x, m, "mouth")
        for x in range(14, 18):
            put(x, m + 1, "tongue")
        put(13, m + 1, "mouth")
        put(18, m + 1, "mouth")
        for x in range(14, 18):
            put(x, m + 2, "mouth")
    elif face == "think":
        open_eyes(dx=1, dy=-1)
        blush()
        for x, y in [(15, m), (16, m), (15, m - 1), (16, m - 1)]:
            put(x, y, "mouth")
    elif face == "happy":
        closed_eyes("happy")
        blush(strong=True)
        for x in range(12, 20):
            put(x, m - 1, "mouth")
        for x in range(13, 19):
            put(x, m, "mouth")
        for x in range(14, 18):
            put(x, m + 1, "tongue")
        put(11, m - 2, "mouth")
        put(20, m - 2, "mouth")
    elif face == "sad":
        open_eyes(dy=1)
        for x in range(13, 19):
            put(x, m, "mouth")
        put(12, m + 1, "mouth")
        put(19, m + 1, "mouth")
        put(25, 15 + q, "tear")
        put(25, 16 + q, "tear")
    return img


def lily_pad() -> Image.Image:
    w, h = 48, 12
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    pad = {(x, y) for x in range(w) for y in range(h)
           if ((x + 0.5 - 24) / 22) ** 2 + ((y + 0.5 - 6) / 5) ** 2 <= 1}
    notch = {(x, y) for x, y in pad if y <= 5 and abs((x - 33) - (5 - y) * 0.9) < 1.6}
    pad -= notch
    for x, y in pad:
        px[x, y] = C["pad_dark"] if y >= 8 else C["pad"]
    for x, y in [(10, 4), (12, 3), (14, 3), (30, 8), (32, 8)]:
        if (x, y) in pad:
            px[x, y] = C["light"] if y < 6 else C["pad"]
    for x in range(w):
        for y in range(h):
            if (x, y) not in pad and any((x + dx, y + dy) in pad for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                px[x, y] = C["line"]
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for face in ("idle", "blink", "talk", "think", "happy", "sad", "sleep"):
        draw(face).save(OUT / f"{face}.png")
    lily_pad().save(OUT / "lilypad.png")
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
