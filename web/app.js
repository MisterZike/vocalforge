/* VocalForge — application shell. */
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) n.append(c.nodeType ? c : String(c));
  return n;
};
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/* changing any of these moves phonemes or notes in time */
const TIMING_KEYS = new Set([
  'pitch.bpm', 'pitch.swing', 'pitch.note_length', 'pitch.root', 'pitch.scale',
  'pitch.auto_style', 'pitch.portamento', 'pitch.quantize', 'pitch.transpose',
  'pitch.vibrato_depth', 'pitch.vibrato_rate', 'pitch.vibrato_delay',
  'pitch.scoop', 'pitch.fall', 'pitch.drift',
  'art.speed', 'art.consonant_length', 'art.legato', 'art.release', 'text.espeak',
]);
/* what belongs to the song rather than the voice */
const CONTENT_KEYS = ['pitch.melody', 'pitch.bpm', 'pitch.root', 'pitch.scale',
                      'pitch.swing', 'pitch.note_length', 'pitch.auto_style'];
/* shown in the roll toolbar, so hidden from the drawer */
const TOOLBAR_KEYS = new Set(['pitch.bpm', 'pitch.root', 'pitch.scale', 'pitch.swing']);

const VOWELS = /^(AA|AE|AH|AO|AW|AX|AY|EH|ER|EY|IH|IY|OW|OY|UH|UW)$/;
const NOTE_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
const midiName = v => NOTE_NAMES[((Math.round(v) % 12) + 12) % 12] + (Math.floor(v / 12) - 1);

const S = {
  schema: [], byKey: {}, defaults: {}, params: {},
  presets: [], activePreset: null, presetMacros: null,
  align: null, render: null, rendering: false, dirty: true, queued: false,
  drawerRows: {},
};

/* ===================================================================== api */
async function api(url, body) {
  try {
    const res = await fetch(url, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    return await res.json();
  } catch (err) { return { error: String(err.message || err) }; }
}

function coerceValue(key, v) {
  const e = S.byKey[key];
  if (!e) return v;
  if (e.kind === 'i') return Math.round(Math.min(e.hi, Math.max(e.lo, v)));
  if (e.kind === 'f') return +Math.min(e.hi, Math.max(e.lo, v)).toFixed(4);
  if (e.kind === 'e') return (e.choices || []).includes(v) ? v : e.default;
  if (e.kind === 'b') return !!v;
  return v;
}
const fmtVal = (v, e) => {
  if (typeof v !== 'number') return String(v);
  const step = e?.step || 0.01;
  const dec = step >= 1 ? 0 : String(step).split('.')[1]?.length || 2;
  return v.toFixed(dec);
};

/* ================================================================== screen */
const Screen = (() => {
  const root = () => $('#screen');
  let holdTimer = 0, locked = false;

  function paint({ name, value, colour, pct, lo, hi, blurb, rows, scan }) {
    const r = root();
    r.style.setProperty('--c', colour || 'var(--vf-bone)');
    $('.sc-name', r).textContent = name ?? '';
    $('.sc-val', r).textContent = value ?? '';
    $('.sc-meter i', r).style.width = (pct == null ? 0 : pct * 100) + '%';
    $('.sc-ends .lo', r).textContent = lo || '';
    $('.sc-ends .hi', r).textContent = hi || '';
    $('.sc-blurb', r).textContent = blurb || '';
    const box = $('.sc-rows', r);
    box.replaceChildren(...(rows || []));
    box.classList.remove('stagger'); void box.offsetWidth; box.classList.add('stagger');
    $('.sc-foot', r).classList.toggle('scanning', !!scan);
    let sc = $('.sc-scan', r);
    if (scan && !sc) $('.sc-foot', r).append(el('div', { class: 'sc-scan' }));
    if (!scan && sc) sc.remove();
    r.classList.remove('swap'); void r.offsetWidth; r.classList.add('swap');
  }

  function row(k, v, onClick) {
    return el('button', { class: 'sc-row', type: 'button', ...(onClick ? { onclick: onClick } : {}) },
      el('span', { class: 'k' }, k), el('span', { class: 'v' }, v));
  }

  const api = {
    knob(def, v) {
      if (locked) return;
      clearTimeout(holdTimer);
      paint({
        name: def.label, value: String(Math.round(v * 100)).padStart(2, '0'),
        colour: def.colour, pct: v, lo: def.lo, hi: def.hi, blurb: def.blurb,
        rows: Object.keys(def.targets).map(t => {
          const raw = S.params[t];
          const unit = def.units?.[t] || '';
          const shown = typeof raw === 'number'
            ? (Math.abs(raw) >= 100 ? raw.toFixed(0) : raw.toFixed(2)) : String(raw ?? '-');
          return row(def.labels?.[t] || t, shown + (unit ? ' ' + unit : ''),
                     () => Drawer.reveal(t));
        }),
      });
    },
    preset(pr) {
      if (locked) return;
      clearTimeout(holdTimer);
      paint({
        name: pr.name, value: pr.source === 'user' ? '▪' : '',
        colour: 'var(--vf-bone)', pct: null, blurb: pr.description,
        rows: [
          pr.text ? row('demo', '“' + pr.text + '”') : null,
          pr.params?.['pitch.melody'] ? row('melody', pr.params['pitch.melody']) : null,
        ].filter(Boolean),
      });
    },
    segment(seg) {
      if (locked) return;
      clearTimeout(holdTimer);
      const ms = Math.round((seg.e - seg.s) * 1000);
      paint({
        name: seg.p, value: ms + ' ms', colour: 'var(--vf-bone)', pct: null,
        blurb: seg.cls + (seg.role ? ' · ' + seg.role : ''),
        rows: [row('start', seg.s.toFixed(3) + ' s'), row('length', ms + ' ms')],
      });
    },
    busy() {
      locked = true;
      clearTimeout(holdTimer);
      paint({ name: 'Rendering', colour: 'var(--vf-signal)', pct: null, scan: true });
    },
    error(msg) {
      locked = true;
      paint({ name: 'Err', colour: 'var(--vf-err)', pct: null, blurb: msg });
    },
    idle(delay = 0) {
      locked = false;
      clearTimeout(holdTimer);
      const go = () => {
        const pr = S.presets.find(p => p.id === S.activePreset);
        const r = S.render;
        paint({
          name: pr ? pr.name : 'Vocalforge',
          value: pr?.source === 'user' ? '▪' : '',
          colour: 'var(--vf-bone)', pct: null,
          blurb: r ? '' : 'Write a line, place some notes, turn a knob.',
          rows: r ? [
            row('length', r.duration.toFixed(2) + ' s'),
            row('peak', r.peak_db + ' dBFS'),
            row('size', (r.bytes / 1048576).toFixed(2) + ' MB'),
            row('render', r.render_time + ' s'),
          ] : [],
        });
      };
      delay ? (holdTimer = setTimeout(go, delay)) : go();
    },
    leave() { if (!locked) api.idle(3000); },
  };
  return api;
})();

/* =================================================================== scope */
const Scope = (() => {
  let ctx = null, an = null, buf = null, raf = 0;
  function init(audio) {
    if (ctx || !audio) return;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
      const src = ctx.createMediaElementSource(audio);
      an = ctx.createAnalyser(); an.fftSize = 2048; an.smoothingTimeConstant = 0.6;
      src.connect(an); an.connect(ctx.destination);
      buf = new Uint8Array(an.fftSize);
      audio.addEventListener('play', () => { ctx.resume(); start(); });
      audio.addEventListener('pause', stop);
      audio.addEventListener('ended', stop);
    } catch { ctx = null; }        // decoration only, never fatal
  }
  function frame() {
    const cv = $('.sc-scope'); if (!cv) { raf = 0; return; }
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const colour = Macros.active?.colour || Theme.get('--vf-bone');
    g.lineWidth = 1; g.strokeStyle = colour; g.beginPath();
    if (an && !$('#audio').paused) {
      an.getByteTimeDomainData(buf);
      const step = Math.max(1, Math.floor(buf.length / w));
      for (let x = 0, i = 0; x < w; x++, i += step) {
        const y = h / 2 + ((buf[i] - 128) / 128) * (h / 2 - 2);
        x ? g.lineTo(x, y) : g.moveTo(x, y);
      }
      g.stroke();
      raf = requestAnimationFrame(frame);
    } else {
      // nothing playing: a flat baseline and a stopped loop. Idle is still.
      g.strokeStyle = Theme.get('--vf-bone-ghost');
      g.moveTo(0, h / 2 + .5); g.lineTo(w, h / 2 + .5); g.stroke();
      raf = 0;
    }
  }
  const start = () => { if (!raf) raf = requestAnimationFrame(frame); };
  const stop = () => { cancelAnimationFrame(raf); raf = 0; frame(); };
  return { init, start, stop, redraw: () => { if (!raf) frame(); } };
})();

/* =================================================================== drawer */
const Drawer = (() => {
  let built = false;

  function open() {
    if (!built) build();
    $('#drawer').classList.add('open');
    $('#drawer').setAttribute('aria-hidden', 'false');
    setTimeout(() => $('#dr-q').focus(), 60);
  }
  function close() {
    $('#drawer').classList.remove('open');
    $('#drawer').setAttribute('aria-hidden', 'true');
  }
  const isOpen = () => $('#drawer').classList.contains('open');

  function help(e) {
    $('#dr-help .txt').textContent = e ? (e.help || e.label) : 'Hover a parameter for what it does.';
    $('#dr-help .key').textContent = e ? e.key : '';
  }

  function control(e) {
    const row = el('div', { class: 'dr-row' });
    row.dataset.key = e.key;
    const name = el('div', {
      class: 'dr-name', title: e.key + '\n\n(double-click to reset)',
      ondblclick: () => setParam(e.key, S.defaults[e.key]),
    }, e.label + (e.unit ? ` (${e.unit})` : ''));
    const top = el('div', { class: 'dr-top' }, name);
    row.append(top);
    row.addEventListener('pointerenter', () => help(e));

    let box = null, range = null, sw = null, sel = null;
    if (e.kind === 'b') {
      sw = el('button', { class: 'dr-switch', type: 'button', role: 'switch',
        onclick: () => setParam(e.key, !S.params[e.key]) }, el('i'));
      top.append(sw);
    } else if (e.kind === 'e') {
      sel = el('select', { oninput: ev => setParam(e.key, ev.target.value) },
        ...(e.choices || []).map(o => el('option', { value: String(o) }, String(o))));
      top.append(sel);
    } else if (e.kind === 's') {
      box = el('input', { class: 'dr-val', type: 'text', style: 'width:150px;text-align:left',
        oninput: ev => setParam(e.key, ev.target.value, false) });
      top.append(box);
    } else {
      box = el('input', { class: 'dr-val', type: 'text', inputmode: 'decimal',
        onchange: ev => {
          let v = parseFloat(ev.target.value);
          if (!isFinite(v)) v = S.defaults[e.key];
          setParam(e.key, Math.min(e.hi, Math.max(e.lo, v)));
        } });
      const logScale = e.kind === 'f' && e.lo > 0 && e.hi / e.lo >= 20;
      range = el('input', {
        type: 'range',
        min: logScale ? 0 : e.lo, max: logScale ? 1000 : e.hi,
        step: logScale ? 1 : (e.step || (e.kind === 'i' ? 1 : 0.01)),
        oninput: ev => {
          let v = parseFloat(ev.target.value);
          if (logScale) v = Math.exp(Math.log(e.lo) + (v / 1000) * (Math.log(e.hi) - Math.log(e.lo)));
          v = e.kind === 'i' ? Math.round(v) : Math.round(v / (e.step || 0.01)) * (e.step || 0.01);
          setParam(e.key, +v.toFixed(6), false);
          box.value = fmtVal(S.params[e.key], e);
          paintRow(e.key);
        },
      });
      range._log = logScale;
      top.append(box);
      row.append(el('div', { class: 'dr-bot' }, range));
    }
    S.drawerRows[e.key] = { row, box, range, sw, sel, e };
    return row;
  }

  function build() {
    built = true;
    const list = $('#dr-list');
    list.replaceChildren();
    let panel = null;
    for (const e of S.schema) {
      if (TOOLBAR_KEYS.has(e.key)) continue;
      const title = `${e.group} / ${e.panel}`;
      if (title !== panel) {
        panel = title;
        const items = S.schema.filter(x => `${x.group} / ${x.panel}` === title && !TOOLBAR_KEYS.has(x.key));
        list.append(el('div', { class: 'dr-group' }, title,
          el('div', { class: 'spacer' }),
          el('button', { class: 'btn bare', title: 'Randomise this group',
            onclick: () => randomiseGroup(items) }, 'Rnd'),
          el('button', { class: 'btn bare', title: 'Reset this group',
            onclick: () => items.forEach(x => setParam(x.key, S.defaults[x.key])) }, 'Reset')));
      }
      list.append(control(e));
    }
    for (const e of S.schema) paintRow(e.key);
    filter();
  }

  function randomiseGroup(items) {
    for (const e of items) {
      if (e.kind === 'f') {
        const d = S.defaults[e.key], span = (e.hi - e.lo) * 0.28;
        setParam(e.key, +Math.min(e.hi, Math.max(e.lo, d + (Math.random() * 2 - 1) * span)).toFixed(4), false);
      } else if (e.kind === 'i') {
        const d = S.defaults[e.key], span = Math.max(1, (e.hi - e.lo) * 0.25);
        setParam(e.key, Math.round(Math.min(e.hi, Math.max(e.lo, d + (Math.random() * 2 - 1) * span))), false);
      } else if (e.kind === 'e' && e.choices?.length) {
        setParam(e.key, e.choices[Math.floor(Math.random() * e.choices.length)], false);
      }
    }
    afterParamBatch(items.map(x => x.key));
  }

  function paintRow(key) {
    const c = S.drawerRows[key]; if (!c) return;
    const { e } = c, v = S.params[key];
    if (c.box) c.box.value = (e.kind === 'f' || e.kind === 'i') ? fmtVal(v, e) : v;
    if (c.sw) c.sw.setAttribute('aria-checked', v ? 'true' : 'false');
    if (c.sel) c.sel.value = String(v);
    if (c.range) {
      const sv = c.range._log
        ? (Math.log(Math.max(v, e.lo)) - Math.log(e.lo)) / (Math.log(e.hi) - Math.log(e.lo)) * 1000
        : v;
      c.range.value = sv;
      c.range.style.setProperty('--pct',
        ((sv - c.range.min) / (c.range.max - c.range.min) * 100) + '%');
    }
    c.row.classList.toggle('changed', JSON.stringify(v) !== JSON.stringify(S.defaults[key]));
  }

  function filter() {
    if (!built) return;
    const q = $('#dr-q').value.trim().toLowerCase();
    const only = $('#changed-only').checked;
    let shownInGroup = 0, lastGroup = null;
    for (const node of $$('#dr-list > *')) {
      if (node.classList.contains('dr-group')) {
        if (lastGroup) lastGroup.style.display = shownInGroup ? '' : 'none';
        lastGroup = node; shownInGroup = 0;
        continue;
      }
      const e = S.drawerRows[node.dataset.key]?.e;
      if (!e) continue;
      const hit = !q || e.key.toLowerCase().includes(q) ||
        e.label.toLowerCase().includes(q) || (e.help || '').toLowerCase().includes(q);
      const chg = !only || node.classList.contains('changed');
      const show = hit && chg;
      node.style.display = show ? '' : 'none';
      if (show) shownInGroup++;
    }
    if (lastGroup) lastGroup.style.display = shownInGroup ? '' : 'none';
  }

  function dirtyDot() {
    const hidden = S.schema.filter(e => !TOOLBAR_KEYS.has(e.key) && e.key !== 'pitch.melody');
    const any = hidden.some(e => JSON.stringify(S.params[e.key]) !== JSON.stringify(S.defaults[e.key]));
    $('#btn-drawer').classList.toggle('dirty', any);
  }

  return {
    open, close, isOpen, filter, paintRow, dirtyDot, help,
    toggle() { isOpen() ? close() : open(); },
    reveal(key) {
      open();
      $('#dr-q').value = ''; $('#changed-only').checked = false; filter();
      const c = S.drawerRows[key];
      if (!c) return;
      c.row.scrollIntoView({ block: 'center', behavior: 'instant' });
      c.row.classList.remove('flash'); void c.row.offsetWidth; c.row.classList.add('flash');
      help(c.e);
    },
  };
})();

/* ============================================================ param writes */
function setParam(key, value, commit = true) {
  S.params[key] = (key in S.byKey) ? coerceValue(key, value) : value;
  Drawer.paintRow(key);
  S.dirty = true;
  if (Macros.isProbe?.(key)) Macros.sync(S.params, false);
  if (commit) afterParamBatch([key]);
}

function afterParamBatch(keys) {
  Drawer.dirtyDot();
  Drawer.filter();
  if (keys.some(k => TIMING_KEYS.has(k))) scheduleAlign(false);
  if ($('#live').checked) scheduleRender();
  const a = Macros.active;
  if (a) Screen.knob(a, Macros.values[a.key] ?? 0.5);
}

/* ================================================================ alignment */
let alignSeq = 0, alignAdopt = false;
async function doAlign(adopt) {
  const seq = ++alignSeq;
  const r = await api('/api/align', { text: $('#text').value, params: S.params });
  if (seq !== alignSeq || r.error) return;
  S.align = r;
  Mel.setAlign(r, adopt);
  paintPhonemes(r);
}
const alignSoon = debounce(() => { const a = alignAdopt; alignAdopt = false; doAlign(a); }, 130);
function scheduleAlign(adopt) { if (adopt) alignAdopt = true; alignSoon(); }

function paintPhonemes(a) {
  const box = $('#phon');
  const kids = [];
  let word = -1;
  for (const s of a.segments) {
    if (s.word !== word && kids.length) kids.push(el('span', { class: 'sep' }, '·'));
    word = s.word;
    kids.push(el('span', {
      class: 'ph' + (VOWELS.test(s.p) ? ' v' : ''),
      onpointerenter: () => Screen.segment(s),
    }, s.p));
  }
  kids.push(el('span', { class: 'count' },
    `${a.syllables.length} syl · ${a.segments.length} phon`));
  box.replaceChildren(...kids);
  box.addEventListener('pointerleave', () => Screen.leave(), { once: true });
}

/* =================================================================== render */
const scheduleRender = debounce(() => doRender(), 420);

function progress(state) {
  const p = $('#progress');
  p.className = state === 'on' ? 'on' : state === 'err' ? 'on err' : '';
  if (state === 'done') {
    p.className = 'on done';
    setTimeout(() => { p.className = 'on done fade'; }, 140);
    setTimeout(() => { p.className = ''; }, 320);
  }
}

async function doRender() {
  if (S.rendering) { S.queued = true; return; }
  S.rendering = true;
  const btn = $('#btn-render');
  btn.textContent = 'Rendering'; btn.disabled = true;
  progress('on'); Screen.busy();
  $('#wave').style.opacity = '.4';

  const r = await api('/api/render', { text: $('#text').value, params: S.params });

  btn.textContent = 'Render'; btn.disabled = false;
  S.rendering = false;
  $('#wave').style.opacity = '1';

  if (r.error) { progress('err'); Screen.error(r.error); return; }
  progress('done');
  S.render = r; S.dirty = false;
  if (r.pitch) { S.align = { ...r, lead: S.align?.lead ?? 0 }; Mel.setAlign(S.align, false); }
  $('#audio').src = r.url;
  drawWave();
  Screen.idle();
  if (S.queued) { S.queued = false; scheduleRender(); }
  else if (S.autoplay) { S.autoplay = false; $('#audio').play(); }
}

/* ================================================================ waveform */
function drawWave() {
  const cv = $('#wave'), g = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * dpr; cv.height = h * dpr;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  const data = S.render?.waveform;
  if (!data?.length) {
    g.fillStyle = Theme.get('--vf-bone-ghost');
    g.font = '9px ui-monospace, monospace'; g.textBaseline = 'middle';
    g.fillText('PRESS RENDER', w / 2 - 34, h / 2);
    return;
  }
  const a = $('#audio');
  const prog = (a.duration && a.currentTime) ? a.currentTime / a.duration : 0;
  const mid = h / 2, amp = h / 2 - 3;

  g.strokeStyle = Theme.get('--vf-line');
  for (const nt of S.render.notes || []) {
    if (nt.midi == null) continue;
    const x = Math.round((nt.start / S.render.duration) * w) + .5;
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke();
  }
  // 1px columns with 1px gaps, not a continuous envelope
  const step = 2, n = data.length;
  for (const [alpha, played] of [[0.28, false], [1, true]]) {
    g.fillStyle = Theme.alpha('--vf-bone', alpha);
    for (let x = 0; x < w; x += step) {
      const i = Math.min(n - 1, Math.floor(x / w * n));
      if ((x / w <= prog) !== played) continue;
      const top = mid - data[i][1] * amp, bot = mid - data[i][0] * amp;
      g.fillRect(x, top, 1, Math.max(1, bot - top));
    }
  }
  if (prog > 0) {
    g.fillStyle = '#FFFFFF';
    g.fillRect(Math.round(prog * w), 0, 1, h);
  }
  const t = a.currentTime || 0, d = a.duration || S.render.duration || 0;
  const fmt = s => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`;
  $('#time').textContent = `${fmt(t)} / ${fmt(d)}`;
}

/* ================================================================= presets */
function renderPresets() {
  const rail = $('#presets');
  for (const n of $$('#presets .preset')) n.remove();
  rail.scrollLeft = 0;
  for (const pr of S.presets) {
    const b = el('button', {
      class: 'preset' + (pr.id === S.activePreset ? ' active' : ''),
      type: 'button',
      onclick: ev => loadPreset(pr, ev.altKey ? { keepContent: false } : {}),
      onpointerenter: () => Screen.preset(pr),
      onpointerleave: () => Screen.leave(),
    }, pr.source === 'user' ? el('i', { class: 'own' }) : null, pr.name);
    if (pr.source === 'user') {
      b.addEventListener('contextmenu', ev => {
        ev.preventDefault();
        if (confirm(`Delete preset "${pr.name}"?`)) deletePreset(pr.name);
      });
    }
    rail.append(b);
  }
}

async function loadPreset(pr, opts = {}) {
  const keep = opts.keepContent ?? $('#keep-content').checked;
  const mine = keep
    ? { text: $('#text').value,
        params: Object.fromEntries(CONTENT_KEYS.map(k => [k, S.params[k]])) }
    : null;

  S.params = { ...S.defaults, ...(pr.params || {}) };
  S.activePreset = pr.id;
  S.presetMacros = Object.keys(pr.macros || {}).length ? pr.macros : null;
  if (mine) { Object.assign(S.params, mine.params); $('#text').value = mine.text; }
  else if (pr.text) $('#text').value = pr.text;

  $('#preset-name').value = pr.source === 'user' ? pr.name : '';
  renderPresets();
  await doAlign(true);
  Macros.sync(S.params);
  if (S.presetMacros) Macros.adopt(S.presetMacros);
  syncToolbar();
  for (const e of S.schema) Drawer.paintRow(e.key);
  Drawer.dirtyDot(); Drawer.filter();
  S.dirty = true;
  Screen.idle();
  if ($('#live').checked) scheduleRender();
}

async function savePreset() {
  const name = $('#preset-name').value.trim();
  if (!name) { $('#preset-name').focus(); Screen.error('Name the voice first'); setTimeout(() => Screen.idle(), 1800); return; }
  const r = await api('/api/preset', {
    name, params: S.params, text: $('#text').value, macros: Macros.values });
  if (r.error) return Screen.error(r.error);
  S.presets = r.presets; S.activePreset = r.id;
  renderPresets(); Screen.idle();
}
async function deletePreset(name) {
  const r = await api('/api/preset/delete', { name });
  S.presets = r.presets; renderPresets();
}

/* ================================================================= toolbar */
function dragNum(key, width = 46) {
  const e = S.byKey[key];
  const n = el('div', { class: 'dragnum', title: `${e.label} — drag up/down, shift for fine`,
                        style: `width:${width}px` });
  n.dataset.key = key;
  let drag = false, lastY = 0, acc = 0;
  n.addEventListener('pointerdown', ev => {
    drag = true; lastY = ev.clientY; acc = S.params[key];
    n.setPointerCapture?.(ev.pointerId); ev.preventDefault();
  });
  n.addEventListener('pointermove', ev => {
    if (!drag) return;
    const span = (e.hi - e.lo);
    acc += (lastY - ev.clientY) * (span / (ev.shiftKey ? 1400 : 420));
    lastY = ev.clientY;
    const step = e.step || (e.kind === 'i' ? 1 : 0.01);
    const v = Math.round(Math.min(e.hi, Math.max(e.lo, acc)) / step) * step;
    setParam(key, +v.toFixed(6), false);
    syncToolbar();
  });
  const end = () => { if (drag) { drag = false; afterParamBatch([key]); } };
  n.addEventListener('pointerup', end);
  n.addEventListener('pointercancel', end);
  return n;
}

function buildToolbar() {
  const t = $('#roll-tools');
  const grp = (...k) => el('div', { class: 'tgrp' }, ...k);
  const lab = s => el('span', { class: 'lbl' }, s);
  const btn = (txt, fn, title) => el('button', { class: 'btn sm bare', type: 'button', title: title || txt, onclick: fn }, txt);

  const scaleSel = el('select', { oninput: ev => setParam('pitch.scale', ev.target.value) },
    ...(S.byKey['pitch.scale'].choices || []).map(o => el('option', { value: o }, o.replace(/_/g, ' '))));
  scaleSel.dataset.key = 'pitch.scale';

  const gridSel = el('select', { oninput: ev => Mel.setGrid(parseFloat(ev.target.value)) },
    ...[['1', 1], ['1/2', .5], ['1/3', 1 / 3], ['1/4', .25], ['1/6', 1 / 6], ['1/8', .125], ['1/16', .0625]]
      .map(([n, v]) => el('option', { value: v }, n)));
  gridSel.value = String(Mel.grid);

  const melOut = el('input', {
    id: 'melody-out', class: 'field', spellcheck: 'false',
    title: 'The melody as text — the same syntax the CLI takes with -m. Paste one here to load it.',
    onchange: ev => { S.params['pitch.melody'] = ev.target.value; S.dirty = true; scheduleAlign(true); },
  });

  t.replaceChildren(
    grp(lab('bpm'), dragNum('pitch.bpm'),
        lab('key'), dragNum('pitch.root', 44), scaleSel,
        lab('swing'), dragNum('pitch.swing', 40)),
    el('span', { class: 'divider' }),
    grp(lab('grid'), gridSel,
        lab('zoom'), btn('−', () => Mel.zoomBy(0.8), 'Zoom out'), btn('+', () => Mel.zoomBy(1.25), 'Zoom in')),
    el('span', { class: 'divider' }),
    grp(lab('oct'), btn('−12', () => Mel.edits.transpose(-12)), btn('−1', () => Mel.edits.transpose(-1)),
        btn('+1', () => Mel.edits.transpose(1)), btn('+12', () => Mel.edits.transpose(12))),
    el('span', { class: 'divider' }),
    grp(lab('len'), btn('½×', () => Mel.edits.scale(.5), 'Halve all note values'),
        btn('2×', () => Mel.edits.scale(2), 'Double all note values'),
        btn('Legato', () => Mel.edits.legato(), 'Extend every note up to the next'),
        btn('Staccato', () => Mel.edits.staccato(), 'Halve every sounding length')),
    el('span', { class: 'divider' }),
    grp(btn('Fit', () => Mel.edits.fitSyllables(), 'One note per syllable'),
        btn('Clear', () => Mel.edits.clear())),
    el('div', { class: 'tgrp end' }, lab('melody'), melOut),
  );
  syncToolbar();
}

function syncToolbar() {
  for (const n of $$('#roll-tools .dragnum')) {
    const k = n.dataset.key, e = S.byKey[k], v = S.params[k];
    n.textContent = k === 'pitch.root' ? midiName(v) : fmtVal(v, e);
  }
  const sc = $('#roll-tools select[data-key="pitch.scale"]');
  if (sc) sc.value = S.params['pitch.scale'];
  const mo = $('#melody-out');
  if (mo && document.activeElement !== mo) mo.value = S.params['pitch.melody'] || '';
}

/* ==================================================================== boot */
async function boot() {
  const s = await api('/api/schema');
  if (s.error) { Screen.error('Cannot reach the server'); return; }
  S.schema = s.schema; S.defaults = s.defaults;
  S.byKey = Object.fromEntries(s.schema.map(e => [e.key, e]));
  S.params = { ...s.defaults };

  const mk = await api('/api/macros');
  Macros.load(mk.macros || []);
  $('#btn-drawer .count').textContent =
    s.schema.filter(e => !TOOLBAR_KEYS.has(e.key)).length;

  const p = await api('/api/presets');
  S.presets = p.presets || [];

  Mel.mount($('#roll-host'), {
    onChange: text => {
      S.params['pitch.melody'] = text;
      syncToolbar();
      S.dirty = true;
      scheduleAlign(false);
      if ($('#live').checked) scheduleRender();
    },
    onSegment: seg => Screen.segment(seg),
    onLeave: () => Screen.leave(),
  });

  Macros.mount($('#knobs'), {
    audio: $('#audio'),
    isPlaying: () => !$('#audio').paused,
    onChange: updates => {
      for (const [k, v] of Object.entries(updates)) {
        S.params[k] = (k in S.byKey) ? coerceValue(k, v) : v;
        Drawer.paintRow(k);
      }
      S.dirty = true;
      if (Object.keys(updates).some(k => TIMING_KEYS.has(k))) scheduleAlign(false);
      Drawer.dirtyDot();
    },
    onScreen: (def, v) => Screen.knob(def, v),
    onLeave: () => Screen.leave(),
    onCommit: () => { if ($('#live').checked) scheduleRender(); },
  });

  buildToolbar();
  renderPresets();
  Scope.init($('#audio'));

  try {
    const saved = localStorage.getItem('vf.keepContent');
    if (saved !== null) $('#keep-content').checked = saved === '1';
  } catch { /* blocked storage — keep the default */ }
  syncKeep();

  const first = S.presets.find(x => x.id === 'breathy_diva') || S.presets[0];
  if (first) await loadPreset(first, { keepContent: false });
  else { await doAlign(true); Macros.sync(S.params); }

  bindUI();
  drawWave(); Scope.redraw(); Screen.idle();
}

function syncKeep() {
  const on = $('#keep-content').checked;
  $('#keep-latch').classList.toggle('off', !on);
  $('#keep-text').textContent = on ? 'Keep words' : 'Replace all';
}

function bindUI() {
  $('#text').addEventListener('input', () => {
    S.dirty = true; scheduleAlign(false);
    if ($('#live').checked) scheduleRender();
  });

  $('#keep-content').addEventListener('change', ev => {
    syncKeep();
    try { localStorage.setItem('vf.keepContent', ev.target.checked ? '1' : '0'); } catch {}
  });

  $('#btn-render').onclick = () => doRender();
  $('#btn-save').onclick = savePreset;
  $('#btn-random').onclick = () => Macros.randomize();
  $('#btn-knobs-reset').onclick = () => Macros.resetKnobs();
  $('#btn-reset').onclick = async () => {
    const keep = $('#keep-content').checked;
    const mine = keep ? Object.fromEntries(CONTENT_KEYS.map(k => [k, S.params[k]])) : null;
    S.params = { ...S.defaults }; S.activePreset = null;
    if (mine) Object.assign(S.params, mine);
    renderPresets();
    await doAlign(true);
    Macros.sync(S.params); syncToolbar();
    for (const e of S.schema) Drawer.paintRow(e.key);
    Drawer.dirtyDot(); Drawer.filter(); Screen.idle();
  };
  $('#btn-dl').onclick = () => {
    if (!S.render) return;
    const a = el('a', { href: S.render.url, download: 'vocalforge.wav' });
    document.body.append(a); a.click(); a.remove();
  };

  $('#btn-drawer').onclick = () => Drawer.toggle();
  $('#dr-close').onclick = () => Drawer.close();
  $('#dr-q').addEventListener('input', () => Drawer.filter());
  $('#changed-only').addEventListener('change', () => Drawer.filter());

  const audio = $('#audio');
  const toggle = () => {
    if (!S.render || S.dirty) { S.autoplay = true; return doRender(); }
    audio.paused ? audio.play() : audio.pause();
  };
  $('#btn-play').onclick = toggle;
  audio.addEventListener('play', () => {
    $('#btn-play').textContent = '❚❚';
    $('#btn-play').classList.add('playing');
    Macros.kick();
    const loop = () => { drawWave(); if (!audio.paused) requestAnimationFrame(loop); };
    loop();
  });
  ['pause', 'ended'].forEach(e => audio.addEventListener(e, () => {
    $('#btn-play').textContent = '▶';
    $('#btn-play').classList.remove('playing');
    drawWave();
  }));
  $('#wave').addEventListener('click', ev => {
    if (!audio.duration) return;
    const r = ev.currentTarget.getBoundingClientRect();
    audio.currentTime = ((ev.clientX - r.left) / r.width) * audio.duration;
    drawWave();
  });

  document.addEventListener('keydown', ev => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName);
    const mod = ev.metaKey || ev.ctrlKey;
    if (mod && ev.key === 'Enter') { ev.preventDefault(); doRender(); }
    else if (mod && ev.key.toLowerCase() === 'k') { ev.preventDefault(); Drawer.toggle(); }
    else if (mod && ev.key.toLowerCase() === 's') { ev.preventDefault(); savePreset(); }
    else if (ev.key === 'Escape' && Drawer.isOpen()) { ev.preventDefault(); Drawer.close(); }
    else if (ev.code === 'Space' && !typing) { ev.preventDefault(); toggle(); }
  });

  new ResizeObserver(() => { drawWave(); Scope.redraw(); }).observe($('#wave'));
}

boot();
