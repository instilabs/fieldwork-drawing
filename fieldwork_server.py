#!/usr/bin/env python3
"""
fieldwork_server.py - drive https://field-work-drawing.web.app/ programmatically.

Launches a real browser (Playwright Chromium), loads the field:work drawing
app, and exposes a small local HTTP API. Every stroke is executed as genuine
trusted pointer input on the app's canvas - the app cannot tell it apart from
a mouse, so everything (Draw / Paint / Boids / Erase, the living "system"
presets, PNG export, video recording) behaves exactly as for a human.

Why this shape: the app is a closed p5.js instance-mode bundle with no API,
no import/export and no console hooks (checked its index.html + js/*.js), so
the honest way in is through the front door: real input events.

Setup (macOS):
  pip install playwright
  python3 -m playwright install chromium
  python3 fieldwork_server.py                # visible browser, port 7766
  python3 fieldwork_server.py --headless     # no window (for testing)

Then:
  curl 127.0.0.1:7766/health
  curl -X POST 127.0.0.1:7766/stroke -H 'Content-Type: application/json' \
       -d '{"points": [[100,100],[400,300],[700,200]], "size": 12, "ink": "#1a1a1a"}'
  curl -X POST 127.0.0.1:7766/replay -H 'Content-Type: application/json' \
       -d @drawing.strokes.json
  curl 127.0.0.1:7766/png -o drawing.png        # the app's own export
  curl 127.0.0.1:7766/screenshot -o screen.png  # what's on screen now

Coordinates for /stroke and /replay are PAGE units of the app's current
format (e.g. 1080x1350 for 4:5). /replay accepts a stroke-list JSON (the
shape draw_with_code.py --strokes writes) and scales it into the page.

API summary:
  GET  /health        -> {ok, format, page_size}
  GET  /state         -> current tool, brush, format as read from the page
  POST /format        {format: "1:1"|"4:5"|"5:4"|"9:16"|"16:9"}
  POST /tool          {tool: "draw"|"paint"|"boids"|"erase"}
  POST /brush         {ink?: "#rrggbb", size?: 1-60, opacity?: 0.05-1}
  POST /stroke        {points: [[x,y],...], ink?, size?, opacity?, tool?, pace_ms?}
  POST /paint         {points: [[x,y],...], shape?: o|x|+|square|diamond, ink?, size?}
  POST /boids         {points: [[x,y],...], heading?, speed?, curl?, shape?}
  POST /erase         {points: [[x,y],...], size?}
  POST /replay        {strokes: [...], source_size?: [w,h], clear_first?: bool,
                       pace_ms?: int, max_strokes?: int, width_scale?: float}
  POST /undo          {}          POST /clear {} (clears the whole drawing)
  GET  /png           -> the app's own PNG export (full page resolution)
  GET  /screenshot    -> PNG of the page area as it appears on screen
"""

import argparse
import json
import queue
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

APP_URL = "https://field-work-drawing.web.app/"

# js/state.js FORMATS - page resolution per format.
FORMATS = {
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "5:4": (1350, 1080),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}

# Captures the page->screen transform the app applies to its canvas each
# frame (js/view.js applyView calls ctx.setTransform), so API page units can
# be mapped to real screen pixels without reimplementing the view math.
INIT_JS = r"""
(() => {
  const orig = CanvasRenderingContext2D.prototype.setTransform;
  window.__fwtf = null;
  CanvasRenderingContext2D.prototype.setTransform = function (a, b, c, d, e, f) {
    try {
      if (this.canvas && this.canvas.closest && this.canvas.closest('#frame')) {
        window.__fwtf = { a, d, e, f };
      }
    } catch (_) {}
    return orig.apply(this, arguments);
  };
})();
"""

TF_JS = r"""
() => {
  const c = document.querySelector('#frame canvas');
  if (!c || !window.__fwtf) return null;
  const r = c.getBoundingClientRect();
  return {
    tf: window.__fwtf,
    rect: { left: r.left, top: r.top, width: r.width, height: r.height },
    canvasW: c.width,
  };
}
"""

STATE_JS = r"""
() => {
  const val = (id) => { const el = document.getElementById(id); return el && el.value; };
  const tool = document.querySelector('[data-tool][aria-pressed="true"]');
  return {
    tool: tool && tool.getAttribute('data-tool'),
    format: val('format'),
    ink: val('ink'),
    size: val('size'),
    opacity: val('opacity'),
    eraser_size: val('eraser-size'),
    paper: val('paper'),
  };
}
"""


class BrowserDriver:
    """Owns the browser. All page calls run on one worker thread (Playwright
    sync API is single-threaded); HTTP handlers submit jobs to it."""

    def __init__(self, headless=False, url=APP_URL):
        self.url = url
        self.headless = headless
        self.jobs = queue.Queue()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        self.ready.wait(timeout=90)
        if self.error:
            raise RuntimeError(self.error)

    def _worker(self):
        try:
            self._pw = sync_playwright().start()
            self.browser = self._pw.chromium.launch(headless=self.headless)
            self.context = self.browser.new_context(
                viewport={"width": 1440, "height": 960},
                device_scale_factor=1,
                accept_downloads=True,
            )
            self.context.add_init_script(INIT_JS)
            self.page = self.context.new_page()
            self.page.goto(self.url, wait_until="load", timeout=60000)
            self.page.wait_for_selector("#frame canvas", timeout=30000)
            # wait until the app has applied a view transform at least once
            for _ in range(100):
                if self.page.evaluate("() => !!window.__fwtf"):
                    break
                time.sleep(0.1)
            self.ready.set()
        except Exception:
            self.error = traceback.format_exc()
            self.ready.set()
            return
        while True:
            job = self.jobs.get()
            if job is None:
                break
            fn, kwargs, out = job
            try:
                out.put((True, fn(self, **kwargs)))
            except Exception:
                out.put((False, traceback.format_exc()))

    def call(self, fn, **kwargs):
        out = queue.Queue()
        self.jobs.put((fn, kwargs, out))
        ok, val = out.get()
        if not ok:
            raise RuntimeError(val)
        return val

    # ---------------------------------------------------------- primitives

    def _tf(self):
        m = self.page.evaluate(TF_JS)
        if not m:
            raise RuntimeError("no transform captured - is the app loaded?")
        return m

    def page_to_screen(self, x, y):
        m = self._tf()
        dpr = m["canvasW"] / m["rect"]["width"]
        sx = m["rect"]["left"] + (m["tf"]["a"] * x + m["tf"]["e"]) / dpr
        sy = m["rect"]["top"] + (m["tf"]["d"] * y + m["tf"]["f"]) / dpr
        return sx, sy

    def set_control(self, cid, value):
        self.page.evaluate(
            """([cid, value]) => {
                const el = document.getElementById(cid);
                if (!el) throw new Error('no control #' + cid);
                el.value = value;
                el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true}));
            }""",
            [cid, str(value)],
        )

    def click_choice(self, attr, value):
        self.page.click(f"[data-{attr}='{value}']")

    # Batched synthetic PointerEvents dispatched at the #live overlay (the
    # element js/input.js listens on). The app does not check isTrusted, and
    # setPointerCapture failure is caught by the app, so this is equivalent
    # to real input - and hundreds of times faster than CDP mouse calls,
    # which is what makes multi-thousand-stroke replays practical.
    DISPATCH_JS = """
    async (args) => {
      const el = document.getElementById('live');
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const opts = (x, y, extra) => Object.assign({
        pointerId: 1, pointerType: 'mouse', isPrimary: true,
        clientX: x, clientY: y, bubbles: true, cancelable: true,
        button: 0, buttons: 1, pressure: 0.5,
      }, extra || {});
      let done = 0;
      for (const pts of args.strokes) {
        if (!pts.length) continue;
        el.dispatchEvent(new PointerEvent('pointerdown', opts(pts[0][0], pts[0][1])));
        for (let i = 1; i < pts.length; i++) {
          el.dispatchEvent(new PointerEvent('pointermove', opts(pts[i][0], pts[i][1])));
        }
        const last = pts[pts.length - 1];
        el.dispatchEvent(new PointerEvent('pointerup', opts(last[0], last[1], { buttons: 0 })));
        done++;
        if (args.pace_ms) await sleep(args.pace_ms);
        else if (done % 50 === 0) await sleep(0);  // let the 15fps renderer breathe
      }
      return done;
    }
    """

    def gestures_batch(self, strokes_screen, pace_ms=0, chunk=500):
        """ strokes_screen: list of strokes, each a list of [screenX, screenY]. """
        done = 0
        for i in range(0, len(strokes_screen), chunk):
            part = strokes_screen[i:i + chunk]
            done += self.page.evaluate(
                self.DISPATCH_JS, {"strokes": part, "pace_ms": pace_ms})
        return done

    def page_points_to_screen(self, pts):
        m = self._tf()
        dpr = m["canvasW"] / m["rect"]["width"]
        return [
            [m["rect"]["left"] + (m["tf"]["a"] * x + m["tf"]["e"]) / dpr,
             m["rect"]["top"] + (m["tf"]["d"] * y + m["tf"]["f"]) / dpr]
            for x, y in pts
        ]

    def gesture(self, points, pace_ms=0):
        """One pointer gesture through page-unit points, as a real mouse."""
        if len(points) < 1:
            return
        pts = [self.page_to_screen(x, y) for x, y in points]
        self.page.mouse.move(pts[0][0], pts[0][1])
        self.page.mouse.down()
        try:
            for sx, sy in pts[1:]:
                self.page.mouse.move(sx, sy)
                if pace_ms:
                    time.sleep(pace_ms / 1000.0)
        finally:
            self.page.mouse.up()


# ------------------------------------------------------------------ actions

def act_state(d):
    return d.call(lambda d: d.page.evaluate(STATE_JS))


def act_format(d, format):
    d.call(lambda d: d.page.select_option("#format", format))


def act_tool(d, tool):
    d.call(lambda d: d.click_choice("tool", tool))


def act_brush(d, ink=None, size=None, opacity=None):
    def go(d):
        if ink is not None:
            d.set_control("ink", ink)
        if size is not None:
            d.set_control("size", max(1, min(60, round(size))))
        if opacity is not None:
            d.set_control("opacity", opacity)
    d.call(go)


def act_stroke(d, points, tool=None, ink=None, size=None, opacity=None, pace_ms=0):
    def go(d):
        if tool:
            d.click_choice("tool", tool)
        if ink is not None:
            d.set_control("ink", ink)
        if size is not None:
            d.set_control("size", max(1, min(60, round(size))))
        if opacity is not None:
            d.set_control("opacity", opacity)
        d.gesture(points, pace_ms=pace_ms)
        return {"points": len(points)}
    return d.call(go)


def act_paint(d, points, shape=None, ink=None, size=None):
    def go(d):
        d.click_choice("tool", "paint")
        if shape:
            d.click_choice("shape", shape)
        if ink is not None:
            d.set_control("ink", ink)
        if size is not None:
            d.set_control("size", max(1, min(60, round(size))))
        d.gesture(points)
        return {"points": len(points)}
    return d.call(go)


def act_boids(d, points, heading=None, speed=None, curl=None, shape=None, ink=None, size=None):
    def go(d):
        d.click_choice("tool", "boids")
        if shape:
            d.click_choice("boid-shape", shape)
        if heading is not None:
            d.set_control("boid-heading", heading)
        if speed is not None:
            d.set_control("boid-speed", speed)
        if curl is not None:
            d.set_control("boid-curl", curl)
        if ink is not None:
            d.set_control("ink", ink)
        if size is not None:
            d.set_control("size", max(1, min(60, round(size))))
        d.gesture(points)
        return {"points": len(points)}
    return d.call(go)


def act_erase(d, points, size=None):
    def go(d):
        d.click_choice("tool", "erase")
        if size is not None:
            d.set_control("eraser-size", size)
        d.gesture(points)
        return {"points": len(points)}
    return d.call(go)


def act_replay(d, strokes, source_size=None, clear_first=False, pace_ms=6,
               max_strokes=None, width_scale=1.0, opacity=None):
    def go(d):
        if clear_first and d.page.is_enabled("#clear"):
            d.page.click("#clear")
            d.page.click("#clear-confirm")
        d.click_choice("tool", "draw")
        fmt = d.page.evaluate("() => document.getElementById('format').value")
        pw, ph = FORMATS.get(fmt, (1080, 1350))
        if source_size:
            sw, sh = source_size
        else:
            sw = max(max(p[0] for p in s["points"]) for s in strokes)
            sh = max(max(p[1] for p in s["points"]) for s in strokes)
        scale = min(pw / sw, ph / sh)
        ox = (pw - sw * scale) / 2
        oy = (ph - sh * scale) / 2

        n = 0
        last_ink = object()
        last_size = object()
        t0 = time.time()
        # group consecutive strokes by (ink, size) so brush control changes
        # (DOM round trips) happen once per group, then batch-dispatch each
        # group as synthetic pointer events in one page.evaluate call.
        work = strokes[: max_strokes or len(strokes)]
        groups = []
        for s in work:
            ink = s.get("color") or s.get("ink") or "#1a1a1a"
            wdt = s.get("width", 3) * scale * width_scale
            size = max(1, min(60, round(wdt)))
            pts = [[x * scale + ox, y * scale + oy] for x, y in s["points"]]
            if groups and groups[-1][0] == ink and groups[-1][1] == size:
                groups[-1][2].append(pts)
            else:
                groups.append((ink, size, [pts]))
        for ink, size, group in groups:
            if ink != last_ink:
                d.set_control("ink", ink)
                last_ink = ink
            if size != last_size:
                d.set_control("size", size)
                last_size = size
            batch = [d.page_points_to_screen(pts) for pts in group]
            n += d.gestures_batch(batch, pace_ms=pace_ms)
        return {"replayed": n, "seconds": round(time.time() - t0, 1),
                "page": [pw, ph], "scale": round(scale, 4)}
    return d.call(go)


def act_undo(d):
    d.call(lambda d: d.page.click("#undo"))


def act_clear(d):
    def go(d):
        if d.page.is_enabled("#clear"):
            d.page.click("#clear")
            d.page.click("#clear-confirm")
    d.call(go)


def act_png(d):
    def go(d):
        d.page.click("#export-open")
        with d.page.expect_download(timeout=15000) as dl:
            d.page.click("#save-png")
        path = dl.value.path()
        with open(path, "rb") as f:
            data = f.read()
        d.page.click("#export-close")
        return data
    return d.call(go)


def act_screenshot(d):
    def go(d):
        # the screen canvas repaints at 15fps; give just-committed marks a
        # few frames to appear before capturing
        time.sleep(0.4)
        m = d._tf()
        return d.page.screenshot(clip={
            "x": m["rect"]["left"], "y": m["rect"]["top"],
            "width": m["rect"]["width"], "height": m["rect"]["height"],
        })
    return d.call(go)


# ------------------------------------------------------------------- http

DRIVER = None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj=None, raw=None, ctype="application/json"):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype if raw is not None else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode())

    def _run(self, fn, **kw):
        try:
            return fn(DRIVER, **kw), None
        except Exception as e:
            return None, str(e)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/health":
            st, err = self._run(act_state)
            fmt = st and st.get("format")
            self._send(200, {"ok": err is None, "url": APP_URL,
                             "format": fmt, "page_size": FORMATS.get(fmt)})
        elif self.path == "/state":
            st, err = self._run(act_state)
            self._send(500 if err else 200, err or st)
        elif self.path == "/png":
            data, err = self._run(act_png)
            self._send(500, {"error": err}) if err else self._send(200, raw=data, ctype="image/png")
        elif self.path == "/screenshot":
            data, err = self._run(act_screenshot)
            self._send(500, {"error": err}) if err else self._send(200, raw=data, ctype="image/png")
        else:
            self._send(404, {"error": "unknown endpoint", "see": "module docstring"})

    def do_POST(self):
        try:
            b = self._body()
        except Exception:
            self._send(400, {"error": "bad JSON body"})
            return
        routes = {
            "/format": lambda: act_format(DRIVER, **b),
            "/tool": lambda: act_tool(DRIVER, **b),
            "/brush": lambda: act_brush(DRIVER, **b),
            "/stroke": lambda: act_stroke(DRIVER, **b),
            "/paint": lambda: act_paint(DRIVER, **b),
            "/boids": lambda: act_boids(DRIVER, **b),
            "/erase": lambda: act_erase(DRIVER, **b),
            "/replay": lambda: act_replay(DRIVER, **b),
            "/undo": lambda: act_undo(DRIVER),
            "/clear": lambda: act_clear(DRIVER),
        }
        fn = routes.get(self.path)
        if not fn:
            self._send(404, {"error": "unknown endpoint"})
            return
        try:
            r = fn()
            self._send(200, {"ok": True, "result": r if r is not None else "done"})
        except Exception as e:
            self._send(500, {"error": str(e)})


def main():
    global DRIVER
    ap = argparse.ArgumentParser(description="HTTP driver for field-work-drawing.web.app")
    ap.add_argument("--port", type=int, default=7766)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--url", default=APP_URL)
    args = ap.parse_args()

    DRIVER = BrowserDriver(headless=args.headless, url=args.url)
    print(f"field:work app loaded ({args.url})")
    print(f"API on http://127.0.0.1:{args.port}  -  endpoints in the module docstring")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
