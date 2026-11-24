# Crammy's sprites

These PNGs are Crammy, the frog in the corner of the app. Replace any of them with
your own art (same file name) and restart the app.

| File | When it shows |
|---|---|
| `idle.png` | Resting. Also used as the tab icon and answer avatar, and for any frame you leave out |
| `blink.png` | A quick blink every few seconds |
| `talk.png` | Mouth open; alternates with `idle.png` while Crammy talks or an answer streams in |
| `think.png` | While the app is searching or the model is working |
| `happy.png` | Hovered, clicked, good quiz scores, finished notes and cards |
| `sad.png` | Errors and low quiz scores |
| `sleep.png` | After a minute of no activity, or when you tell Crammy to nap |
| `lilypad.png` | Optional pad under the frog (48×12). Delete it to have no pad |

Tips:

- Frames are drawn at 32×32 and shown at 3× (2× on phones) with no smoothing, so
  pixel art stays crisp. Other square sizes work too; they're scaled to fit.
- Keep the feet at the same spot in every frame so the frog doesn't jump around
  when frames switch.
- `.gif` and `.webp` work as well (e.g. an animated `idle.gif`); if both exist, `.png` wins.
- `tools/draw_frog.py` drew these defaults; you don't need it for your own art.
