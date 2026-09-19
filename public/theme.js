/* Single source of truth for colours used by canvas drawing code.

   CSS owns the palette; canvas code cannot read custom properties directly,
   so this resolves them once and caches. Call Theme.refresh() after anything
   that changes the palette (theme switch, custom accent) and the next frame
   picks up the new values. */
'use strict';

const Theme = (() => {
  let cache = new Map();
  let root = null;

  function raw(name) {
    if (cache.has(name)) return cache.get(name);
    root = root || getComputedStyle(document.documentElement);
    let v = root.getPropertyValue(name).trim();
    if (!v) v = '';
    cache.set(name, v);
    return v;
  }

  return {
    /** Resolve a --custom-property, with an optional fallback colour. */
    get(name, fallback = '#888') {
      const v = raw(name.startsWith('--') ? name : '--' + name);
      return v || fallback;
    },
    /** Same, as a number (for sizes/durations stored as tokens). */
    num(name, fallback = 0) {
      const v = parseFloat(this.get(name, ''));
      return isFinite(v) ? v : fallback;
    },
    /** Colour with an alpha applied, accepting #rgb/#rrggbb tokens. */
    alpha(name, a, fallback = '#888') {
      const c = this.get(name, fallback);
      const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c);
      if (!m) return c;
      let h = m[1];
      if (h.length === 3) h = h.split('').map(x => x + x).join('');
      const n = parseInt(h, 16);
      return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
    },
    refresh() { cache = new Map(); root = null; },
  };
})();
