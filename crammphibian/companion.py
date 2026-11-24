"""Crammy, the pixel-art frog that lives in the corner of the app.

The frog is plain HTML/CSS/JS (assets/companion.*) injected once into the page
and kept alive across Streamlit reruns. Python only configures it and sends it
lines to say:

    companion.mount(tips)                         # once per run, near the top
    companion.say("Nice work!", mood="happy", key="quiz-3")

Swapping the art: replace the images in assets/frog/ (idle, blink, talk, think,
happy, sad, sleep, and optionally lilypad). PNG, GIF or WebP all work; pixel art
is drawn without smoothing. See assets/frog/README.md.
"""

from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).with_name("assets")
FROG_DIR = ASSETS / "frog"
FONT = ASSETS / "fonts" / "PixelifySans.woff2"
NAME = "Crammy"
FRAMES = ("idle", "blink", "talk", "think", "happy", "sad", "sleep", "lilypad")
MOODS = ("idle", "talk", "think", "happy", "sad", "sleep")
_MIME = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".woff2": "font/woff2"}

THINKING = [
    "Flipping through your notes",
    "Hopping between slides",
    "Hmm, let me check the pages",
    "Looking for the best passages",
]
WRITING = ["Writing it up", "Ribbit, here it comes", "Croaking out an answer"]


@lru_cache(maxsize=64)
def _data_uri(path: Path, _mtime: float) -> str:
    mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def data_uri(path: Path) -> str:
    return _data_uri(path, path.stat().st_mtime)


def frame_path(name: str) -> Path | None:
    for ext in (".png", ".gif", ".webp"):
        p = FROG_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


def frames() -> dict[str, str]:
    """Frame name -> data URI. Missing frames fall back to idle (lilypad is optional)."""
    out = {name: data_uri(p) for name in FRAMES if (p := frame_path(name))}
    for name in FRAMES[:-1]:
        if name not in out and "idle" in out:
            out[name] = out["idle"]
    return out


def icon(scale: int = 4):
    """The idle frame scaled up without blurring, for the tab icon and chat avatar."""
    p = frame_path("idle")
    if p is None:
        return "🐸"
    from PIL import Image

    img = Image.open(p).convert("RGBA")
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def _read(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def theme_css() -> str:
    """The app's pond theme with the pixel font embedded (works offline)."""
    font = f"url({data_uri(FONT)}) format('woff2')" if FONT.exists() else "local('Pixelify Sans')"
    return _read("theme.css").replace("PIXEL_FONT_SRC", font)


def _bootstrap(js: str) -> str:
    """Runs inside a 0-height component iframe and reaches into the app page (same origin)."""
    return f"""<script>
(function () {{
  var P = window.parent, D;
  try {{ D = P.document; }} catch (e) {{ return; }}
  {js}
}})();
</script>"""


def _html(body: str) -> None:
    import streamlit.components.v1 as components

    components.html(body, height=0)


def mount(tips: list[str]) -> None:
    """Puts the frog on the page (first run) and updates its sprites and tips."""
    config = {"name": NAME, "frames": frames(), "tips": tips, "thinking": THINKING, "writing": WRITING}
    js = f"""
  var css = {json.dumps(_read("companion.css"))};
  var tag = D.getElementById("crammy-style");
  if (!tag) {{ tag = D.createElement("style"); tag.id = "crammy-style"; D.head.appendChild(tag); }}
  if (tag.textContent !== css) tag.textContent = css;
  if (!P.__crammy) {{
    var s = D.createElement("script");
    s.textContent = {json.dumps(_read("companion.js"))};
    D.head.appendChild(s);
  }}
  P.__crammy && P.__crammy.configure({json.dumps(config)});
"""
    _html(_bootstrap(js))


def say(text: str, mood: str = "talk", key: str | None = None, hold_ms: int | None = None) -> None:
    """Makes the frog say something. Each key is said once per page load (reruns don't repeat it)."""
    if mood not in MOODS:
        mood = "talk"
    key = key or hashlib.sha1(f"{mood}:{text}".encode()).hexdigest()[:12]
    opts = {"mood": mood, "id": key, **({"hold": hold_ms} if hold_ms else {})}
    js = f"""
  var go = function (n) {{
    if (P.__crammy) P.__crammy.say({json.dumps(text)}, {json.dumps(opts)});
    else if (n < 40) setTimeout(function () {{ go(n + 1); }}, 50);
  }};
  go(0);
"""
    _html(_bootstrap(js))
