# How to replay a photo trace onto the app

Turn a photo (a pose, a sketch, a logo) into an ink drawing on the real
platform.

## Steps

1. Start the driver:

   ```bash
   python3 fieldwork_server.py
   ```

2. Trace the photo. This writes both a preview PNG and a `.strokes.json`
   replay file:

   ```bash
   python3 draw_with_code.py trace --photo sample-pose.jpg --out pose_sketch.png
   # writes pose_sketch.png and pose_sketch.strokes.json
   ```

3. Check `pose_sketch.png`. Happy with it? Replay onto the app:

   ```bash
   curl -X POST 127.0.0.1:7766/replay -H 'Content-Type: application/json' \
     -d @pose_sketch.strokes.json
   ```

   Not happy? Wipe and retry with different knobs:

   ```bash
   curl -X POST 127.0.0.1:7766/clear -d '{}'
   ```

## Knobs

| Flag | Default | Effect |
|---|---|---|
| `--size WxH` | `1000x1400` | Working resolution; `/replay` rescales to the page format |
| `--edge-pct` | `6.0` | Edge threshold percentile: lower = more outlines |
| `--max-strokes` | `9000` | Cap on total strokes |
| `--density` | `1.0` | Hatching density multiplier |
| `--shadow-level` | `0.55` | How dark a region must be to get hatching |
| `--seed` | random | Fix for reproducible output |
| `--strokes PATH` | `<out>.strokes.json` | Custom strokes-file path |

## Tips

- Portrait source? Set the app to a portrait format first:
  `curl -X POST 127.0.0.1:7766/format -d '{"format": "4:5"}'`
- For a live-drawing feel, replay at human speed:
  `curl -X POST 127.0.0.1:7766/replay -H 'Content-Type: application/json' \
    -d '{"strokes": ..., "pace_ms": 30}'` (or edit the JSON file)
- The trace style is sketchy cross-hatching, not flat vector fills. That is
  the look; lean into it.

Sample output: ![trace mode sample](images/sample_trace.png)
