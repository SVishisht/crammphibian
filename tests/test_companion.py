import shutil

from crammphibian import companion


def test_default_frog_has_every_frame():
    frames = companion.frames()
    for name in companion.FRAMES:
        assert frames[name].startswith("data:image/png;base64,"), name


def test_missing_frames_fall_back_to_idle(tmp_path, monkeypatch):
    shutil.copy(companion.FROG_DIR / "idle.png", tmp_path / "idle.png")
    monkeypatch.setattr(companion, "FROG_DIR", tmp_path)
    frames = companion.frames()
    assert frames["happy"] == frames["idle"]
    assert "lilypad" not in frames  # optional


def test_custom_gif_frame_is_picked_up(tmp_path, monkeypatch):
    shutil.copy(companion.FROG_DIR / "idle.png", tmp_path / "idle.png")
    (tmp_path / "happy.gif").write_bytes(b"GIF89a")
    monkeypatch.setattr(companion, "FROG_DIR", tmp_path)
    assert companion.frames()["happy"].startswith("data:image/gif;base64,")


def test_theme_embeds_the_pixel_font():
    css = companion.theme_css()
    assert "PIXEL_FONT_SRC" not in css
    assert "data:font/woff2;base64," in css


def test_icon_is_scaled_up_crisply():
    img = companion.icon(scale=4)
    assert img.size == (128, 128)
