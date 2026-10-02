/* The room: a library in the dark, revealed by your cursor.
   Ported from docs/cognify-prototype.html. All drawing lives here; React only supplies the elements. */

export type RoomElements = {
  stage: HTMLElement;
  scene: HTMLCanvasElement;
  motes: HTMLCanvasElement;
  sparks: HTMLCanvasElement;
  cursor: HTMLElement;
  veil: HTMLElement;
  flash: HTMLElement;
};

type Mote = { x: number; y: number; r: number; vx: number; vy: number; p: number };
type Spark = { x: number; y: number; vx: number; vy: number; life: number; r: number; c: number[] };

const root = () => document.documentElement;
const cssVar = (v: string) => getComputedStyle(root()).getPropertyValue(v).trim();
const rgb = (h: string): number[] => {
  const n = parseInt(h.replace("#", ""), 16);
  return [n >> 16, (n >> 8) & 255, n & 255];
};
const rgba = (h: string, a: number) => {
  const c = rgb(h);
  return `rgba(${c[0]},${c[1]},${c[2]},${a})`;
};
const shade = (h: string, f: number) => {
  const c = rgb(h).map((v) => Math.max(0, Math.min(255, v * f)) | 0);
  return `rgb(${c[0]},${c[1]},${c[2]})`;
};
// Small seeded random generator, so the bookshelves look the same every time.
const rng = (seed: number) => () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;

function sizeCanvas(c: HTMLCanvasElement, scale: number) {
  const dpr = Math.min(window.devicePixelRatio || 1, scale);
  c.width = Math.round(innerWidth * dpr);
  c.height = Math.round(innerHeight * dpr);
  const x = c.getContext("2d")!;
  x.setTransform(dpr, 0, 0, dpr, 0, 0);
  return x;
}

class Room {
  private el: RoomElements | null = null;
  private reduce = false;
  private touch = false;
  private ambient = true;
  private raf = 0;
  private motes: Mote[] = [];
  private mx: CanvasRenderingContext2D | null = null;
  private cx = 0;
  private cy = 0;
  private tx = 0;
  private ty = 0;
  private moved = false;
  private resizeTimer = 0;
  private themeTimer = 0;
  private last = 0; // time of the last drawn frame
  private paused = false; // the page is covered (Progress drawer, seal): nothing here can be seen moving
  private visible = true;
  private accent2 = [255, 255, 255]; // mote colour, read once per theme (reading CSS every frame is slow)

  private onMove = (e: PointerEvent) => {
    if (e.pointerType === "touch" || this.reduce || !this.el) return;
    this.tx = e.clientX;
    this.ty = e.clientY;
    if (!this.moved) {
      this.moved = true;
      this.el.cursor.style.opacity = this.ambient ? "1" : "0";
    }
  };

  private onVisibility = () => {
    this.visible = document.visibilityState === "visible";
    this.resume();
  };

  /** Stop the room while it is covered; it keeps showing its last frame. */
  setPaused(paused: boolean) {
    this.paused = paused;
    this.resume();
  }

  private resume() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    if (!this.el || this.reduce || this.paused || !this.visible) return;
    this.last = 0;
    this.raf = requestAnimationFrame(this.frame);
  }

  private onResize = () => {
    clearTimeout(this.resizeTimer);
    this.resizeTimer = window.setTimeout(() => this.paint(), 160);
  };

  /** Start drawing. Returns a function that stops everything again. */
  start(el: RoomElements): () => void {
    this.el = el;
    this.reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.touch = matchMedia("(hover: none)").matches;
    this.cx = this.tx = innerWidth * 0.72;
    this.cy = this.ty = innerHeight * 0.26;
    this.moved = false;
    this.paint();
    el.veil.style.transform = `translate(${this.cx}px,${this.cy}px)`;
    el.cursor.style.transform = `translate(${this.cx}px,${this.cy}px)`;
    el.cursor.style.opacity = this.touch ? "1" : "0";
    this.visible = document.visibilityState === "visible";
    // Reduced motion: one still frame of dust, no drifting, no breathing lights.
    if (this.reduce) this.drawMotes(0);
    this.resume();
    addEventListener("pointermove", this.onMove, { passive: true });
    addEventListener("resize", this.onResize);
    document.addEventListener("visibilitychange", this.onVisibility);
    return () => {
      cancelAnimationFrame(this.raf);
      document.removeEventListener("visibilitychange", this.onVisibility);
      clearTimeout(this.resizeTimer);
      clearTimeout(this.themeTimer);
      removeEventListener("pointermove", this.onMove);
      removeEventListener("resize", this.onResize);
      this.el = null;
    };
  }

  private paint() {
    this.drawScene();
    this.sizeMotes();
    if (this.reduce || this.paused) this.drawMotes(0);
  }

  private drawScene() {
    if (!this.el) return;
    const W = innerWidth;
    const H = innerHeight;
    const scene = this.el.scene;
    const out = sizeCanvas(scene, 1.25);
    // Draw the shelves off screen first, then copy them over once with the blur baked in.
    // A live CSS blur on a moving full-screen layer is what made big screens slow.
    const buffer = document.createElement("canvas");
    buffer.width = scene.width;
    buffer.height = scene.height;
    const x = buffer.getContext("2d")!;
    const dpr = scene.width / W;
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    const r = rng(20261001);
    const spines = ["--sp1", "--sp2", "--sp3", "--sp4", "--sp5", "--sp6"].map(cssVar);
    const accent = cssVar("--accent");
    const wood = cssVar("--sp3");
    const g = x.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, cssVar("--ground-3"));
    g.addColorStop(0.6, cssVar("--ground-2"));
    g.addColorStop(1, cssVar("--ground"));
    x.fillStyle = g;
    x.fillRect(0, 0, W, H);
    const shelfH = Math.max(176, H / 4.3);
    for (let y = 6; y < H + shelfH; y += shelfH) {
      let px = -14;
      while (px < W + 20) {
        if (r() < 0.035) {
          px += 26 + r() * 52;
          continue;
        }
        const w = 11 + r() * 24;
        const h = shelfH * (0.56 + r() * 0.34);
        const c = spines[(r() * spines.length) | 0];
        const lean = r() < 0.05 ? (r() - 0.5) * 0.3 : 0;
        const base = y + shelfH - 17;
        x.save();
        x.translate(px + w / 2, base);
        x.rotate(lean);
        const gg = x.createLinearGradient(-w / 2, 0, w / 2, 0);
        gg.addColorStop(0, shade(c, 0.5));
        gg.addColorStop(0.3, shade(c, 1.2));
        gg.addColorStop(0.7, shade(c, 0.92));
        gg.addColorStop(1, shade(c, 0.42));
        x.fillStyle = gg;
        x.fillRect(-w / 2, -h, w, h);
        x.fillStyle = rgba(accent, 0.16);
        x.fillRect(-w / 2, -h, w, 2);
        if (r() < 0.75) {
          x.fillStyle = rgba(accent, 0.65);
          x.fillRect(-w / 2 + 1.5, -h * 0.16, w - 3, 2);
          x.fillRect(-w / 2 + 1.5, -h * 0.82, w - 3, 2);
          if (r() < 0.5) x.fillRect(-w / 2 + 3, -h * 0.52, w - 6, h * 0.07);
        }
        x.restore();
        px += w + (r() < 0.15 ? 2.5 : 0.5);
      }
      const wg = x.createLinearGradient(0, y + shelfH - 17, 0, y + shelfH);
      wg.addColorStop(0, shade(wood, 1.15));
      wg.addColorStop(1, shade(wood, 0.38));
      x.fillStyle = wg;
      x.fillRect(0, y + shelfH - 17, W, 17);
      x.fillStyle = rgba(accent, 0.25);
      x.fillRect(0, y + shelfH - 17, W, 1.5);
      x.fillStyle = "rgba(0,0,0,.5)";
      x.fillRect(0, y + shelfH, W, 8);
    }
    // Soft bokeh lamps, no window or frame: the room stays an atmosphere, not a picture.
    x.globalCompositeOperation = "lighter";
    for (let i = 0; i < 46; i++) {
      const cx = W * (0.1 + 0.85 * r());
      const cy = H * (0.55 * r() * r());
      const rad = 12 + r() * 46;
      const a = 0.05 + r() * 0.14;
      const rg = x.createRadialGradient(cx, cy, 0, cx, cy, rad);
      rg.addColorStop(0, rgba(accent, a));
      rg.addColorStop(0.75, rgba(accent, a * 0.55));
      rg.addColorStop(1, rgba(accent, 0));
      x.fillStyle = rg;
      x.beginPath();
      x.arc(cx, cy, rad, 0, 6.3);
      x.fill();
    }
    x.globalCompositeOperation = "source-over";

    out.setTransform(1, 0, 0, 1, 0, 0);
    // Not every browser supports filters on a canvas; those keep the CSS blur instead.
    const canFilter = typeof (out as { filter?: unknown }).filter === "string";
    if (canFilter) {
      out.filter = `blur(${(2.6 * dpr).toFixed(2)}px) saturate(1.1)`;
      out.drawImage(buffer, 0, 0);
      out.filter = "none";
      scene.style.filter = "none";
    } else {
      out.drawImage(buffer, 0, 0);
      scene.style.filter = "";
    }
    this.accent2 = rgb(cssVar("--accent-2"));
  }

  // Dust motes, brighter where the light is.
  private sizeMotes() {
    if (!this.el) return;
    // The motes canvas is redrawn every frame, so keep it at normal resolution: the dots are tiny anyway.
    this.mx = sizeCanvas(this.el.motes, 0.75);
    this.motes = Array.from({ length: Math.round(innerWidth / 24) }, () => ({
      x: Math.random() * innerWidth,
      y: Math.random() * innerHeight,
      r: 0.5 + Math.random() * 1.7,
      vx: (Math.random() - 0.3) * 0.12,
      vy: -0.04 - Math.random() * 0.15,
      p: Math.random() * 6.28,
    }));
  }

  private frame = (t: number) => {
    const el = this.el;
    if (!el || !this.mx) return;
    // About 24 frames a second is plenty for drifting dust and a slow light.
    const elapsed = t - this.last;
    if (this.last && elapsed < 40) {
      this.raf = requestAnimationFrame(this.frame);
      return;
    }
    const steps = this.last ? Math.min(elapsed / 16.67, 5) : 1;
    this.last = t; // how many 60 fps frames this one stands for
    if (this.touch && !this.reduce) {
      // Touch screens have no cursor, so the light drifts by itself.
      this.tx = innerWidth * (0.5 + 0.38 * Math.sin(t / 5200));
      this.ty = innerHeight * (0.36 + 0.26 * Math.cos(t / 6900));
    }
    const dx = this.tx - this.cx;
    const dy = this.ty - this.cy;
    if (Math.abs(dx) > 0.15 || Math.abs(dy) > 0.15) {
      const ease = 1 - Math.pow(1 - 0.09, steps);
      this.cx += dx * ease;
      this.cy += dy * ease;
      // The dark veil has a soft hole in it; moving it is a cheap GPU move, not a repaint.
      el.veil.style.transform = `translate(${this.cx.toFixed(1)}px,${this.cy.toFixed(1)}px)`;
      el.cursor.style.transform = `translate(${this.cx.toFixed(1)}px,${this.cy.toFixed(1)}px)`;
      const nx = this.cx / innerWidth - 0.5;
      const ny = this.cy / innerHeight - 0.5;
      el.scene.style.transform = `scale(1.05) translate(${(-nx * 16).toFixed(1)}px,${(-ny * 10).toFixed(1)}px)`;
    }
    this.drawMotes(steps);
    this.raf = requestAnimationFrame(this.frame);
  };

  /** Dust motes, brighter where the light is. `steps` is how far they drift (0: draw them where they are). */
  private drawMotes(steps: number) {
    const mx = this.mx;
    if (!mx) return;
    mx.clearRect(0, 0, innerWidth, innerHeight);
    if (this.ambient) {
      const ac = this.accent2;
      for (const m of this.motes) {
        m.x += m.vx * steps;
        m.y += m.vy * steps;
        m.p += 0.012 * steps;
        if (m.y < -10) {
          m.y = innerHeight + 10;
          m.x = Math.random() * innerWidth;
        }
        if (m.x > innerWidth + 10) m.x = -10;
        const near = Math.max(0, 1 - Math.hypot(m.x - this.cx, m.y - this.cy) / 420);
        const a = (0.1 + 0.65 * near) * (0.6 + 0.4 * Math.sin(m.p));
        mx.fillStyle = `rgba(${ac[0]},${ac[1]},${ac[2]},${a.toFixed(3)})`;
        mx.beginPath();
        mx.arc(m.x, m.y, m.r, 0, 6.3);
        mx.fill();
      }
    }
  }

  /** A burst of golden sparks at a screen position. */
  burst(x0: number, y0: number, n = 170) {
    const el = this.el;
    if (!el || this.reduce) return;
    const c = el.sparks;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = innerWidth * dpr;
    c.height = innerHeight * dpr;
    const x = c.getContext("2d")!;
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    const c1 = rgb(cssVar("--accent-2"));
    const c2 = [255, 246, 226];
    const parts: Spark[] = Array.from({ length: n }, () => {
      const a = Math.random() * 6.283;
      const s = 2 + Math.random() * (n < 80 ? 5 : 10);
      return { x: x0, y: y0, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 2.2, life: 1, r: 1 + Math.random() * 2.6, c: Math.random() < 0.75 ? c1 : c2 };
    });
    const step = () => {
      x.clearRect(0, 0, innerWidth, innerHeight);
      let alive = 0;
      for (const p of parts) {
        if (p.life <= 0) continue;
        alive++;
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= 0.965;
        p.vy = p.vy * 0.965 + 0.14;
        p.life -= 0.012;
        x.fillStyle = `rgba(${p.c[0]},${p.c[1]},${p.c[2]},${Math.max(0, p.life).toFixed(3)})`;
        x.beginPath();
        x.arc(p.x, p.y, p.r, 0, 6.3);
        x.fill();
      }
      if (alive) requestAnimationFrame(step);
      else x.clearRect(0, 0, innerWidth, innerHeight);
    };
    step();
  }

  /** Redraw the shelves after the theme changed (fades out, redraws, fades in). */
  setTheme() {
    const el = this.el;
    if (!el) return;
    el.scene.style.opacity = "0";
    clearTimeout(this.themeTimer);
    this.themeTimer = window.setTimeout(() => {
      this.drawScene();
      if (this.reduce || this.paused) this.drawMotes(0); // the dust takes the new theme's colour too
      if (this.el) this.el.scene.style.opacity = "1";
    }, 220);
  }

  setAmbient(on: boolean) {
    this.ambient = on;
    if (this.el) this.el.cursor.style.opacity = on ? "1" : "0";
  }

  flash() {
    const f = this.el?.flash;
    if (!f) return;
    f.classList.remove("go");
    void f.offsetWidth;
    f.classList.add("go");
  }
}

export const room = new Room();
