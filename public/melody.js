/* Piano roll with the phoneme/note alignment drawn underneath it on the
   same beat axis. Notation surface: nothing here animates. */
'use strict';

const Mel = (() => {
  const GUT = 40;          // left gutter showing note names
  const ROW = 14;          // pixels per semitone
  const LANE = 22;         // height of one alignment lane
  const PAD = 8;

  // phoneme classes reuse the macro palette, so the whole app runs on ten hues
  const CLS_COLOUR = {
    vowel: '#3DDC6B', diphthong: '#00E0C6', nasal: '#B15CFF',
    approximant: '#4D7CFF', fricative: '#FFD21E', stop: '#FF3B30',
    affricate: '#FF8A3D', silence: '#2B2926',
  };
  const NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
  const BLACK = [1, 3, 6, 8, 10];
  const nameOf = m => NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1);

  const M = {
    notes: [], align: null, tail: 0,
    grid: 0.25, zoom: 90, top: 76, sel: -1,
    hooks: {}, canvas: null, wrap: null,
  };
  // vertical layout, recomputed from the region height
  const G = { ROWS: 19, ROLL_H: 266, SYL_Y: 274, PHN_Y: 299, RULE_Y: 324, H: 342 };

  function layout() {
    const avail = (M.wrap?.clientHeight || 340) - (LANE * 2 + 6 + 18 + PAD);
    G.ROWS = Math.max(9, Math.min(30, Math.floor(avail / ROW)));
    G.ROLL_H = G.ROWS * ROW;
    G.SYL_Y = G.ROLL_H + PAD;
    G.PHN_Y = G.SYL_Y + LANE + 3;
    G.RULE_Y = G.PHN_Y + LANE + 3;
    G.H = G.RULE_Y + 18;
  }

  /* ------------------------------------------------------------ geometry */
  const totalBeats = () => Math.max(
    4,
    M.notes.reduce((a, n) => Math.max(a, n.start + n.len), 0) + 1,
    (M.align?.total_beats || 0) + 1);

  const bx = b => GUT + b * M.zoom;
  const xb = x => (x - GUT) / M.zoom;
  const my = m => (M.top - m) * ROW;
  const ym = y => M.top - Math.floor(y / ROW);
  const snap = b => Math.round(b / M.grid) * M.grid;
  const tb = t => ((t - (M.align?.lead || 0)) / (M.align?.beat || 0.5));

  /* --------------------------------------------------------- serialising */
  function fmtBeats(v) {
    for (const d of [1, 2, 3, 4, 6, 8, 16]) {
      const n = v * d;
      if (Math.abs(n - Math.round(n)) < 1e-6) {
        const num = Math.round(n);
        return d === 1 ? String(num) : (num % d === 0 ? String(num / d) : `${num}/${d}`);
      }
    }
    return String(+v.toFixed(4));
  }

  function serialize() {
    const ns = [...M.notes].sort((a, b) => a.start - b.start);
    if (!ns.length) return '';
    const out = [];
    let octave = null;
    if (ns[0].start > 1e-6) out.push('R:' + fmtBeats(ns[0].start));
    ns.forEach((n, i) => {
      const step = i < ns.length - 1 ? ns[i + 1].start - n.start : n.len + M.tail;
      const len = Math.min(n.len, step);
      const m = Math.round(n.midi), oct = Math.floor(m / 12) - 1;
      let tok = NAMES[((m % 12) + 12) % 12] + (oct === octave ? '' : oct);
      octave = oct;
      if (Math.abs(len - step) > 1e-6) tok += `:${fmtBeats(step)}:${fmtBeats(len)}`;
      else if (Math.abs(step - 1) > 1e-6) tok += `:${fmtBeats(step)}`;
      out.push(tok);
    });
    return out.join(' ');
  }

  function adopt(a) {
    const rows = a?.notes || [];
    M.notes = rows
      .filter(n => n.midi !== null && n.midi !== undefined)
      .map(n => ({ midi: Math.round(n.midi), start: n.start_beat, len: n.len_beats }));
    const last = M.notes[M.notes.length - 1];
    M.tail = last ? Math.max(0, (a?.total_beats || 0) - (last.start + last.len)) : 0;
    fitRange();
  }

  function fitRange() {
    if (!M.notes.length) { M.top = 76; return; }
    const hi = Math.max(...M.notes.map(n => n.midi));
    const lo = Math.min(...M.notes.map(n => n.midi));
    const centre = (hi + lo) / 2;
    M.top = Math.round(Math.min(Math.max(centre + G.ROWS / 2, lo + G.ROWS - 2), hi + 2));
  }

  /* The voice is monophonic: no two notes may start on the same beat and none
     may sound past the next one. Without this, serialize() can emit a
     zero-length step that the parser turns into a silent note. */
  function normalize() {
    const sel = M.sel >= 0 ? M.notes[M.sel] : null;
    M.notes.sort((a, b) => a.start - b.start);
    const out = [];
    for (const n of M.notes) {
      const prev = out[out.length - 1];
      if (prev && Math.abs(prev.start - n.start) < 1e-6) {
        if (prev === sel) continue;
        out[out.length - 1] = n;
        continue;
      }
      out.push(n);
    }
    out.forEach((n, i) => {
      const room = i < out.length - 1 ? out[i + 1].start - n.start : Infinity;
      n.len = Math.max(1 / 32, Math.min(n.len, room));
    });
    M.notes = out;
    M.sel = sel ? out.indexOf(sel) : -1;
  }

  const changed = () => { normalize(); M.hooks.onChange?.(serialize()); draw(); };

  /* --------------------------------------------------------------- draw */
  const T = n => Theme.get(n);

  function draw() {
    const cv = M.canvas; if (!cv) return;
    layout();
    const beats = Math.max(totalBeats(), (M.wrap.clientWidth - GUT) / M.zoom);
    const cssW = Math.max(M.wrap.clientWidth, GUT + beats * M.zoom);
    const dpr = window.devicePixelRatio || 1;
    cv.style.width = cssW + 'px'; cv.style.height = G.H + 'px';
    cv.width = cssW * dpr; cv.height = G.H * dpr;
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, cssW, G.H);
    g.font = '10px ui-monospace, monospace';
    g.textBaseline = 'middle';

    const white = T('--roll-white'), black = T('--roll-black');
    for (let r = 0; r < G.ROWS; r++) {
      const m = M.top - r;
      g.fillStyle = BLACK.includes(((m % 12) + 12) % 12) ? black : white;
      g.fillRect(GUT, r * ROW, cssW - GUT, ROW);
      if (((m % 12) + 12) % 12 === 0) {
        g.strokeStyle = T('--roll-bar'); g.beginPath();
        g.moveTo(GUT, r * ROW + .5); g.lineTo(cssW, r * ROW + .5); g.stroke();
      }
    }

    for (let b = 0; b <= beats; b += M.grid) {
      const x = Math.round(bx(b)) + .5;
      const isBar = Math.abs(b % 4) < 1e-6, isBeat = Math.abs(b % 1) < 1e-6;
      g.strokeStyle = isBar ? T('--roll-bar') : (isBeat ? T('--roll-beat') : T('--roll-sub'));
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, G.ROLL_H); g.stroke();
    }

    const pc = M.align?.pitch;
    if (pc?.midi?.length) {
      g.strokeStyle = T('--vf-signal'); g.lineWidth = 1.5;
      g.beginPath();
      let pen = false;
      for (let i = 0; i < pc.midi.length; i++) {
        const t = i / pc.hz, x = bx(tb(t)), y = my(pc.midi[i]) + ROW / 2;
        if (!pc.gate[i] || y < -ROW || y > G.ROLL_H + ROW) { pen = false; continue; }
        pen ? g.lineTo(x, y) : g.moveTo(x, y);
        pen = true;
      }
      g.stroke(); g.lineWidth = 1;
    }

    const sounding = new Map();
    for (const n of (M.align?.notes || [])) {
      if (n.midi != null) sounding.set(n.start_beat.toFixed(4), n.sound_beats);
    }
    const on = T('--note-on'), off = T('--note-off'), sig = T('--vf-signal');
    M.notes.forEach((n, i) => {
      const x0 = bx(n.start), y0 = my(n.midi);
      if (y0 < -ROW || y0 > G.ROLL_H) return;
      const w = Math.max(n.len * M.zoom, 3);
      const snd = sounding.get(n.start.toFixed(4));
      const sw = snd != null ? Math.max(snd * M.zoom, 2) : w;
      g.fillStyle = off; g.fillRect(x0, y0 + 1, w, ROW - 2);
      g.fillStyle = on;  g.fillRect(x0, y0 + 1, Math.min(sw, w), ROW - 2);
      if (i === M.sel) {
        g.strokeStyle = sig; g.strokeRect(x0 + .5, y0 + 1.5, w - 1, ROW - 3);
      }
      if (w > 26) {
        g.fillStyle = T('--vf-black');
        g.fillText(nameOf(n.midi), x0 + 4, y0 + ROW / 2 + .5);
      }
    });

    g.fillStyle = T('--vf-recess'); g.fillRect(0, 0, GUT, G.ROLL_H);
    for (let r = 0; r < G.ROWS; r++) {
      const m = M.top - r, isBlack = BLACK.includes(((m % 12) + 12) % 12);
      g.fillStyle = isBlack ? T('--key-sharp') : T('--key-nat');
      g.fillRect(2, r * ROW + 1, GUT - 6, ROW - 2);
      if (!isBlack) {
        g.fillStyle = T('--vf-bone-mute');
        g.fillText(nameOf(m), 5, r * ROW + ROW / 2 + .5);
      }
    }
    g.strokeStyle = T('--vf-line');
    g.beginPath(); g.moveTo(GUT + .5, 0); g.lineTo(GUT + .5, G.H); g.stroke();

    drawLanes(g, cssW, beats);
  }

  function drawLanes(g, cssW, beats) {
    const a = M.align;
    g.fillStyle = T('--vf-bone-mute');
    g.fillText('syl', 5, G.SYL_Y + LANE / 2);
    g.fillText('phn', 5, G.PHN_Y + LANE / 2);
    g.strokeStyle = T('--vf-line');
    for (const y of [G.SYL_Y, G.PHN_Y]) {
      g.beginPath(); g.moveTo(GUT, y + .5); g.lineTo(cssW, y + .5); g.stroke();
    }
    if (!a) return;

    g.setLineDash([2, 3]);
    g.strokeStyle = Theme.alpha('--vf-signal', 0.4);
    for (const s of a.syllables) {
      if (s.vowel_on == null) continue;
      const x = Math.round(bx(tb(s.vowel_on))) + .5;
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, G.SYL_Y + LANE); g.stroke();
    }
    g.setLineDash([]);

    const faceA = T('--vf-face'), faceB = T('--vf-face-hi');
    for (const s of a.syllables) {
      const x0 = bx(tb(s.s)), w = Math.max(bx(tb(s.e)) - x0, 2);
      g.fillStyle = s.note % 2 ? faceA : faceB;
      g.fillRect(x0, G.SYL_Y + 1, w, LANE - 1);
      if (w > 11) {
        g.fillStyle = T('--vf-bone-dim');
        g.save(); g.beginPath(); g.rect(x0, G.SYL_Y, w, LANE); g.clip();
        g.fillText(s.text || s.nucleus || '', x0 + 4, G.SYL_Y + LANE / 2);
        g.restore();
      }
    }

    for (const s of a.segments) {
      const x0 = bx(tb(s.s)), w = Math.max(bx(tb(s.e)) - x0, 1.5);
      const c = CLS_COLOUR[s.cls] || '#4A4641';
      g.fillStyle = s.role === 'nucleus' ? c : c + '59';
      g.fillRect(x0, G.PHN_Y + 1, w, LANE - 1);
      g.strokeStyle = T('--vf-recess');
      g.strokeRect(x0 + .5, G.PHN_Y + 1.5, w - 1, LANE - 2);
      if (w > 9) {
        g.fillStyle = s.role === 'nucleus' ? T('--vf-black') : T('--vf-bone-dim');
        g.save(); g.beginPath(); g.rect(x0, G.PHN_Y, w, LANE); g.clip();
        g.fillText(s.p, x0 + 3, G.PHN_Y + LANE / 2);
        g.restore();
      }
    }

    g.fillStyle = T('--vf-bone-mute');
    for (let b = 0; b <= beats; b++) {
      const x = bx(b), bar = b % 4 === 0;
      g.strokeStyle = bar ? T('--vf-line') : T('--roll-sub');
      g.beginPath(); g.moveTo(x + .5, G.RULE_Y); g.lineTo(x + .5, G.RULE_Y + (bar ? 8 : 4));
      g.stroke();
      if (bar) g.fillText(`${b / 4 + 1}`, x + 3, G.RULE_Y + 11);
    }
    if (a) {
      g.fillStyle = T('--vf-bone-ghost');
      g.fillText(`${(a.duration || 0).toFixed(2)}s @ ${a.bpm} BPM`, cssW - 110, G.RULE_Y + 11);
    }
  }

  /* ---------------------------------------------------------- interaction */
  function hit(x, y) {
    if (y > G.ROLL_H || x < GUT) return { i: -1 };
    for (let i = M.notes.length - 1; i >= 0; i--) {
      const n = M.notes[i];
      const x0 = bx(n.start), x1 = bx(n.start + n.len), y0 = my(n.midi);
      if (x >= x0 && x <= x1 && y >= y0 && y <= y0 + ROW) return { i, edge: x > x1 - 7 };
    }
    return { i: -1 };
  }

  function laneHit(x, y) {
    const a = M.align; if (!a) return null;
    if (y >= G.PHN_Y && y <= G.PHN_Y + LANE) {
      return a.segments.find(s => x >= bx(tb(s.s)) && x <= bx(tb(s.e))) || null;
    }
    if (y >= G.SYL_Y && y <= G.SYL_Y + LANE) {
      const s = a.syllables.find(s => x >= bx(tb(s.s)) && x <= bx(tb(s.e)));
      return s ? { ...s, p: s.text, cls: 'syllable' } : null;
    }
    return null;
  }

  function bind(cv) {
    let drag = null;
    const pos = ev => {
      const r = cv.getBoundingClientRect();
      return { x: ev.clientX - r.left, y: ev.clientY - r.top };
    };

    cv.addEventListener('mousedown', ev => {
      if (ev.button === 2) return;
      const { x, y } = pos(ev);
      const h = hit(x, y);
      if (h.i >= 0) {
        M.sel = h.i;
        const n = M.notes[h.i];
        drag = { mode: h.edge ? 'resize' : 'move', note: n, db: xb(x) - n.start };
      } else if (y <= G.ROLL_H && x >= GUT) {
        const n = { midi: ym(y), start: Math.max(0, snap(xb(x))), len: M.grid };
        M.notes.push(n);
        M.sel = M.notes.indexOf(n);
        drag = { mode: 'resize', note: n, db: 0 };
        changed();
        M.sel = M.notes.indexOf(n);
      } else return;
      draw();
      ev.preventDefault();
    });

    cv.addEventListener('mousemove', ev => {
      if (drag) return;
      const { x, y } = pos(ev);
      const seg = laneHit(x, y);
      if (seg !== bind._seg) { bind._seg = seg; if (seg) M.hooks.onSegment?.(seg); }
    });
    cv.addEventListener('mouseleave', () => {
      if (bind._seg) { bind._seg = null; M.hooks.onLeave?.(); }
    });

    window.addEventListener('mousemove', ev => {
      if (!drag) return;
      const { x, y } = pos(ev);
      const n = drag.note;
      if (!n || !M.notes.includes(n)) { drag = null; return; }
      if (drag.mode === 'move') {
        n.start = Math.max(0, snap(xb(x) - drag.db));
        n.midi = Math.min(127, Math.max(0, ym(y)));
      } else {
        n.len = Math.max(M.grid, snap(xb(x) - n.start));
      }
      M.sel = M.notes.indexOf(n);
      draw();
    });
    window.addEventListener('mouseup', () => { if (drag) { drag = null; changed(); } });

    cv.addEventListener('contextmenu', ev => {
      const { x, y } = pos(ev);
      const h = hit(x, y);
      if (h.i >= 0) { M.notes.splice(h.i, 1); M.sel = -1; changed(); }
      ev.preventDefault();
    });

    cv.addEventListener('wheel', ev => {
      if (ev.ctrlKey) M.zoom = Math.min(400, Math.max(18, M.zoom * (ev.deltaY < 0 ? 1.15 : 0.87)));
      else if (ev.shiftKey) { M.wrap.scrollLeft += ev.deltaY; return; }
      else M.top = Math.min(120, Math.max(G.ROWS, M.top + (ev.deltaY < 0 ? 1 : -1)));
      draw();
      ev.preventDefault();
    }, { passive: false });

    document.addEventListener('keydown', ev => {
      if (/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(ev.target.tagName)) return;
      if (M.sel < 0 || !M.notes[M.sel]) return;
      const n = M.notes[M.sel];
      if (ev.key === 'Delete' || ev.key === 'Backspace') {
        M.notes.splice(M.sel, 1); M.sel = -1; changed(); ev.preventDefault();
      } else if (ev.key === 'ArrowUp') { n.midi++; changed(); ev.preventDefault(); }
      else if (ev.key === 'ArrowDown') { n.midi--; changed(); ev.preventDefault(); }
      else if (ev.key === 'ArrowLeft') { n.start = Math.max(0, n.start - M.grid); changed(); ev.preventDefault(); }
      else if (ev.key === 'ArrowRight') { n.start += M.grid; changed(); ev.preventDefault(); }
    });
  }

  /* --------------------------------------------------------------- edits */
  const edits = {
    clear() { M.notes = []; M.sel = -1; M.tail = 0; changed(); },
    transpose(st) { M.notes.forEach(n => n.midi = Math.min(127, Math.max(0, n.midi + st))); fitRange(); changed(); },
    scale(f) { M.notes.forEach(n => { n.start *= f; n.len = Math.max(M.grid, n.len * f); }); changed(); },
    legato() {
      const ns = [...M.notes].sort((a, b) => a.start - b.start);
      ns.forEach((n, i) => { if (i < ns.length - 1) n.len = Math.max(M.grid, ns[i + 1].start - n.start); });
      changed();
    },
    staccato() { M.notes.forEach(n => n.len = Math.max(M.grid, n.len / 2)); changed(); },
    fitSyllables() {
      const n = M.align?.syllables?.length || 0;
      if (!n) return;
      const pitches = M.notes.length ? M.notes.map(x => x.midi) : [60];
      M.notes = Array.from({ length: n }, (_, i) => ({
        midi: pitches[i % pitches.length], start: i * M.grid * 2, len: M.grid * 2,
      }));
      fitRange(); changed();
    },
  };

  return {
    mount(wrap, hooks) {
      M.hooks = hooks || {};
      M.wrap = wrap;
      wrap.replaceChildren();
      const cv = document.createElement('canvas');
      wrap.append(cv);
      M.canvas = cv;
      bind(cv);
      new ResizeObserver(() => draw()).observe(wrap);
      draw();
    },
    draw, serialize, adopt, edits,
    setAlign(a, takeNotes) { M.align = a; if (takeNotes) adopt(a); draw(); },
    setGrid(v) { M.grid = v; draw(); },
    zoomBy(f) { M.zoom = Math.min(400, Math.max(18, M.zoom * f)); draw(); },
    get grid() { return M.grid; },
    get notes() { return M.notes; },
  };
})();
