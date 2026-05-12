/**
 * statusBars.js
 *
 * Drop-in status bar widget. Each bar shows a value as a percentage of its
 * max, coloured green below a threshold and red above.
 *
 * Safe to call update() / updateDynamic() before init() — queued and replayed.
 *
 * ─── STATIC BAR (fixed threshold & max from config) ──────────────────────────
 *
 * statusBars.init('my-container', [
 *   { key: 'delay',   label: 'UI Delay', unit: ' sec', decimals: 2, max: 2.0,  threshold: 1.0 },
 *   { key: 'loopCpu', label: 'Loop CPU', unit: ' %',   decimals: 1, max: 200,  threshold: 110 },
 *   { key: 'effSps',  label: 'Eff. SPS', unit: ' Msps',decimals: 6, max: null, threshold: null },
 *   //                                                      max/threshold null → dynamic only
 * ]);
 *
 * // In your polling routine:
 * statusBars.update('delay',   sdrState.getUiDelay());
 * statusBars.update('loopCpu', sdrState.getLoopCpuPc());
 *
 * ─── DYNAMIC BAR (threshold and/or max supplied at call time) ─────────────────
 *
 * statusBars.updateDynamic('effSps', {
 *   value:     sdrState.getEffectiveSps(),
 *   max:       sdrState.getSps() / 1e6,   // sets bar width scale
 *   threshold: 0.99 * (sdrState.getSps() / 1e6),  // green above, red below
 *   thresholdMode: 'below',   // 'below' → red when value < threshold (default: 'above')
 * });
 *
 * updateDynamic() options
 * -----------------------
 *   value          (required) raw numeric value
 *   max            bar width scale; falls back to config max if omitted
 *   threshold      colour boundary; falls back to config threshold if omitted
 *   thresholdMode  'above' (default) → red when value >= threshold
 *                  'below'           → red when value <  threshold
 *
 * The threshold marker on the bar tracks the dynamic threshold automatically.
 */

const statusBars = (() => {

  /* ── colours ─────────────────────────────────────────── */
  const COL_GREEN  = '#3B6D11';
  const COL_RED    = '#A32D2D';
  const COL_FILL_G = '#639922';
  const COL_FILL_R = '#E24B4A';
  const COL_TRACK  = 'rgba(128,128,128,0.15)';

  /* ── internal state ──────────────────────────────────── */
  const bars    = {};
  const pending = [];
  let   ready   = false;

  /* ── helpers ─────────────────────────────────────────── */
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function el(tag, style, text) {
    const e = document.createElement(tag);
    if (style) Object.assign(e.style, style);
    if (text !== undefined) e.textContent = text;
    return e;
  }

  /* ── build DOM for one bar ───────────────────────────── */
  function buildBar(container, cfg) {
    const wrap = el('div', { marginBottom: '10px', fontFamily: 'sans-serif' });

    const labelRow = el('div', {
      display: 'flex', justifyContent: 'space-between',
      alignItems: 'baseline', marginBottom: '3px',
    });
    const labelEl = el('span', { fontSize: '12pt', color: '#888', userSelect: 'none' }, cfg.label);
    const valueEl = el('span', {
      fontSize: '13pt', fontWeight: '600',
      color: COL_GREEN, transition: 'color 0.2s',
    }, '\u2014');
    labelRow.append(labelEl, valueEl);

    const track = el('div', {
      position: 'relative', height: '14px',
      background: COL_TRACK, borderRadius: '3px', overflow: 'hidden',
    });

    const fill = el('div', {
      position: 'absolute', top: '0', left: '0', bottom: '0',
      width: '0%', background: COL_FILL_G, borderRadius: '3px',
      transition: 'width 0.2s ease, background 0.2s ease',
    });

    const marker = el('div', {
      position: 'absolute', top: '0', bottom: '0', width: '1px',
      background: 'rgba(0,0,0,0.35)',
      left: (cfg.threshold != null && cfg.max != null)
        ? clamp((cfg.threshold / cfg.max) * 100, 0, 100) + '%'
        : '0%',
    });

    track.append(fill, marker);
    wrap.append(labelRow, track);
    container.appendChild(wrap);

    bars[cfg.key] = {
      cfg,
      els: { valueEl, fill, marker },
      lastValue: undefined,
      lastMax: undefined,
      lastThreshold: undefined,
    };
  }

  /* ── core render (shared by update and updateDynamic) ── */
  function render(bar, value, max, threshold, thresholdMode) {
    const { cfg, els } = bar;
    const rounded = value.toFixed(cfg.decimals);

    /* skip if nothing changed */
    if (bar.lastValue     === rounded   &&
        bar.lastMax       === max       &&
        bar.lastThreshold === threshold) return;

    bar.lastValue     = rounded;
    bar.lastMax       = max;
    bar.lastThreshold = threshold;

    const pct   = max > 0 ? (value / max) * 100 : 0;
    const isRed = (thresholdMode === 'below')
      ? value < threshold
      : value >= threshold;

    els.valueEl.textContent   = rounded + (cfg.unit || '');
    els.valueEl.style.color   = isRed ? COL_RED    : COL_GREEN;
    els.fill.style.width      = clamp(pct, 0, 100).toFixed(2) + '%';
    els.fill.style.background = isRed ? COL_FILL_R : COL_FILL_G;

    /* move threshold marker */
    const markerPct = (max > 0 && threshold != null)
      ? clamp((threshold / max) * 100, 0, 100)
      : 0;
    els.marker.style.left = markerPct.toFixed(2) + '%';
  }

  /* ── guard: look up bar or warn ──────────────────────── */
  function getBar(key, caller) {
    const bar = bars[key];
    if (!bar) {
      console.warn(
        'statusBars.' + caller + ': unknown key "' + key + '".' +
        ' Known keys: ' + Object.keys(bars).join(', ')
      );
    }
    return bar || null;
  }

  /* ── public API ──────────────────────────────────────── */

  /**
   * init(containerId, configArray)
   * Renders bars into the element with the given id.
   * Flushes any queued update/updateDynamic calls immediately after.
   *
   * Config fields:  key, label, unit, decimals, max, threshold
   * Set max/threshold to null for bars that will always use updateDynamic().
   */
  function init(containerId, configArray) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.error('statusBars.init: no element found with id "' + containerId + '"');
      return;
    }
    container.innerHTML = '';
    Object.assign(container.style, {
      padding: '8px 10px', background: 'rgba(0,0,0,0.05)',
      borderRadius: '5px', minWidth: '200px',
    });

    configArray.forEach(cfg => buildBar(container, cfg));
    ready = true;

    while (pending.length) {
      const item = pending.shift();
      if (item.type === 'dynamic') {
        updateDynamic(item.key, item.opts);
      } else {
        update(item.key, item.rawValue);
      }
    }
  }

  /**
   * update(key, value)
   * For bars with static max and threshold defined in config.
   */
  function update(key, rawValue) {
    if (!ready) { pending.push({ type: 'static', key, rawValue }); return; }

    const bar = getBar(key, 'update');
    if (!bar) return;

    const { cfg } = bar;
    if (cfg.max == null || cfg.threshold == null) {
      console.warn('statusBars.update: "' + key + '" has no static max/threshold — use updateDynamic()');
      return;
    }

    render(bar, parseFloat(rawValue), cfg.max, cfg.threshold, 'above');
  }

  /**
   * updateDynamic(key, opts)
   * For bars where max and/or threshold change at runtime.
   *
   * opts = {
   *   value,                    // (required) current reading
   *   max,                      // bar scale; falls back to config max
   *   threshold,                // colour boundary; falls back to config threshold
   *   thresholdMode,            // 'above' (default) or 'below'
   * }
   *
   * Example — effective SPS bar:
   *   statusBars.updateDynamic('effSps', {
   *     value:         sdrState.getEffectiveSps(),
   *     max:           sdrState.getSps() / 1e6,
   *     threshold:     0.99 * (sdrState.getSps() / 1e6),
   *     thresholdMode: 'below',
   *   });
   */
  function updateDynamic(key, opts) {
    if (!ready) { pending.push({ type: 'dynamic', key, opts }); return; }

    const bar = getBar(key, 'updateDynamic');
    if (!bar) return;

    const { cfg } = bar;
    const value         = parseFloat(opts.value);
    const max           = (opts.max       != null) ? parseFloat(opts.max)       : cfg.max;
    const threshold     = (opts.threshold != null) ? parseFloat(opts.threshold) : cfg.threshold;
    const thresholdMode = opts.thresholdMode || 'above';

    if (max == null || threshold == null) {
      console.warn('statusBars.updateDynamic: "' + key + '" — max or threshold still null');
      return;
    }

    render(bar, value, max, threshold, thresholdMode);
  }

  return { init, update, updateDynamic };

})();
