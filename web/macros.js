/* Ten macro knobs over 154 parameters.

   Chassis: a value arc and a pointer notch around a well cut into the
   faceplate; inside the well a small lit diagram of what the knob does.
   All ten graphics share one rAF loop that only runs while something is
   happening — dragging, hovering, or audio playing. */
'use strict';

const Macros = (() => {
  const SWEEP = 270, R = 31;
  const C = 2 * Math.PI * R;          // 194.78
  const ARC = C * (SWEEP / 360);      // 146.08
  const NS = 'http://www.w3.org/2000/svg';
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // a fixed scatter, so a knob looks the same every time you open the app
  const SEED = [0.31,0.78,0.12,0.94,0.55,0.03,0.67,0.41,0.86,0.22,
                0.73,0.08,0.60,0.37,0.91,0.17,0.49,0.82,0.26,0.64,
                0.05,0.71,0.44,0.98];

  const M = {
    defs: [], values: {}, base: {}, arts: {},
    active: null, hooks: {}, els: {}, raf: 0, hovering: 0, dragging: 0,
  };

  const el = (t, a) => {
    const n = document.createElementNS(NS, t);
    for (const k in (a || {})) n.setAttribute(k, a[k]);
    return n;
  };
  const clamp01 = v => Math.min(1, Math.max(0, v));
  const lerp = (a, b, t) => a + (b - a) * t;

  /* ------------------------------------------------------- curve maths */
  function evalCurve(points, v) {
    v = clamp01(v);
    if (!points.length) return null;
    if (typeof points[0][1] === 'string') {
      let out = points[0][1];
      for (const [x, y] of points) if (v >= x) out = y;
      return out;
    }
    if (v <= points[0][0]) return +points[0][1];
    if (v >= points.at(-1)[0]) return +points.at(-1)[1];
    for (let i = 0; i < points.length - 1; i++) {
      const [x0, y0] = points[i], [x1, y1] = points[i + 1];
      if (v >= x0 && v <= x1) {
        const t = x1 === x0 ? 0 : (v - x0) / (x1 - x0);
        return +y0 + (+y1 - +y0) * t;
      }
    }
    return +points.at(-1)[1];
  }

  function invertCurve(points, value) {
    if (!points.length || typeof points[0][1] === 'string') return 0.5;
    const xs = points.map(p => +p[0]), ys = points.map(p => +p[1]);
    const v = parseFloat(value);
    if (!isFinite(v)) return 0.5;
    const rising = ys.at(-1) >= ys[0];
    if ((rising && v <= ys[0]) || (!rising && v >= ys[0])) return xs[0];
    if ((rising && v >= ys.at(-1)) || (!rising && v <= ys.at(-1))) return xs.at(-1);
    for (let i = 0; i < ys.length - 1; i++) {
      const a = ys[i], b = ys[i + 1];
      if ((a <= v && v <= b) || (b <= v && v <= a)) {
        const t = b === a ? 0 : (v - a) / (b - a);
        return xs[i] + (xs[i + 1] - xs[i]) * t;
      }
    }
    return 0.5;
  }

  /* ==================================================================
     the ten well graphics
     each returns { root, set(v), tick(v, t) }
     ================================================================== */
  const ART = {};

  // BODY — a resonant body that grows until it outgrows its own window
  ART.body = c => {
    const core = el('circle', { cx: 37, cy: 37, r: 4, fill: c });
    const r1 = el('circle', { cx: 37, cy: 37, r: 6, fill: 'none', stroke: c, 'stroke-width': 1, opacity: .45 });
    const r2 = el('circle', { cx: 37, cy: 37, r: 8, fill: 'none', stroke: c, 'stroke-width': 1, opacity: .2 });
    const pulse = el('circle', { cx: 37, cy: 37, r: 4, fill: 'none', stroke: c, 'stroke-width': 1, opacity: 0 });
    const root = el('g'); root.append(r2, r1, core, pulse);
    let base = 4;
    return {
      root,
      set(v) {
        base = 4 + v * 16;
        core.setAttribute('r', base.toFixed(2));
        r1.setAttribute('r', (base * 1.4).toFixed(2));
        r2.setAttribute('r', (base * 1.85).toFixed(2));
      },
      tick(v, t) {
        core.setAttribute('r', (base * (1 + 0.04 * Math.sin(t * 5.0))).toFixed(2));
        const age = (t % 1.6) / 1.2;
        if (age <= 1) {
          pulse.setAttribute('r', (base + age * 19).toFixed(2));
          pulse.setAttribute('opacity', ((1 - age) * 0.5).toFixed(3));
        } else pulse.setAttribute('opacity', 0);
      },
    };
  };

  // AIR — breath drifting across a closed glottis that it erases
  ART.air = c => {
    const line = el('line', { x1: 15, y1: 37, x2: 59, y2: 37, stroke: c, 'stroke-width': 1, opacity: 1 });
    const mk = () => {
      const g = el('g');
      for (let i = 0; i < 14; i++) {
        g.append(el('circle', {
          cx: (14 + SEED[i] * 46).toFixed(1),
          cy: (14 + SEED[i + 8] * 46).toFixed(1), r: 0.9, fill: c,
        }));
      }
      return g;
    };
    const a = mk(), b = mk();
    b.setAttribute('transform', 'translate(-46,46)');
    const root = el('g'); root.append(line, a, b);
    let shown = -1;
    return {
      root,
      set(v) {
        const n = Math.round(2 + v * 12);
        if (n !== shown) {
          shown = n;
          for (let i = 0; i < 14; i++) {
            const d = i < n ? '' : 'none';
            a.children[i].style.display = d;
            b.children[i].style.display = d;
          }
        }
        a.setAttribute('opacity', (0.2 + v * 0.8).toFixed(2));
        b.setAttribute('opacity', (0.2 + v * 0.8).toFixed(2));
        line.setAttribute('opacity', (1 - v).toFixed(2));
      },
      tick(v, t) {
        const d = ((2 + v * 11) * t) % 46;
        a.setAttribute('transform', `translate(${d.toFixed(1)},${(-d).toFixed(1)})`);
        b.setAttribute('transform', `translate(${(d - 46).toFixed(1)},${(46 - d).toFixed(1)})`);
      },
    };
  };

  // TONE — a spectrum that tilts from dark-heavy to bright-heavy
  ART.tone = c => {
    const bars = [];
    const root = el('g');
    for (let i = 0; i < 9; i++) {
      const b = el('rect', { x: (16 + i * 4.6).toFixed(1), y: 50, width: 3, height: 4, fill: c });
      bars.push(b); root.append(b);
    }
    let hs = new Array(9).fill(4);
    return {
      root,
      set(v) {
        root.setAttribute('opacity', (0.55 + v * 0.45).toFixed(2));
        for (let i = 0; i < 9; i++) {
          const k = i / 8;
          hs[i] = 4 + 30 * (0.15 + 0.85 * lerp(1 - k, k, v));
          bars[i].setAttribute('height', hs[i].toFixed(1));
          bars[i].setAttribute('y', (54 - hs[i]).toFixed(1));
        }
      },
      tick(v, t) {
        for (let i = 0; i < 9; i++) {
          const h = hs[i] * (1 + 0.08 * Math.sin(t * 6.9 + i * 0.7));
          bars[i].setAttribute('height', h.toFixed(1));
          bars[i].setAttribute('y', (54 - h).toFixed(1));
        }
      },
    };
  };

  // GRIT — a clean wave that fractures; the stutter is the point
  ART.grit = c => {
    const path = el('path', { d: '', fill: 'none', stroke: c, 'stroke-width': 1.4, 'stroke-linecap': 'round' });
    const cracks = [0, 1, 2].map(i => el('line', {
      x1: 37, y1: 37, x2: 37, y2: 37, stroke: c, 'stroke-width': 1, opacity: 0,
    }));
    const root = el('g'); root.append(path, ...cracks);
    let last = -1, noise = SEED.slice();
    const build = v => {
      let d = '', pen = false;
      for (let i = 0; i < 24; i++) {
        const x = 15 + i * (44 / 23);
        const y = 37 + Math.sin(i / 23 * Math.PI * 4) * 5 + (noise[i] - 0.5) * v * 14;
        const brk = v > 0.6 && i % 3 === 2;
        if (!pen || brk) { d += `M${x.toFixed(1)} ${y.toFixed(1)}`; pen = true; }
        else d += `L${x.toFixed(1)} ${y.toFixed(1)}`;
        if (brk) pen = false;
      }
      path.setAttribute('d', d);
      const cl = Math.max(0, (v - 0.75) * 40);
      for (let i = 0; i < 3; i++) {
        const a = i * 2.1 + 0.4;
        cracks[i].setAttribute('x2', (37 + Math.cos(a) * cl).toFixed(1));
        cracks[i].setAttribute('y2', (37 + Math.sin(a) * cl).toFixed(1));
        cracks[i].setAttribute('opacity', cl > 0 ? 0.7 : 0);
      }
    };
    return {
      root,
      set(v) { build(v); },
      tick(v, t) {                                  // re-roll at 12fps
        const f = Math.floor(t * 12);
        if (f === last) return;
        last = f;
        for (let i = 0; i < 24; i++) noise[i] = (noise[(i + 7) % 24] * 9301 + 49297) % 1;
        build(v);
      },
    };
  };

  // LIFE — a machine lattice dissolving as a square wave becomes a pulse
  ART.life = c => {
    const grid = el('g', { opacity: .3 });
    for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) {
      grid.append(el('circle', { cx: 19 + x * 12, cy: 19 + y * 12, r: 0.7, fill: c }));
    }
    const wrap = el('g');
    const path = el('path', { d: '', fill: 'none', stroke: c, 'stroke-width': 1.4, 'stroke-linejoin': 'round' });
    wrap.append(path);
    const root = el('g'); root.append(grid, wrap);
    const HAND = [0,-2,1,-1,4,-6,2,0,-1,3,-2,1,0,-3,5,-1,0,2,-2,1,0,-1,2,0];
    let cur = 0;
    const build = v => {
      let d = '';
      for (let i = 0; i < 48; i++) {
        const k = i % 24;
        const sq = (Math.floor(k / 3) % 2) ? -7 : 7;
        const y = 37 + lerp(sq, HAND[k], v);
        const x = i * (44 / 23);
        d += (i ? 'L' : 'M') + (15 + x).toFixed(1) + ' ' + y.toFixed(1);
      }
      path.setAttribute('d', d);
    };
    return {
      root,
      set(v) { cur = v; grid.setAttribute('opacity', (0.3 * (1 - v)).toFixed(2)); build(v); },
      tick(v, t) {
        const d = -((14 * t) % 44);
        wrap.setAttribute('transform', `translate(${d.toFixed(1)},0)`);
        if (v > 0.6 && Math.floor(t * 10) % 2 === 0) build(v);
      },
    };
  };

  // MOTION — a vibrato pendulum; dead flat at zero, which is honest
  ART.motion = c => {
    const base = el('line', { x1: 15, y1: 37, x2: 59, y2: 37, stroke: c, 'stroke-width': 1, opacity: .25 });
    const wrap = el('g');
    const path = el('path', { d: '', fill: 'none', stroke: c, 'stroke-width': 1.4 });
    wrap.append(path);
    const dot = el('circle', { cx: 57, cy: 37, r: 2, fill: c });
    const root = el('g'); root.append(base, wrap, dot);
    let amp = 0, wl = 46;
    const build = v => {
      amp = v * 15; wl = 46 / (0.8 + v * 1.4);
      let d = '';
      for (let i = 0; i <= 60; i++) {
        const x = i * (88 / 60);
        const y = 37 + Math.sin(x / wl * Math.PI * 2) * amp;
        d += (i ? 'L' : 'M') + (15 + x).toFixed(1) + ' ' + y.toFixed(1);
      }
      path.setAttribute('d', d);
    };
    return {
      root,
      set(v) { build(v); dot.setAttribute('cy', 37); },
      tick(v, t) {
        const sp = (0.8 + v * 2.2) * 14;
        const d = -((sp * t) % wl);
        wrap.setAttribute('transform', `translate(${d.toFixed(1)},0)`);
        dot.setAttribute('cy', (37 + Math.sin(((42 - d) / wl) * Math.PI * 2) * amp).toFixed(1));
      },
    };
  };

  // DICTION — one slurred bar separating into hard syllables
  ART.diction = c => {
    const rects = [];
    const root = el('g');
    for (let i = 0; i < 5; i++) {
      const r = el('rect', { x: 0, y: 31, width: 7, height: 12, rx: 3, fill: c });
      rects.push(r); root.append(r);
    }
    return {
      root,
      set(v) {
        const gap = v * 3.2, w = 7;
        const total = 5 * w + 4 * gap;
        const x0 = 37 - total / 2;
        for (let i = 0; i < 5; i++) {
          rects[i].setAttribute('x', (x0 + i * (w + gap)).toFixed(1));
          rects[i].setAttribute('rx', (3 - v * 2.5).toFixed(2));
          rects[i].setAttribute('opacity', (0.4 + v * 0.6).toFixed(2));
          rects[i].setAttribute('fill', c);
        }
      },
      tick(v, t) {
        const k = Math.floor((t % 1.6) / 1.6 * 6.5);
        for (let i = 0; i < 5; i++) rects[i].setAttribute('fill', i === k ? '#FFFFFF' : c);
      },
    };
  };

  // ROBOT — smooth formant bands quantising into vocoder cells
  ART.robot = c => {
    const rows = [];
    const root = el('g');
    for (let i = 0; i < 7; i++) {
      const l = el('line', { x1: 15, y1: 19 + i * 6, x2: 40, y2: 19 + i * 6, stroke: c, 'stroke-width': 3 });
      rows.push(l); root.append(l);
    }
    const ENV = [0.55, 0.9, 0.7, 1.0, 0.6, 0.8, 0.45];
    let last = -1, cur = 0;
    const draw = (v, jitter) => {
      const n = Math.round(lerp(7, 4, v));
      for (let i = 0; i < 7; i++) {
        if (i >= n) { rows[i].style.display = 'none'; continue; }
        rows[i].style.display = '';
        const len = 10 + (ENV[i] * (0.7 + jitter[i] * 0.3)) * 34;
        rows[i].setAttribute('x2', (15 + len).toFixed(1));
        rows[i].setAttribute('stroke-dasharray', v > 0.15 ? `${(3).toFixed(0)} ${(v * 2.2).toFixed(1)}` : 'none');
      }
    };
    let jit = [.5, .5, .5, .5, .5, .5, .5];
    return {
      root,
      set(v) { cur = v; draw(v, jit); },
      tick(v, t) {                                  // step at 10fps, never tween
        const f = Math.floor(t * 10);
        if (f === last) return;
        last = f;
        jit = jit.map((_, i) => SEED[(f + i) % SEED.length]);
        draw(v, jit);
      },
    };
  };

  // THICK — stacked detuned copies beating against each other
  ART.thick = c => {
    const bars = [];
    const root = el('g');
    for (let i = 0; i < 7; i++) {
      const b = el('rect', { x: 35.5, y: 24, width: 3, height: 26, fill: c });
      bars.push(b); root.append(b);
    }
    return {
      root,
      set(v) {
        const n = Math.round(v * 6);
        for (let i = 0; i < 7; i++) {
          if (i > n) { bars[i].style.display = 'none'; continue; }
          bars[i].style.display = '';
          const side = i % 2 ? 1 : -1;
          const step = Math.ceil(i / 2);
          bars[i].setAttribute('x', (35.5 + side * (step ? 3 + step * 3.4 : 0)).toFixed(1));
          bars[i].setAttribute('opacity', (1 - step * 0.11).toFixed(2));
        }
      },
      tick(v, t) {
        for (let i = 0; i < 7; i++) {
          if (bars[i].style.display === 'none') continue;
          const dy = Math.sin(t * (0.25 + i * 0.04) * 6.28) * 1;
          bars[i].setAttribute('transform', `translate(0,${dy.toFixed(2)})`);
        }
      },
    };
  };

  // SPACE — ripples that die on the dot when dry and reach the rim when wet
  ART.space = c => {
    const dot = el('circle', { cx: 37, cy: 37, r: 2, fill: c });
    const rings = [0, 1, 2].map(() =>
      el('circle', { cx: 37, cy: 37, r: 2, fill: 'none', stroke: c, 'stroke-width': 1, opacity: 0 }));
    const root = el('g'); root.append(...rings, dot);
    let cur = 0;
    return {
      root,
      set(v) {
        cur = v;
        if (v <= 0.01) rings.forEach(r => r.setAttribute('opacity', 0));
      },
      tick(v, t) {
        if (v <= 0.01) return;
        const life = 0.5 + v * 2.2;
        for (let i = 0; i < 3; i++) {
          const age = ((t + i * 1.6 / 3) % 1.6) / life;
          if (age > 1) { rings[i].setAttribute('opacity', 0); continue; }
          rings[i].setAttribute('r', (2 + age * 21).toFixed(1));
          rings[i].setAttribute('opacity', ((1 - age) * (0.25 + v * 0.75)).toFixed(3));
        }
      },
    };
  };

  /* ==================================================== shared rAF loop */
  function needsMotion() {
    return !REDUCED && (M.dragging > 0 || M.hovering > 0 || M.hooks.isPlaying?.());
  }
  function loop(ms) {
    const t = ms / 1000;
    for (const def of M.defs) {
      const art = M.arts[def.key];
      if (art) art.tick(M.values[def.key] ?? 0.5, t);
    }
    M.raf = needsMotion() ? requestAnimationFrame(loop) : 0;
    if (!M.raf) for (const def of M.defs) M.arts[def.key]?.set(M.values[def.key] ?? 0.5);
  }
  function kick() {
    if (M.raf || !needsMotion()) return;
    M.raf = requestAnimationFrame(loop);
  }

  /* ============================================================ chassis */
  function build(def) {
    const s = el('svg', { class: 'knob', viewBox: '0 0 74 74' });
    const track = el('circle', {
      class: 'k-track', cx: 37, cy: 37, r: R, fill: 'none',
      'stroke-dasharray': `${ARC.toFixed(2)} ${C.toFixed(2)}`,
      transform: 'rotate(135 37 37)',
    });
    const arc = el('circle', {
      class: 'k-arc', cx: 37, cy: 37, r: R, fill: 'none', stroke: def.colour,
      'stroke-dasharray': `0 ${C.toFixed(2)}`, transform: 'rotate(135 37 37)',
    });
    const point = el('g', { class: 'k-point', transform: 'rotate(-135 37 37)' });
    point.append(el('line', { class: 'k-notch', x1: 37, y1: 11.5, x2: 37, y2: 8, stroke: def.colour }));
    const well = el('circle', { class: 'k-well', cx: 37, cy: 37, r: 25 });
    const ring = el('circle', { class: 'k-ring', cx: 37, cy: 37, r: 25, fill: 'none' });
    const art = (ART[def.key] || ART.body)(def.colour);
    const artg = el('g', { class: 'k-art', 'clip-path': 'url(#kwell)' });
    artg.append(art.root);
    s.append(track, arc, point, well, ring, artg);

    const wrap = document.createElement('button');
    wrap.className = 'macro';
    wrap.type = 'button';
    wrap.dataset.key = def.key;
    wrap.style.setProperty('--c', def.colour);
    wrap.setAttribute('role', 'slider');
    wrap.setAttribute('aria-valuemin', '0');
    wrap.setAttribute('aria-valuemax', '100');
    wrap.setAttribute('aria-label', `${def.label}, ${def.lo} to ${def.hi}`);
    wrap.title = `${def.label} — ${def.lo} → ${def.hi}\n${def.blurb}`;

    const badge = document.createElement('i'); badge.className = 'm-badge';
    const name = document.createElement('div'); name.className = 'm-name'; name.textContent = def.label;
    const val = document.createElement('div'); val.className = 'm-val'; val.textContent = '50';
    wrap.append(s, badge, name, val);

    M.els[def.key] = { wrap, arc, point, val };
    M.arts[def.key] = art;
    bind(wrap, def);
    return wrap;
  }

  function bind(wrap, def) {
    let drag = false, lastY = 0, acc = 0;
    const snap = () => {
      wrap.classList.add('snap');
      setTimeout(() => wrap.classList.remove('snap'), 240);
    };

    wrap.addEventListener('pointerdown', ev => {
      if (ev.button === 2) return;
      drag = true; M.dragging++; lastY = ev.clientY; acc = M.values[def.key] ?? 0.5;
      wrap.setPointerCapture?.(ev.pointerId);
      setActive(def.key); kick();
      ev.preventDefault();
    });
    wrap.addEventListener('pointermove', ev => {
      if (!drag) return;
      acc += (lastY - ev.clientY) / (ev.shiftKey ? 700 : 170);
      lastY = ev.clientY;
      set(def.key, acc, true);
    });
    const end = ev => {
      if (!drag) return;
      drag = false; M.dragging = Math.max(0, M.dragging - 1);
      wrap.releasePointerCapture?.(ev.pointerId);
      M.hooks.onCommit?.();
    };
    wrap.addEventListener('pointerup', end);
    wrap.addEventListener('pointercancel', end);

    wrap.addEventListener('pointerenter', () => { M.hovering++; setActive(def.key); kick(); });
    wrap.addEventListener('pointerleave', () => {
      M.hovering = Math.max(0, M.hovering - 1);
      if (!drag) M.hooks.onLeave?.();
    });
    wrap.addEventListener('focus', () => setActive(def.key));

    wrap.addEventListener('dblclick', () => {
      snap(); set(def.key, M.base[def.key] ?? 0.5, true); M.hooks.onCommit?.();
    });
    wrap.addEventListener('wheel', ev => {
      setActive(def.key); kick();
      set(def.key, (M.values[def.key] ?? 0.5) + (ev.deltaY < 0 ? 0.02 : -0.02), true);
      clearTimeout(bind._t);
      bind._t = setTimeout(() => M.hooks.onCommit?.(), 260);
      ev.preventDefault();
    }, { passive: false });

    wrap.addEventListener('keydown', ev => {
      const step = ev.shiftKey ? 0.005 : 0.02;
      let d = 0;
      if (ev.key === 'ArrowUp' || ev.key === 'ArrowRight') d = step;
      else if (ev.key === 'ArrowDown' || ev.key === 'ArrowLeft') d = -step;
      else if (ev.key === 'Home') { set(def.key, 0, true); M.hooks.onCommit?.(); ev.preventDefault(); return; }
      else if (ev.key === 'End') { set(def.key, 1, true); M.hooks.onCommit?.(); ev.preventDefault(); return; }
      else return;
      set(def.key, (M.values[def.key] ?? 0.5) + d, true);
      clearTimeout(bind._k);
      bind._k = setTimeout(() => M.hooks.onCommit?.(), 300);
      ev.preventDefault();
    });
  }

  /* ------------------------------------------------------------ state */
  function paint(key) {
    const e = M.els[key]; if (!e) return;
    const v = clamp01(M.values[key] ?? 0.5);
    e.arc.setAttribute('stroke-dasharray', `${(ARC * v).toFixed(2)} ${C.toFixed(2)}`);
    e.point.setAttribute('transform', `rotate(${(-SWEEP / 2 + v * SWEEP).toFixed(2)} 37 37)`);
    e.val.textContent = String(Math.round(v * 100)).padStart(2, '0');
    e.wrap.setAttribute('aria-valuenow', Math.round(v * 100));
    e.wrap.classList.toggle('moved', Math.abs(v - (M.base[key] ?? 0.5)) > 0.005);
    M.arts[key]?.set(v);
  }

  function set(key, v, write) {
    const def = M.defs.find(d => d.key === key); if (!def) return;
    M.values[key] = clamp01(v);
    paint(key);
    if (write) {
      const updates = {};
      for (const [t, pts] of Object.entries(def.targets)) updates[t] = evalCurve(pts, M.values[key]);
      M.hooks.onChange?.(updates);
      M.hooks.onScreen?.(def, M.values[key]);
    }
  }

  function setActive(key) {
    if (M.active === key) return;
    M.active = key;
    for (const e of Object.values(M.els)) {
      e.wrap.classList.toggle('active', e.wrap.dataset.key === key);
    }
    const def = M.defs.find(d => d.key === key);
    if (def) M.hooks.onScreen?.(def, M.values[key] ?? 0.5);
  }

  /* -------------------------------------------------------------- API */
  return {
    load(defs) { M.defs = defs || []; },
    get defs() { return M.defs; },
    get values() { return { ...M.values }; },
    get active() { return M.defs.find(d => d.key === M.active) || null; },

    mount(host, hooks) {
      M.hooks = hooks || {};
      M.els = {}; M.arts = {};
      host.replaceChildren();
      for (const def of M.defs) host.append(build(def));
      for (const def of M.defs) paint(def.key);
      kick();
      if (!needsMotion()) for (const def of M.defs) M.arts[def.key]?.set(M.values[def.key] ?? 0.5);
    },

    sync(params, rebase = true) {
      for (const def of M.defs) {
        const v = invertCurve(def.targets[def.probe], params[def.probe]);
        M.values[def.key] = v;
        if (rebase) M.base[def.key] = v;
        paint(def.key);
      }
    },
    adopt(values) {
      for (const def of M.defs) {
        const v = values?.[def.key];
        if (typeof v !== 'number') continue;
        M.values[def.key] = clamp01(v);
        M.base[def.key] = M.values[def.key];
        paint(def.key);
      }
    },
    randomize() {
      const updates = {};
      for (const def of M.defs) {
        // biased to the middle, so a random voice is usually singable
        const r = (Math.random() + Math.random() + Math.random() - 1.5) * 0.55;
        M.values[def.key] = clamp01(0.5 + r);
        M.els[def.key]?.wrap.classList.add('snap');
        paint(def.key);
        for (const [t, pts] of Object.entries(def.targets)) updates[t] = evalCurve(pts, M.values[def.key]);
      }
      setTimeout(() => Object.values(M.els).forEach(e => e.wrap.classList.remove('snap')), 240);
      M.hooks.onChange?.(updates);
      M.hooks.onCommit?.();
    },
    resetKnobs() {
      const updates = {};
      for (const def of M.defs) {
        M.values[def.key] = M.base[def.key] ?? 0.5;
        M.els[def.key]?.wrap.classList.add('snap');
        paint(def.key);
        for (const [t, pts] of Object.entries(def.targets)) updates[t] = evalCurve(pts, M.values[def.key]);
      }
      setTimeout(() => Object.values(M.els).forEach(e => e.wrap.classList.remove('snap')), 240);
      M.hooks.onChange?.(updates);
      M.hooks.onCommit?.();
    },
    isProbe(key) { return M.defs.some(d => d.probe === key); },
    kick,
    evalCurve, invertCurve,
  };
})();
