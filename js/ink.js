// Handwriting layer. Strokes live in "page coordinates" (the page is always
// laid out at a fixed logical width), so notes stay exactly where you wrote
// them no matter how big the screen is or how far you zoom.
//
// The layer is split into horizontal canvas tiles, because iPad Safari caps
// the size of a single canvas and long chapters (Psalm 119!) are tall.

const TILE = 1024;

export class InkLayer {
  constructor(host, width) {
    this.host = host;
    this.width = width;
    this.tiles = [];
    this.strokes = [];
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.pending = null; // highlighter stroke in progress
    this.raf = 0;
  }

  setHeight(height) {
    this.height = height;
    this.host.style.height = height + "px";
    const n = Math.ceil(height / TILE);
    while (this.tiles.length > n) this.tiles.pop().canvas.remove();
    while (this.tiles.length < n) {
      const canvas = document.createElement("canvas");
      const top = this.tiles.length * TILE;
      canvas.width = this.width * this.dpr;
      canvas.height = TILE * this.dpr;
      Object.assign(canvas.style, { position: "absolute", left: 0, top: top + "px", width: this.width + "px", height: TILE + "px" });
      this.host.appendChild(canvas);
      this.tiles.push({ canvas, ctx: canvas.getContext("2d"), top });
    }
    this.redrawAll();
  }

  setStrokes(strokes) {
    this.strokes = strokes;
    this.redrawAll();
  }

  redrawAll() {
    for (const t of this.tiles) this.redrawTile(t);
  }

  redrawTile(t) {
    const { ctx } = t;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, -t.top * this.dpr);
    for (const s of this.strokes) if (hits(t, s.bbox)) drawStroke(ctx, s);
    if (this.pending && hits(t, this.pending.bbox)) drawStroke(ctx, this.pending);
  }

  redrawRegion(bbox) {
    for (const t of this.tiles) if (hits(t, bbox)) this.redrawTile(t);
  }

  // ---- live drawing -------------------------------------------------------

  begin(stroke) {
    stroke.bbox = [Infinity, Infinity, -Infinity, -Infinity];
    this.live = stroke;
    if (stroke.tool === "hl") this.pending = stroke;
  }

  extend(points) {
    const s = this.live;
    if (!s) return;
    const start = Math.max(0, s.pts.length - 1);
    for (const p of points) {
      s.pts.push(p);
      grow(s.bbox, p, s.w);
    }
    if (s.tool === "hl") {
      // Highlighter is translucent: redraw it as one path so overlapping
      // segments don't leave darker blotches.
      if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this.redrawRegion(s.bbox); });
    } else {
      const seg = { ...s, pts: s.pts.slice(Math.max(0, start - 1)) };
      const box = [Infinity, Infinity, -Infinity, -Infinity];
      for (const p of seg.pts) grow(box, p, s.w);
      for (const t of this.tiles) {
        if (!hits(t, box)) continue;
        t.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, -t.top * this.dpr);
        drawStroke(t.ctx, seg);
      }
    }
  }

  end() {
    const s = this.live;
    this.live = null;
    this.pending = null;
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    if (!s || !s.pts.length) return null;
    s.pts = s.pts.map(([x, y, p]) => [round(x), round(y), Math.round(p * 100) / 100]);
    this.strokes.push(s);
    this.redrawRegion(s.bbox);
    return s;
  }

  // Returns the strokes touched by an eraser at (x, y), and removes them.
  eraseAt(x, y, r) {
    const gone = [];
    this.strokes = this.strokes.filter((s) => {
      const [a, b, c, d] = s.bbox;
      if (x < a - r || x > c + r || y < b - r || y > d + r) return true;
      if (touches(s, x, y, r)) { gone.push(s); return false; }
      return true;
    });
    for (const s of gone) this.redrawRegion(s.bbox);
    return gone;
  }

  maxY() {
    let m = 0;
    for (const s of this.strokes) m = Math.max(m, s.bbox[3]);
    return m;
  }
}

// ---- helpers ----------------------------------------------------------------

const round = (n) => Math.round(n * 10) / 10;

function grow(b, [x, y], w) {
  const pad = w + 2;
  b[0] = Math.min(b[0], x - pad); b[1] = Math.min(b[1], y - pad);
  b[2] = Math.max(b[2], x + pad); b[3] = Math.max(b[3], y + pad);
}

export function bboxOf(s) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const p of s.pts) grow(b, p, s.w);
  return b;
}

const hits = (t, b) => b[3] >= t.top && b[1] <= t.top + TILE;

const penWidth = (s, p) => s.w * (0.35 + 0.95 * (p || 0.5));

function drawStroke(ctx, s) {
  const pts = s.pts;
  if (!pts.length) return;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = s.color;
  ctx.fillStyle = s.color;

  if (s.tool === "hl") {
    ctx.globalAlpha = 0.38;
    ctx.lineWidth = s.w;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    if (pts.length === 1) ctx.lineTo(pts[0][0] + 0.1, pts[0][1]);
    for (let i = 1; i < pts.length - 1; i++) {
      const mx = (pts[i][0] + pts[i + 1][0]) / 2, my = (pts[i][1] + pts[i + 1][1]) / 2;
      ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
    }
    if (pts.length > 1) ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
    ctx.stroke();
    ctx.globalAlpha = 1;
    return;
  }

  // Pen: pressure-sensitive width, smoothed through segment midpoints.
  if (pts.length === 1) {
    ctx.beginPath();
    ctx.arc(pts[0][0], pts[0][1], penWidth(s, pts[0][2]) / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  let px = pts[0][0], py = pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    const [x, y, p] = pts[i];
    const nx = i < pts.length - 1 ? (x + pts[i + 1][0]) / 2 : x;
    const ny = i < pts.length - 1 ? (y + pts[i + 1][1]) / 2 : y;
    ctx.lineWidth = penWidth(s, p);
    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.quadraticCurveTo(x, y, nx, ny);
    ctx.stroke();
    px = nx; py = ny;
  }
}

function touches(s, x, y, r) {
  const reach = r + s.w / 2;
  const pts = s.pts;
  if (pts.length === 1) return Math.hypot(pts[0][0] - x, pts[0][1] - y) <= reach;
  for (let i = 1; i < pts.length; i++) {
    if (distToSeg(x, y, pts[i - 1], pts[i]) <= reach) return true;
  }
  return false;
}

function distToSeg(x, y, [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay;
  const len = dx * dx + dy * dy;
  let t = len ? ((x - ax) * dx + (y - ay) * dy) / len : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
}
