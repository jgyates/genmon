/* ============================================================
   Genmon v2 — Main Application
   jQuery 4 SPA with dark/light themes, live polling, SVG gauges
   ============================================================ */

;(function($, window, undefined) {
'use strict';

/* ============================================================
   CONFIG
   ============================================================ */
var CFG = {
  baseUrl:      '/cmd/',
  pollMs:       3000,   // gui_status_json
  pagePollMs:   5000,   // page-specific data
  regPollMs:    1000,   // register view
  ajaxTimeout:  4000,
  storageKey:   'genmon_v2',
  version:      '2.0.0'
};

/* ============================================================
   STATE
   ============================================================ */
var S = {
  startInfo:     null,
  currentPage:   null,
  baseStatus:    'READY',
  switchState:   'Auto',
  writeAccess:   false,
  useMetric:     false,
  connected:     true,
  gauges:        [],
  tileConfig:    [],
  chart:         null,
  regLabels:     null,
  prevRegData:   null,
  regTimestamps: {},
  dirty:         {}   /* pages with unsaved changes, e.g. {settings:true, journal:true} */
};

/* ============================================================
   UTILITIES
   ============================================================ */
var _escEl = document.createElement('div');
function esc(s) {
  if (s == null) return '';
  _escEl.textContent = String(s);
  return _escEl.innerHTML;
}
/** Allow only safe inline HTML tags (br, b, i, em, strong, font with color attr) */
function safeHtml(s) {
  if (s == null) return '';
  /* First escape everything, then selectively un-escape known safe tags */
  var h = esc(s);
  h = h.replace(/&lt;br\s*\/?&gt;/gi, '<br>');
  h = h.replace(/&lt;(\/?(?:b|i|em|strong))&gt;/gi, '<$1>');
  h = h.replace(/&lt;font\s+color=(?:&apos;|&#39;|&quot;|')([a-zA-Z]+)(?:&apos;|&#39;|&quot;|')&gt;/gi, '<span style="color:$1">');
  h = h.replace(/&lt;\/font&gt;/gi, '</span>');
  return h;
}
function roundNum(v) {
  var n = parseFloat(v);
  if (isNaN(n)) return v;
  return parseFloat(n.toPrecision(12));
}
function formatVal(v, u) {
  if (v == null || v === '') return '--';
  return esc(roundNum(v)) + (u ? ' <span class="unit">' + esc(u) + '</span>' : '');
}
function statusKey(bs) {
  if (!bs) return 'ready';
  var m = {
    'ready':'ready','alarm':'alarm','exercising':'exercise',
    'running':'running','running-manual':'running-manual',
    'servicedue':'service','off':'off','manual':'manual'
  };
  return m[String(bs).toLowerCase().replace(/\s+/g,'-')] || 'ready';
}

/* ============================================================
   STORE  (server-backed persistence via genmon.conf ui_prefs)
   ============================================================ */
var Store = {
  _c: {},
  _syncTimer: null,
  _loaded: false,   /* true only after a successful pull — guards against overwriting server data */

  /* Pull prefs from server (synchronous, called once at init) */
  _pull: function() {
    try {
      var raw = $.ajax({url: CFG.baseUrl + 'get_ui_prefs',
        dataType:'text', async:false, timeout:4000}).responseText;
      if (raw && raw.charAt(0) === '{') {
        var d = JSON.parse(raw);
        if (d && typeof d === 'object') {
          if (Object.keys(d).length) this._c = d;
          this._loaded = true;   /* server responded with valid JSON (even if empty) */
        }
      }
    } catch(e) { /* server unavailable — _loaded stays false, writes are blocked */ }
  },

  /* Push prefs to server (debounced 2s, fire-and-forget) */
  _push: function() {
    if (!this._loaded) return;
    var self = this;
    clearTimeout(this._syncTimer);
    this._syncTimer = setTimeout(function() { self._flush(); }, 2000);
  },
  _flush: function() {
    if (!this._loaded) return;   /* never overwrite server data if we failed to load */
    clearTimeout(this._syncTimer);
    try {
      $.ajax({url: CFG.baseUrl + 'set_ui_prefs?set_ui_prefs=' +
        encodeURIComponent(JSON.stringify(this._c)),
        dataType:'text', timeout:4000});
    } catch(e) {}
  },

  get: function(k, d) { var v = this._c[k]; return v !== undefined ? v : d; },
  set: function(k, v) { this._c[k] = v; this._push(); },
  /* tile prefs: { order: ['info-switch','battery-voltage',...], hidden: {'cpu-temp':true}, sizes: {'battery-voltage':'lg'} } */
  getDash: function() { return this.get('dash', {}); },
  setDash: function(d) { this.set('dash', d); },
  /* Generate a stable slug from a tile title, e.g. "Battery Voltage" -> "battery-voltage" */
  slugify: function(title) {
    return (title||'').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'tile';
  },
  /* Build the canonical key list from info tiles + gauge tiles + special keys.
     Also migrates any legacy numeric prefs to string keys. */
  buildKeyMap: function(infoTiles, gaugeTiles, specialKeys) {
    var allKeys = [];
    var numToKey = {};  /* legacy numeric index -> string key */
    var keyToGauge = {}; /* string key -> gauge array index */
    /* Info tiles: use their .id */
    for (var i = 0; i < infoTiles.length; i++) {
      var ik = infoTiles[i].id;
      allKeys.push(ik);
      numToKey[i] = ik;
    }
    /* Gauge tiles: slugify title (deduplicate with suffix if needed) */
    /* Skip graph-type tiles (powergraph) — they render as the special chart tile */
    var seen = {};
    for (var g = 0; g < gaugeTiles.length; g++) {
      if ((gaugeTiles[g].type||'').toLowerCase() === 'graph') continue;
      var base = this.slugify(gaugeTiles[g].title || gaugeTiles[g].subtype || ('gauge-' + g));
      var key = base;
      if (seen[key]) { var n = 2; while (seen[key + '-' + n]) n++; key = key + '-' + n; }
      seen[key] = true;
      allKeys.push(key);
      numToKey[infoTiles.length + g] = key;
      keyToGauge[key] = g;
    }
    /* Special keys */
    if (specialKeys) for (var s = 0; s < specialKeys.length; s++) allKeys.push(specialKeys[s]);
    return { allKeys: allKeys, numToKey: numToKey, keyToGauge: keyToGauge };
  },
  /* Migrate legacy numeric prefs inside a dash object to string keys */
  _migrateDash: function(d, numToKey) {
    var dominated = false;
    /* Migrate order array */
    if (Array.isArray(d.order)) {
      for (var i = 0; i < d.order.length; i++) {
        if (typeof d.order[i] === 'number' && numToKey[d.order[i]] !== undefined) {
          d.order[i] = numToKey[d.order[i]];
          dominated = true;
        }
      }
    }
    /* Migrate keyed maps (hidden, sizes, fontSizes, gaugeTypes) */
    var maps = ['hidden', 'sizes', 'fontSizes', 'gaugeTypes'];
    for (var mi = 0; mi < maps.length; mi++) {
      var m = d[maps[mi]];
      if (!m) continue;
      var keys = Object.keys(m);
      for (var ki = 0; ki < keys.length; ki++) {
        var nk = parseInt(keys[ki], 10);
        if (!isNaN(nk) && numToKey[nk] !== undefined) {
          m[numToKey[nk]] = m[keys[ki]];
          delete m[keys[ki]];
          dominated = true;
        }
      }
    }
    return dominated;
  },
  getTileOrder: function(allKeys, numToKey) {
    var d = this.getDash(), o = d.order;
    /* Migrate legacy numeric values if present */
    if (numToKey && this._migrateDash(d, numToKey)) {
      this.setDash(d);
      o = d.order;
    }
    if (!Array.isArray(o) || !o.length) return allKeys.slice();
    /* Rebuild from saved order — filter invalid, append missing */
    var result = [], seen = {};
    for (var k = 0; k < o.length; k++) {
      var key = o[k];
      if (!seen[key] && allKeys.indexOf(key) !== -1) { result.push(key); seen[key] = true; }
    }
    for (var m = 0; m < allKeys.length; m++) {
      if (!seen[allKeys[m]]) result.push(allKeys[m]);
    }
    return result;
  },
  setTileOrder: function(order) { var d = this.getDash(); d.order = order; this.setDash(d); },
  isTileHidden: function(i) { var d = this.getDash(); return d.hidden && d.hidden[i] === true; },
  setTileHidden: function(i, hide) {
    var d = this.getDash();
    if (!d.hidden) d.hidden = {};
    if (hide) d.hidden[i] = true; else delete d.hidden[i];
    this.setDash(d);
  },
  getTileSize: function(i) { var d = this.getDash(); return (d.sizes && d.sizes[i]) || null; },
  setTileSize: function(i, sz) {
    var d = this.getDash();
    if (!d.sizes) d.sizes = {};
    if (sz) d.sizes[i] = sz; else delete d.sizes[i];
    this.setDash(d);
  },
  getTileFontSize: function(i) { var d = this.getDash(); return (d.fontSizes && d.fontSizes[i]) || null; },
  setTileFontSize: function(i, sz) {
    var d = this.getDash();
    if (!d.fontSizes) d.fontSizes = {};
    if (sz) d.fontSizes[i] = sz; else delete d.fontSizes[i];
    this.setDash(d);
  },
  getGaugeType: function(i) { var d = this.getDash(); return (d.gaugeTypes && d.gaugeTypes[i]) || null; },
  setGaugeType: function(i, t) {
    var d = this.getDash();
    if (!d.gaugeTypes) d.gaugeTypes = {};
    if (t) d.gaugeTypes[i] = t; else delete d.gaugeTypes[i];
    this.setDash(d);
  },
  getChartSize: function() { var d = this.getDash(); return d.chartSize || null; },
  setChartSize: function(sz) { var d = this.getDash(); d.chartSize = sz; this.setDash(d); },
  resetDash: function() { this.set('dash', {}); }
};

/* ============================================================
   THEME
   ============================================================ */
var Theme = {
  init: function() { this.apply(Store.get('theme','dark')); },
  toggle: function() {
    this.apply($('html').attr('data-theme') === 'dark' ? 'light' : 'dark');
  },
  apply: function(t) {
    $('html').attr('data-theme', t);
    Store.set('theme', t);

    /* refresh Chart.js colors that can't use CSS var() */
    if (S.chart) {
      var cs = getComputedStyle(document.documentElement);
      var g = cs.getPropertyValue('--chart-grid').trim() || 'rgba(148,163,184,.1)';
      var k = cs.getPropertyValue('--chart-tick').trim() || '#94a3b8';
      var sx = S.chart.options.scales;
      sx.x.grid.color = g; sx.x.ticks.color = k;
      sx.y.grid.color = g; sx.y.ticks.color = k;
      S.chart.update('none');
    }
  }
};

/* ============================================================
   API
   ============================================================ */
var API = {
  _errs: 0,
  get: function(cmd, timeout) {
    return $.ajax({
      url: CFG.baseUrl + cmd, dataType: 'json',
      timeout: timeout || CFG.ajaxTimeout, cache: false
    }).done(function() {
      API._errs = 0;
      if (!S.connected) { S.connected = true; UI.connBadge(); }
    }).fail(function(xhr) {
      API._errs++;
      // Detect auth redirect
      if (xhr.responseText && xhr.responseText.indexOf('<form') >= 0) {
        window.location.href = '/';
        return;
      }
      if (API._errs > 3 && S.connected) { S.connected = false; UI.connBadge(); }
    });
  },
  set: function(cmd, val, timeout) {
    return $.ajax({
      url: CFG.baseUrl + cmd + '?' + cmd + '=' + encodeURIComponent(val),
      dataType: 'text', timeout: timeout || CFG.ajaxTimeout * 3, cache: false
    });
  }
};

/* ============================================================
   MODAL
   ============================================================ */
var Modal = {
  _$ov: null,
  _cb: null,
  /** Mark a string as pre-escaped HTML so Modal.show() won't double-escape it */
  html: function(s) { return {_trusted: true, _html: s}; },
  init: function() { this._$ov = $('#modal-overlay'); },
  show: function(title, body, buttons) {
    var bh = '';
    if (buttons) buttons.forEach(function(b) {
      bh += '<button class="btn ' + (b.cls||'btn-outline') + '" data-action="' +
            esc(b.action||'close') + '">' + esc(b.text) + '</button>';
    });
    this._$ov.html(
      '<div class="modal"><div class="modal-header">' + esc(title) +
      '<button class="modal-close" data-action="close">&times;</button></div>' +
      '<div class="modal-body">' + (body._trusted ? body._html : esc(body)) + '</div>' +
      (bh ? '<div class="modal-footer">' + bh + '</div>' : '') +
      '</div>'
    ).removeClass('hidden');
    var self = this;
    this._$ov.find('[data-action]').off('click').on('click', function() {
      var a = $(this).data('action');
      if (a === 'close') self.close();
      else if (self._cb) self._cb(a, self._$ov.find('.modal'));
    });
    return this;
  },
  onAction: function(fn) { this._cb = fn; return this; },
  close: function() { this._$ov.addClass('hidden').html(''); this._cb = null; },
  alert: function(t, m) {
    this.show(t, Modal.html('<p>' + (m && m._trusted ? m._html : esc(m)) + '</p>'), [{text:'OK',cls:'btn-primary',action:'close'}]);
  },
  confirm: function(t, m, fn, cancelFn) {
    this.show(t, Modal.html('<p>' + (m && m._trusted ? m._html : esc(m)) + '</p>'), [
      {text:'Cancel',action:'close'}, {text:'Confirm',cls:'btn-primary',action:'yes'}
    ]).onAction(function(a) { if (a==='yes') { Modal.close(); if (fn) fn(); } else { if (cancelFn) cancelFn(); } });
  },
  prompt: function(t, label, def, fn) {
    this.show(t, Modal.html(
      '<div class="form-group"><label class="form-label">' + esc(label) + '</label>' +
      '<input class="form-input" id="modal-input" value="' + esc(def||'') + '"></div>'),
      [{text:'Cancel',action:'close'}, {text:'OK',cls:'btn-primary',action:'ok'}]
    ).onAction(function(a, $m) {
      if (a==='ok') { var v=$m.find('#modal-input').val(); Modal.close(); if (fn) fn(v); }
    });
  },
  /* Restart modal: shows spinner + countdown, polls backend, auto-dismiss */
  restart: function(msg, newUrl) {
    var self = this, secs = 20, timer = null, poller = null, alive = false;
    var redirectMode = !!newUrl;
    var body = '<div class="restart-modal">' +
      '<div class="restart-spinner"></div>' +
      '<p class="restart-msg">' + esc(msg || 'Settings saved. Service is restarting…') + '</p>' +
      (redirectMode
        ? '<p class="restart-countdown">Redirecting to <b>' + esc(newUrl) + '</b> in <span id="restart-secs">' + secs + '</span>s…</p>'
        : '<p class="restart-countdown">Waiting <span id="restart-secs">' + secs + '</span>s for service…</p>') +
      '<div class="restart-bar-track"><div class="restart-bar-fill" id="restart-bar"></div></div>' +
      '</div>';
    this._$ov.html(
      '<div class="modal restart-modal-wrap">' +
      '<div class="modal-header">Restarting' +
      '</div>' +
      '<div class="modal-body">' + body + '</div></div>'
    ).removeClass('hidden');
    /* disable normal close */
    this._$ov.find('[data-action]').off('click');
    this._cb = null;
    var total = secs, elapsed = 0;
    function tick() {
      elapsed++;
      var rem = total - elapsed;
      $('#restart-secs').text(Math.max(rem, 0));
      var pct = Math.min(elapsed / total * 100, 100);
      $('#restart-bar').css('width', pct + '%');
      if (rem <= 0 && !alive) {
        /* extend — keep waiting */
        total += 10;
      }
    }
    function poll() {
      var target = redirectMode ? newUrl + 'getbase' : CFG.baseUrl + 'getbase';
      $.ajax({ url: target, dataType: 'json', timeout: 3000, cache: false })
        .done(function(d) {
          if (d && d !== 'Closing') {
            alive = true;
            clearInterval(timer);
            clearInterval(poller);
            if (redirectMode) {
              location.href = newUrl;
            } else {
              self.close();
              S.connected = true; UI.connBadge(); API._errs = 0;
              Pages.render(S.currentPage);
            }
          }
        })
        .fail(function() {
          if (redirectMode && elapsed >= 30) {
            /* Server not reachable at new URL after extended wait.
               Show a manual link instead of redirecting to an error page. */
            clearInterval(timer);
            clearInterval(poller);
            $('.restart-spinner').hide();
            $('.restart-countdown').html(
              'The server is running but your browser cannot reach it at the new address.<br>' +
              'This usually means the certificate is not yet trusted.<br><br>' +
              '<a href="' + esc(newUrl) + '" style="color:var(--accent);font-weight:600">' +
              'Click here to open ' + esc(newUrl) + '</a><br>' +
              '<span style="font-size:.85em;color:var(--text-muted)">If you see a certificate warning, accept it and import the CA certificate from Settings.</span>'
            );
          }
        });
    }
    /* Start after 3s grace period (backend needs time to enter restart state) */
    setTimeout(function() {
      timer = setInterval(tick, 1000);
      poller = setInterval(poll, 2500);
    }, 3000);
  }
};

/* ============================================================
   ICONS  (inline SVG paths – Feather-style)
   ============================================================ */
var ICONS = {
  status:        '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
  maintenance:   '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>',
  outage:        '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  logs:          '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  monitor:       '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  notifications: '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>',
  journal:       '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>',
  settings:      '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  addons:        '<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
  about:         '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  registers:     '<rect x="4" y="4" width="16" height="16" rx="2"/><line x1="9" y1="4" x2="9" y2="20"/><line x1="15" y1="4" x2="15" y2="20"/><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/>',
  advanced:      '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
  /* Extra icons for buttons & settings categories */
  home:          '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  shield:        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  lock:          '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>',
  user:          '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  wifi:          '<path d="M5 12.55a11 11 0 0114.08 0"/><path d="M1.42 9a16 16 0 0121.16 0"/><path d="M8.53 16.11a6 6 0 016.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
  cloud:         '<path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z"/>',
  cpu:           '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
  mail:          '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22 6 12 13 2 6"/>',
  save:          '<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
  download:      '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  upload:        '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  plus:          '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  trash:         '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>',
  play:          '<polygon points="5 3 19 12 5 21 5 3"/>',
  stop:          '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>',
  power:         '<path d="M18.36 6.64a9 9 0 11-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/>',
  refresh:       '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>',
  clock:         '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  check:         '<polyline points="20 6 9 17 4 12"/>',
  search:        '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  warning:       '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  modbus:        '<rect x="4" y="4" width="16" height="16" rx="2"/><line x1="9" y1="4" x2="9" y2="20"/><line x1="15" y1="4" x2="15" y2="20"/><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/>',
  zap:           '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  archive:       '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
  droplet:       '<path d="M12 2.69l5.66 5.66a8 8 0 11-11.31 0z"/>',
  wind:          '<path d="M9.59 4.59A2 2 0 1111 8H2m10.59 11.41A2 2 0 1014 16H2m15.73-8.27A2.5 2.5 0 1119.5 12H2"/>',
  sort:          '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',
  clipboard:     '<path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>'
};
function icon(name) {
  return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    (ICONS[name]||ICONS.about) + '</svg>';
}
/** Small icon for placement inside buttons */
function btnIcon(name, sz) {
  sz = sz || 14;
  return '<svg class="btn-ico" width="'+sz+'" height="'+sz+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    (ICONS[name]||'') + '</svg>';
}
/**
 * Download a CA cert via fetch+blob to bypass Chrome's insecure-origin
 * download restriction.  Falls back to showing the PEM text inline.
 */
function _certDL(url, filename) {
  var st = document.getElementById('cert-dl-status');
  if (st) { st.style.display = 'none'; st.textContent = ''; }
  fetch(url).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.blob();
  }).then(function(blob) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 200);
    /* Show post-download hint */
    if (st) {
      st.innerHTML = '<span style="color:var(--green)">' + icon('check') +
        '</span> <strong>' + filename + '</strong> saved to Downloads. ' +
        'Now double-click it and follow the steps below.';
      st.style.display = '';
    }
  })['catch'](function() {
    /* Download blocked — fetch PEM text and show fallback textarea */
    fetch('/download/ca.pem').then(function(r){ return r.text(); }).then(function(pem) {
      var fb = document.getElementById('cert-pem-fallback');
      var ta = document.getElementById('cert-pem-text');
      if (fb && ta) { ta.value = pem; fb.style.display = ''; }
    })['catch'](function(){
      if (st) {
        st.innerHTML = icon('warning') + ' Could not download. Make sure the server is running with Local CA mode enabled.';
        st.style.display = '';
      }
    });
  });
}
window._certDL = _certDL;

/* ============================================================
   NAV
   ============================================================ */
var NAV_ITEMS = [
  { id:'status',        label:'Dashboard',       page:'status',        icon:'status' },
  { id:'maintenance',   label:'Maintenance',     page:'maint',         icon:'maintenance' },
  { id:'outage',        label:'Outage',          page:'outage',        icon:'outage' },
  { id:'logs',          label:'Logs',            page:'logs',          icon:'logs' },
  { id:'monitor',       label:'Monitor',         page:'monitor',       icon:'monitor' },
  { id:'journal',       label:'Service Journal', page:'journal',       icon:'journal' },
  { id:'settings',      label:'Settings',        page:'settings',      icon:'settings' },
  { id:'registers',     label:'Modbus',          page:'registers',     icon:'modbus' },
  { id:'addons',        label:'Add-Ons',         page:'addons',        icon:'addons' },
  { id:'about',         label:'About',           page:'about',         icon:'about' }
];

var Nav = {
  build: function(pages) {
    var showModbus = Store.get('showModbus', true);
    var h = '';
    NAV_ITEMS.forEach(function(n) {
      if (!pages || pages[n.page] !== false) {
        if (n.id === 'registers' && !showModbus) return;
        h += '<a class="nav-item" href="#' + n.id + '" data-page="' + n.id + '">' +
             icon(n.icon) + '<span>' + esc(n.label) + '</span></a>';
      }
    });
    $('#nav-menu').html(h).on('click', '.nav-item', function(e) {
      e.preventDefault();
      Router.go($(this).data('page'));
      Nav.closeMobile();
    });
  },
  setActive: function(id) {
    $('.nav-item').removeClass('active');
    $('.nav-item[data-page="'+id+'"]').addClass('active');
  },
  toggleMobile: function() {
    $('#sidebar').hasClass('open') ? Nav.closeMobile() : Nav.openMobile();
  },
  openMobile: function() {
    $('#sidebar').addClass('open');
    $('#sidebar-overlay').addClass('visible');
  },
  closeMobile: function() {
    $('#sidebar').removeClass('open');
    $('#sidebar-overlay').removeClass('visible');
  }
};

/* ============================================================
   ROUTER
   ============================================================ */
var Router = {
  _navigate: function(page) {
    /* Cleanup previous page */
    if (S.currentPage === 'status' && Pages.status._clockTimer) {
      clearInterval(Pages.status._clockTimer);
      Pages.status._clockTimer = null;
    }
    delete S.dirty[S.currentPage];
    S.currentPage = page;
    Nav.setActive(page);
    window.location.hash = '#' + page;
    $('#customize-btn').toggle(page === 'status').removeClass('edit-active');
    S.editMode = false;
    Pages.render(page);
    /* page entrance animation */
    var $c = $('#content');
    $c.removeClass('page-enter');
    void $c[0].offsetWidth;          /* reflow to restart animation */
    $c.addClass('page-enter');
    Poll.setPage(page);
  },
  go: function(page) {
    if (S.currentPage === page) return;
    if (S.dirty[S.currentPage]) {
      var prev = S.currentPage;
      Modal.confirm('Unsaved Changes',
        'You have unsaved changes. Discard them?',
        function() { delete S.dirty[prev]; Router._navigate(page); },
        function() { /* stay — restore hash */ window.location.hash = '#' + prev; }
      );
      return;
    }
    Router._navigate(page);
  },
  init: function() {
    var h = window.location.hash.replace('#','') || 'status';
    if (h === 'advanced') h = 'settings'; /* advanced merged into settings */
    var valid = NAV_ITEMS.some(function(n){return n.id===h;});
    Router.go(valid ? h : 'status');
    $(window).on('hashchange', function() {
      var p = window.location.hash.replace('#','') || 'status';
      if (p !== S.currentPage) Router.go(p);
    });
  }
};

/* ============================================================
   POLLING
   ============================================================ */
var Poll = {
  _st: null, _pt: null, _rt: null,
  start: function() {
    this.stopAll();
    this._st = setInterval(function(){ Poll.fetchStatus(); }, CFG.pollMs);
    Poll.fetchStatus();
  },
  stopAll: function() {
    clearInterval(this._st); clearInterval(this._pt); clearInterval(this._rt);
    this._st = this._pt = this._rt = null;
  },
  setPage: function(page) {
    clearInterval(this._pt); clearInterval(this._rt);
    this._pt = this._rt = null;
    if (page === 'registers') {
      this._rt = setInterval(function(){ Poll.fetchRegs(); }, CFG.regPollMs);
      Poll.fetchRegs();
    } else {
      this._pt = setInterval(function(){ Poll.fetchPage(); }, CFG.pagePollMs);
      Poll.fetchPage();
    }
  },
  fetchStatus: function() {
    API.get('gui_status_json').done(function(d) {
      if (!d) return;
      S.baseStatus    = d.basestatus  || 'READY';
      S.switchState  = d.switchstate || 'Auto';
      S.engineState  = d.enginestate || '';
      S.kwOutput     = d.kwOutput    || '0 kW';
      if (d.RunHours != null) {
        S.runHours = parseFloat(d.RunHours) || 0;
        /* Live-fill journal hours field if it's still at default 0 */
        var $jh = $('#j-hours');
        if ($jh.length && S.runHours && (!$jh.val() || $jh.val() === '0')) {
          $jh.val(S.runHours);
        }
      }
      S.altDateFmt   = !!d.AltDateformat;
      S.updateAvailable = !!d.UpdateAvailable;
      if (d.Weather) S.weather = d.Weather;
      UI.statusBadge(S.baseStatus);
      $('#monitor-time').text(d.MonitorTime || '');
      UI.updatePill();
      /* --- Alert bar: system health + unsent feedback --- */
      if (d.SystemHealth && d.SystemHealth !== 'OK') {
        var hl = /thread|dead|log file/i.test(d.SystemHealth) ? 'error' : 'warn';
        AlertBar.set('health', hl, d.SystemHealth);
      } else { AlertBar.clear('health'); }
      if (d.UnsentFeedback && d.UnsentFeedback.toLowerCase() === 'true') {
        AlertBar.set('feedback', 'info', 'Unknown values detected. Enable Auto Feedback in Settings to help improve the software.');
      } else { AlertBar.clear('feedback'); }
      if (d.indicators) UI.indicators(d.indicators);
      else if (d.tiles || d.SystemHealth) {
        /* Fallback: derive indicators from tiles + SystemHealth when
           backend doesn't provide the indicators dict (e.g. upstream genmon) */
        var ind = {};
        if (d.tiles) {
          for (var ti = 0; ti < d.tiles.length; ti++) {
            var tt = d.tiles[ti], sub = (tt.subtype||'').toLowerCase();
            if (sub === 'wifi' && tt.value) {
              ind.wifi = Math.abs(parseFloat(tt.value)) || 0;
            } else if (sub === 'temperature' && /cpu/i.test(tt.title||'') && tt.value) {
              ind.cpuTemp = parseFloat(tt.value) || 0;
            }
          }
        }
        if (d.SystemHealth) ind.health = d.SystemHealth === 'OK' ? 'ok' : 'warn';
        UI.indicators(ind);
      }
      UI.weatherPill();
      if (S.currentPage === 'status') {
        if (d.tiles) Pages._updateGauges(d.tiles);
        Pages.status._updateInfoTiles(d);
        Pages.status._updateWeatherTile();
        /* Auto-show weather tile when data arrives for the first time */
        if (S.weather && S.weather.length && !Store.get('weatherSeen')) {
          Store.set('weatherSeen', true);
          if (!Store.isTileHidden('weather') && !$('[data-tile="weather"]').length) {
            var $wt = $(Pages.status._weatherTileHtml()).hide();
            $wt.appendTo($('#tile-grid'));
            $wt.fadeIn(200);
            Pages.status._updateWeatherTile();
          }
        }
      }
    });
  },
  fetchPage: function() {
    var p = S.currentPage;
    if (!p || !Pages[p] || !Pages[p].cmd) return;
    API.get(Pages[p].cmd).done(function(d) {
      if (d && S.currentPage === p && Pages[p].update) Pages[p].update(d);
    });
  },
  fetchRegs: function() {
    API.get('registers_json').done(function(d) {
      if (d && S.currentPage === 'registers') Pages.registers.update(d);
    });
  }
};

/* ============================================================
   ALERT BAR  — non-blocking system warnings
   ============================================================ */
var AlertBar = {
  _alerts: {},
  _LEVELS: {info:0, warn:1, error:2},
  _ICONS: {
    info:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    warn:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
  },
  set: function(src, level, msg) {
    this._alerts[src] = {level: level, msg: msg};
    this._render();
  },
  clear: function(src) {
    if (this._alerts[src]) { delete this._alerts[src]; this._render(); }
  },
  _render: function() {
    var $bar = $('#alert-bar');
    if (!$bar.length) return;
    var keys = Object.keys(this._alerts);
    if (!keys.length) {
      $bar.removeClass('active alert-bar-info alert-bar-warn alert-bar-error');
      return;
    }
    var self = this, top = 'info', msgs = [];
    keys.forEach(function(k) {
      var a = self._alerts[k];
      if (self._LEVELS[a.level] > self._LEVELS[top]) top = a.level;
      msgs.push(a.msg);
    });
    $bar.removeClass('alert-bar-info alert-bar-warn alert-bar-error')
        .addClass('active alert-bar-' + top)
        .html(this._ICONS[top] + '<span>' + msgs.join(' &mdash; ') + '</span>');
  }
};

/* ============================================================
   UI HELPERS
   ============================================================ */
var UI = {
  statusBadge: function(st) {
    $('#status-badge').attr('data-status', statusKey(st));
    $('#status-text').text(st);
  },
  connBadge: function() {
    var $f = $('#footer-connection');
    var $bar = $f.closest('.footer');
    if (S.connected) {
      $f.removeClass('error').html('&#x2713; Connected');
      $bar.removeClass('footer-disconnected');
      AlertBar.clear('conn');
    } else {
      $f.addClass('error').html('&#x2717; Disconnected');
      $bar.addClass('footer-disconnected');
      AlertBar.set('conn', 'error', 'Lost connection to server');
    }
  },

  /** Recursively render nested JSON as collapsible KV sections */
  renderJson: function(data, depth) {
    if (!data || typeof data !== 'object') return '<span>' + esc(String(data)) + '</span>';
    depth = depth || 0;
    var h = '';
    if (Array.isArray(data)) {
      for (var i = 0; i < data.length; i++) {
        var item = data[i];
        if (item && typeof item === 'object') {
          h += UI.renderJson(item, depth);
        } else {
          h += '<div class="kv-row"><span class="kv-val">' + esc(item!=null?item:'') + '</span></div>';
        }
      }
      return h;
    }
    for (var key in data) {
      if (!data.hasOwnProperty(key)) continue;
      var v = data[key];
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        h += '<div class="status-section">' +
          '<div class="status-section-title open">' + esc(key) + '</div>' +
          '<div class="status-kv">' +
          UI.renderJson(v, depth+1) + '</div></div>';
      } else if (Array.isArray(v)) {
        h += '<div class="status-section">' +
          '<div class="status-section-title open">' + esc(key) + '</div>' +
          '<div class="status-kv">' +
          UI.renderJson(v, depth+1) + '</div></div>';
      } else {
        h += '<div class="kv-row"><span class="kv-key">' + esc(key) +
          '</span><span class="kv-val">' + esc(v!=null?v:'') + '</span></div>';
      }
    }
    return h;
  },

  /** Build a form field from settings definition array
   *  def = [type, label, sort, currentValue, tooltip, options/regex] */
  /* "disable" keys that should display as positive "Enable" toggles.
     Checked = feature enabled; the saved config value is inverted. */
  _INVERT_KEYS: {
    disableweather: 'Enable Weather',
    disablesmtp: 'Enable Outbound Email (SMTP)',
    disableimap: 'Enable Inbound Email Commands (IMAP)',
    disableoutagecheck: 'Enable Outage Checking',
    disablepowerlog: 'Enable Power Log'
  },

  formField: function(name, def, value) {
    var type = def[0], label = def[1], tip = def[4]||'';
    var invert = UI._INVERT_KEYS[name];
    if (type === 'boolean') {
      var checked = (value===true||value==='true'||value===1);
      if (invert) { checked = !checked; label = invert; }
      return '<div class="form-group setting-field" data-label="'+esc(label).toLowerCase()+'">' +
        '<div class="setting-toggle-row">' +
        '<label class="toggle"><input type="checkbox" id="f_'+esc(name)+'" name="'+esc(name)+'"' +
        (invert ? ' data-invert="1"' : '') +
        (checked ? ' checked' : '') + '><span class="toggle-slider"></span></label>' +
        '<label class="setting-toggle-label" for="f_'+esc(name)+'">' + esc(label) + '</label></div>' +
        (tip ? '<div class="form-hint">' + esc(tip) + '</div>' : '') + '</div>';
    }
    var h = '<div class="form-group setting-field" data-label="'+esc(label).toLowerCase()+'">' +
      '<label class="form-label" for="f_'+esc(name)+'">' + esc(label) + '</label>';
    if (type === 'list' && def[5]) {
      var opts = String(def[5]).split(',');
      h += '<select class="form-select" id="f_'+esc(name)+'" name="'+esc(name)+'">';
      opts.forEach(function(o){ o=o.trim();
        h += '<option value="'+esc(o)+'"'+(String(value)===o?' selected':'')+'>'+esc(o)+'</option>';
      });
      h += '</select>';
    } else if (type === 'password') {
      var pwBounds = def[5] ? ' data-bounds="'+esc(def[5])+'"' : '';
      h += '<div class="pw-wrap"><input class="form-input" type="password" id="f_'+esc(name)+'" name="'+esc(name)+'" value="'+esc(value)+'"'+pwBounds+'>' +
        '<button type="button" class="pw-toggle" tabindex="-1" title="Show/hide">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button></div>';
    } else if (type === 'readonly') {
      h += '<div class="ro-wrap" style="display:flex;align-items:center;gap:6px">' +
        '<input class="form-input" type="text" id="f_'+esc(name)+'" value="'+esc(value)+'" readonly ' +
        'style="background:#e9ecef;border-color:#ced4da;opacity:.85;cursor:default;user-select:all;color:#495057;flex:1">' +
        '<button type="button" class="btn btn-sm" style="white-space:nowrap;padding:2px 8px;font-size:12px" ' +
        'onclick="var i=this.previousElementSibling;i.select();document.execCommand(\'copy\');this.textContent=\'Copied!\';var b=this;setTimeout(function(){b.textContent=\'Copy\';},1500)" ' +
        'title="Copy to clipboard">Copy</button></div>';
    } else if (type === 'int') {
      var intBounds = def[5] ? ' data-bounds="'+esc(def[5])+'"' : '';
      h += '<input class="form-input" type="number" id="f_'+esc(name)+'" name="'+esc(name)+'" value="'+esc(value)+'"'+intBounds+'>';
    } else {
      var txtBounds = def[5] ? ' data-bounds="'+esc(def[5])+'"' : '';
      h += '<input class="form-input" type="text" id="f_'+esc(name)+'" name="'+esc(name)+'" value="'+esc(value)+'"'+txtBounds+'>';
    }
    if (tip) h += '<div class="form-hint">' + esc(tip) + '</div>';
    h += '</div>';
    return h;
  },

  /* ---- Bounds validation (non-blocking, advisory only) ---- */
  _VALIDATORS: {
    required:  function(v)      { return v.trim().length > 0 ? '' : 'Required'; },
    digits:    function(v)      { return v===''||/^\d+$/.test(v) ? '' : 'Must be digits only'; },
    number:    function(v)      { return v===''||!isNaN(Number(v)) ? '' : 'Must be a number'; },
    range:     function(v,a,b)  { var n=Number(v); return v===''||(!isNaN(n)&&n>=a&&n<=b) ? '' : 'Must be between '+a+' and '+b; },
    min:       function(v,n)    { return v===''||v.length>=n ? '' : 'At least '+n+' characters'; },
    max:       function(v,n)    { return v===''||v.length<=n ? '' : 'At most '+n+' characters'; },
    minmax:    function(v,a,b)  { return v===''||(v.length>=a&&v.length<=b) ? '' : 'Must be '+a+'\u2013'+b+' characters'; },
    email:     function(v)      { return v===''||/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? '' : 'Invalid email address'; },
    IPAddress: function(v)      { return v===''||/^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$/.test(v) ? '' : 'Invalid IP address'; },
    InternetAddress: function(v){ return v===''||/^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})?$/.test(v)||UI._VALIDATORS.IPAddress(v)==='' ? '' : 'Invalid address'; },
    HTTPAddress:     function(v){ return v===''||/^https?:\/\/.+/.test(v) ? '' : 'Must be an http(s) URL'; },
    UnixFile:   function(v)     { return v===''||/^\/[^\0]+$/.test(v) ? '' : 'Must be a Unix file path'; },
    UnixDir:    function(v)     { return v===''||/^\/[^\0]+\/$/.test(v) ? '' : 'Must be a Unix directory path'; },
    UnixDevice: function(v)     { return v===''||/^\/dev\/[^\0]+$/.test(v) ? '' : 'Must be a /dev/ device path'; },
    InternationalPhone: function(v){ return v===''||/^\+?[\d\s\-().]{7,20}$/.test(v) ? '' : 'Invalid phone number'; },
    username:  function(v)      { return v===''||/^[a-zA-Z0-9_\-@.]{3,50}$/.test(v) ? '' : 'Invalid username'; }
  },
  /** Parse a bounds string like "required digits range:0:27" into callable checks */
  parseBounds: function(boundsStr) {
    if (!boundsStr) return null;
    var rules = [], parts = boundsStr.split(/\s+/);
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i], segs = p.split(':'), name = segs[0];
      if (UI._VALIDATORS[name]) {
        var args = segs.slice(1).map(Number);
        rules.push({ name: name, args: args });
      }
    }
    return rules.length ? rules : null;
  },
  /** Validate a value against parsed rules. Returns first error message or '' */
  validateBounds: function(value, rules) {
    if (!rules) return '';
    for (var i = 0; i < rules.length; i++) {
      var r = rules[i], fn = UI._VALIDATORS[r.name];
      if (fn) {
        var msg = fn.apply(null, [value].concat(r.args));
        if (msg) return msg;
      }
    }
    return '';
  },
  /** Live-validate an input with [data-bounds]. Adds/removes .field-invalid + hint. */
  _checkField: function(el) {
    var $el = $(el), bounds = $el.attr('data-bounds');
    if (!bounds) return;
    var rules = UI.parseBounds(bounds);
    var msg = UI.validateBounds($el.val(), rules);
    var $grp = $el.closest('.form-group, .adn-param-row');
    $grp.find('.field-error-hint').remove();
    if (msg) {
      $el.addClass('field-invalid');
      $el.after('<div class="field-error-hint">' + esc(msg) + '</div>');
    } else {
      $el.removeClass('field-invalid');
    }
  },
  /** Bind live validation on all [data-bounds] inputs inside a container */
  bindBoundsValidation: function($container) {
    $container.off('input.bounds change.bounds').on('input.bounds change.bounds', '[data-bounds]', function() {
      UI._checkField(this);
    });
  },

  /** Collect form values from a container into key=val&key=val string (raw, not encoded) */
  collectForm: function(sel) {
    var parts = [];
    $(sel).find('[name]').each(function() {
      var $e = $(this), n = $e.attr('name');
      var v = $e.is(':checkbox') ? ($e.is(':checked')?'true':'false') : $e.val();
      /* Invert "disable" keys back: UI shows Enable (checked=on) but config key is disable */
      if ($e.is(':checkbox') && $e.attr('data-invert') === '1') {
        v = (v === 'true') ? 'false' : 'true';
      }
      parts.push(n + '=' + v);
    });
    return parts.join('&');
  },

  /** Bind section-title click toggle globally inside $container */
  bindSectionToggles: function($c) {
    $c.off('click.sect', '.status-section-title').on('click.sect', '.status-section-title', function() {
      $(this).toggleClass('open').next('.status-kv').slideToggle(200);
    });
  },

  /** Save which sections are open inside $container */
  saveOpenSections: function($c) {
    var open = {};
    $c.find('.status-section-title').each(function() {
      open[$(this).text().trim()] = $(this).hasClass('open');
    });
    return open;
  },

  /** Restore open/closed state after re-render */
  restoreOpenSections: function($c, map) {
    if (!map) return;
    $c.find('.status-section-title').each(function() {
      var key = $(this).text().trim();
      if (key in map) {
        $(this).toggleClass('open', map[key]);
        $(this).next('.status-kv').toggle(map[key]);
      }
    });
  },

  /** Re-render a JSON panel preserving open/closed section state */
  refreshJsonPanel: function($p, data) {
    var saved = UI.saveOpenSections($p);
    $p.html(UI.renderJson(data));
    UI.restoreOpenSections($p, saved);
    UI.bindSectionToggles($p);
  },

  /* ---- Header status-bar indicators (Android-style) ---- */
  indicators: function(ind) {
    var parts = [];

    /* WiFi signal strength (dBm, positive number means -N dBm) */
    if (ind.wifi) {
      var dbm = ind.wifi;  /* e.g. 42 means -42 dBm */
      var wPct = Math.round(Math.max(0, Math.min(100, (-dbm + 90) / 60 * 100)));
      var bars = dbm <= 30 ? 4 : dbm <= 50 ? 3 : dbm <= 65 ? 2 : 1;
      var wc = bars >= 3 ? 'ind-ok' : bars === 2 ? 'ind-warn' : 'ind-bad';
      parts.push(
        '<div class="hdr-ind '+wc+'" title="WiFi: -'+dbm+' dBm ('+wPct+'%)">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
        /* Fan-shaped wifi arcs — dim the ones above the signal level */
        '<path d="M1.42 9a16.02 16.02 0 0121.16 0"' + (bars < 4 ? ' class="ind-dim"' : '') + '/>' +
        '<path d="M5 12.55a11 11 0 0114 0"' + (bars < 3 ? ' class="ind-dim"' : '') + '/>' +
        '<path d="M8.53 16.11a6 6 0 016.95 0"' + (bars < 2 ? ' class="ind-dim"' : '') + '/>' +
        '<circle cx="12" cy="20" r="1" fill="currentColor" stroke="none"/>' +
        '</svg><span class="ind-val">'+wPct+'%</span></div>');
    }

    /* CPU temperature */
    if (ind.cpuTemp) {
      var t = ind.cpuTemp;
      /* Derive thresholds from the CPU tile's colorzones if available */
      var warnAt = 80, badAt = 85;
      if (S.tileConfig) {
        for (var ci = 0; ci < S.tileConfig.length; ci++) {
          var ct = S.tileConfig[ci];
          if (ct && (ct.subtype||'').toLowerCase() === 'temperature' &&
              /cpu/i.test(ct.title||'') && ct.colorzones && ct.colorzones.length >= 2) {
            /* zones: [GREEN 0-nominal, YELLOW nominal-mid, RED mid-max] */
            warnAt = ct.colorzones[0].max;
            badAt = ct.colorzones[1].max;
            break;
          }
        }
      }
      var tc = t < warnAt ? 'ind-ok' : t < badAt ? 'ind-warn' : 'ind-bad';
      parts.push(
        '<div class="hdr-ind '+tc+'" title="CPU: '+t+'\u00B0C">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M14 14.76V3.5a2.5 2.5 0 00-5 0v11.26a4.5 4.5 0 105 0z"/>' +
        '<circle cx="11.5" cy="17.5" r="2" fill="currentColor" stroke="none" opacity=".5"/>' +
        '</svg><span class="ind-val">'+t+'\u00B0</span></div>');
    }

    /* Packets per second */
    if (ind.pps != null) {
      var pps = ind.pps;
      var crc = ind.crcPct || 0;
      var pc = (pps > 0 && crc < 0.01) ? 'ind-ok' : (pps > 0 && crc < 0.05) ? 'ind-warn' : pps === 0 ? 'ind-warn' : 'ind-bad';
      parts.push(
        '<div class="hdr-ind '+pc+'" title="Comm: '+pps+' pkt/s, CRC err: '+(crc*100).toFixed(1)+'%">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>' +
        '</svg><span class="ind-val">'+pps+'</span></div>');
    }

    /* System health */
    if (ind.health) {
      var hc = ind.health === 'ok' ? 'ind-ok' : 'ind-bad';
      parts.push(
        '<div class="hdr-ind '+hc+' hdr-ind-health" title="System: '+ind.health+'" style="cursor:pointer">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
        (ind.health === 'ok'
          ? '<path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'
          : '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>') +
        '</svg></div>');
    }

    $('#indicators').html(parts.join(''));
    $('#indicators').off('click.health').on('click.health', '.hdr-ind-health', function(){ Router.go('monitor'); });
  },

  /* ---- Software Update pill in header ---- */
  updatePill: function() {
    var $pill = $('#update-pill');
    if (!S.updateAvailable) {
      if ($pill.length) $pill.remove();
      return;
    }
    if ($pill.length) return; /* already shown */
    var html = '<button class="hdr-update-pill" id="update-pill" title="A software update is available">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
      '<span class="update-pill-text">Update Available</span></button>';
    var $badge = $('#status-badge');
    if ($badge.length) $badge.before(html);
    else $('#indicators').after(html);
    $('#update-pill').on('click', function() { Router.go('about'); });
  },

  /* ---- Weather pill in header ---- */
  weatherPill: function() {
    var $pill = $('#weather-pill');
    var w = S.weather;
    if (!w || !w.length) {
      if ($pill.length) $pill.remove();
      return;
    }
    /* Parse weather array into flat map */
    var m = {};
    for (var i = 0; i < w.length; i++) {
      var obj = w[i];
      for (var k in obj) { if (obj.hasOwnProperty(k)) m[k] = obj[k]; }
    }
    var temp = m['Current Temperature'] || '';
    var cond = m['Conditions'] || '';
    if (!temp) { if ($pill.length) $pill.remove(); return; }
    var ico = Pages.status._weatherConditionIcon(cond);
    var html = '<div class="hdr-ind hdr-weather-pill" id="weather-pill" title="' + esc(cond || 'Weather') + '">' +
      '<span class="weather-pill-icon">' + ico + '</span>' +
      '<span class="weather-pill-temp">' + esc(temp) + '</span></div>';
    if ($pill.length) {
      $pill.replaceWith(html);
    } else {
      /* Insert before the status badge */
      var $badge = $('#status-badge');
      if ($badge.length) $badge.before(html);
      else $('#indicators').append(html);
    }
  }
};

/* ============================================================
   W E L C O M E   T O U R
   ============================================================ */
var Tour = {
  _step: 0,
  _steps: [
    { title: 'Welcome to Genmon!',
      body: 'This dashboard gives you a live overview of your generator. ' +
            'Let\u2019s take a quick look at how to make it yours.',
      target: null },
    { title: 'Customize your dashboard',
      body: 'Click the <b>Edit</b> button (pencil icon) in the header to enter edit mode. ' +
            'Once in edit mode you can:<ul style="margin:.5em 0 0 1.2em;padding:0;font-size:.9em">' +
            '<li><b>Drag &amp; drop</b> tiles to reorder them</li>' +
            '<li><b>Resize</b> tiles (small / medium / large)</li>' +
            '<li><b>Change the look</b> &ndash; pick a different gauge style per tile</li>' +
            '<li><b>Hide</b> any tile you don&rsquo;t need (&times; button)</li></ul>',
      target: '#customize-btn' },
    { title: 'Detailed Status',
      body: 'Below the tiles you\u2019ll find a collapsible <b>Detailed Status</b> panel with all generator data. ' +
            'Click its header to expand it.',
      target: '#status-panel-hdr' },
    { title: 'Detail View mode',
      body: 'Prefer raw data over gauges? Open the <b>Edit Dashboard</b> panel (pencil icon) and toggle ' +
            '<b>Disable graphical Dashboard</b> to auto-expand the status panel and hide the tile grid. ' +
            'This preference is saved.',
      target: '#customize-btn' }
  ],

  start: function() {
    this._step = 0;
    this._render();
  },

  _render: function() {
    var s = this._steps[this._step];
    /* Remove previous */
    $('.tour-overlay, .tour-spotlight, .tour-tooltip').remove();

    /* Backdrop */
    var $ov = $('<div class="tour-overlay"></div>');
    $('body').append($ov);

    /* Spotlight + tooltip */
    var pos = null;
    if (s.target) {
      var $t = $(s.target);
      if ($t.length && $t.is(':visible')) {
        var r = $t[0].getBoundingClientRect();
        pos = { top: r.top, left: r.left, width: r.width, height: r.height };
        var $sp = $('<div class="tour-spotlight"></div>').css({
          top: pos.top - 6, left: pos.left - 6,
          width: pos.width + 12, height: pos.height + 12
        });
        $('body').append($sp);
      }
    }

    /* Tooltip */
    var isLast = this._step >= this._steps.length - 1;
    var $tt = $('<div class="tour-tooltip">' +
      '<div class="tour-title">' + esc(s.title) + '</div>' +
      '<div class="tour-body">' + s.body + '</div>' +
      '<div class="tour-footer">' +
        '<span class="tour-counter">' + (this._step+1) + ' / ' + this._steps.length + '</span>' +
        '<div class="tour-btns">' +
          '<button class="btn btn-sm btn-outline tour-skip">Skip</button>' +
          '<button class="btn btn-sm btn-primary tour-next">' + (isLast ? 'Done' : 'Next') + '</button>' +
        '</div>' +
      '</div></div>');

    $('body').append($tt);

    /* Position tooltip near target  */
    if (pos) {
      var ttW = $tt.outerWidth(), ttH = $tt.outerHeight();
      var wW = $(window).width(), wH = $(window).height();
      var tTop = pos.top + pos.height + 14;
      var above = false;
      if (tTop + ttH > wH - 10) { tTop = pos.top - ttH - 14; above = true; }
      /* Clamp so tooltip never goes off-screen */
      if (tTop + ttH > wH - 10) tTop = wH - ttH - 10;
      if (tTop < 10) tTop = 10;
      var tLeft = pos.left + pos.width / 2 - ttW / 2;
      if (tLeft < 10) tLeft = 10;
      if (tLeft + ttW > wW - 10) tLeft = wW - ttW - 10;
      $tt.css({ top: tTop, left: tLeft });
      /* Arrow pointing at target */
      var arrowLeft = pos.left + pos.width / 2 - tLeft;
      arrowLeft = Math.max(16, Math.min(arrowLeft, ttW - 16));
      var $arrow = $('<div class="tour-arrow"></div>').css('left', arrowLeft + 'px');
      if (above) $arrow.addClass('tour-arrow-down');
      $tt.prepend($arrow);
    } else {
      $tt.css({ top: '50%', left: '50%', transform: 'translate(-50%,-50%)' });
    }

    /* Button handlers */
    var self = this;
    $tt.find('.tour-skip').on('click', function() { self._finish(); });
    $tt.find('.tour-next').on('click', function() {
      if (isLast) { self._finish(); }
      else { self._step++; self._render(); }
    });
    $ov.on('click', function() { self._finish(); });
  },

  _finish: function() {
    $('.tour-overlay, .tour-spotlight, .tour-tooltip').remove();
    Store.set('tourSeen', true);
  }
};

/* ============================================================
   P A G E S
   ============================================================ */
var Pages = {
  render: function(page) {
    var $c = $('#content');
    if (Pages[page] && Pages[page].render) {
      Pages[page].render($c);
      $c.scrollTop(0);
    } else {
      $c.html('<div class="text-muted text-center mt-2">Page not found.</div>');
    }
  },

  /** Update gauge values from gui_status_json tiles array */
  _updateGauges: function(tiles) {
    S._lastGaugeTiles = tiles;
    var self = Pages.status;
    var km = S.keyMap;
    if (!km) return;
    for (var i = 0; i < tiles.length; i++) {
      /* Convert gauge index i to its string key */
      var iLen = S.infoTileCount != null ? S.infoTileCount : self.INFO_TILES.length;
      var key = km.numToKey[iLen + i];
      if (!key) continue;
      var sub = (tiles[i].subtype||'').toLowerCase();
      var fixed = self._FIXED_GAUGES[sub];

      if (fixed === 'thermo') {
        self._updateThermo(key, tiles[i]);
        continue;
      }
      if (fixed === 'wifibar') {
        self._updateWifi(key, tiles[i]);
        continue;
      }

      var g = S.gauges[i];
      if (g) {
        g.set(tiles[i].value);
        var lbl = tiles[i].text ||
          (roundNum(tiles[i].value) + (S.tileConfig[i] ? ' ' + (S.tileConfig[i].units||'') : ''));
        g.setLabel(lbl);
      }
      var $tv = $('#tile-val-'+key);
      if ($tv.length) {
        var tu = S.tileConfig[i] ? S.tileConfig[i].units : '';
        $tv.html(formatVal(tiles[i].value, tu));
      }
    }
  },

  /* ========== STATUS / DASHBOARD ========== */
  status: {
    cmd: 'status_json',
    _dragSrc: null,
    /* Virtual info tiles prepended before gauge tiles */
    /* Gauge type choices: 'radial' (default dial), 'arc' (half-donut), 'hbar' (horizontal bar), 'fuel' (tank) */
    /* 'thermo' (thermometer) and 'wifibar' (signal bars) are fixed types that cannot be changed */
    GAUGE_TYPES: ['radial','arc','hbar'],
    GAUGE_TYPE_LABELS: {radial:'\u25D4', arc:'\u25E0', hbar:'\u2501'},
    /* Fixed (non-user-changeable) gauge types keyed by tile subtype */
    _FIXED_GAUGES: { cpu:'thermo', temperature:'thermo', wifi:'wifibar', wifipercent:'wifibar' },
    /* Default gauge type per tile title keyword */
    _defaultGaugeType: function(title, subtype) {
      var fixed = Pages.status._FIXED_GAUGES[subtype];
      if (fixed) return fixed;
      var t = (title||'').toLowerCase();
      if (/fuel/i.test(t)) return 'fuel';
      if (/current/i.test(t)) return 'hbar';
      if (/power/i.test(t) && !/graph/i.test(t)) return 'arc';
      if (/battery/i.test(t)) return 'radial';
      if (/rpm/i.test(t)) return 'radial';
      if (/frequency|freq/i.test(t)) return 'arc';
      if (/voltage|volt/i.test(t)) return 'hbar';
      return 'radial';
    },
    INFO_TILES: [
      {id:'info-switch',  title:'Switch State',  field:'switchstate', icon:'maintenance',
       subs: [{label:'Base Status', field:'basestatus'},
              {label:'Engine', field:'enginestate'}, {label:'Health', field:'SystemHealth'}]},
      {id:'info-engine',  title:'Engine State',  field:'enginestate', icon:'status',
       subs: [{label:'RPM', field:'RPM'}, {label:'Frequency', field:'Frequency'},
              {label:'Battery', field:'BatteryVoltage'}, {label:'Run Hours', field:'RunHours'}]},
      {id:'info-power',   title:'Power Output',  field:'kwOutput',    icon:'monitor', needsPower:true,
       subs: [{label:'Output', field:'OutputVoltage'},
              {label:'Frequency', field:'Frequency'}, {label:'RPM', field:'RPM'}]},
      {id:'info-line',    title:'Line Status',   field:'UtilityVoltage', icon:'power', needsOutage:true,
       subs: [{label:'Max', field:'UtilityMaxVoltage'}, {label:'Min', field:'UtilityMinVoltage'},
              {label:'Threshold', field:'UtilityThresholdVoltage'}]},
      {id:'info-logs',    title:'Recent Logs',   field:'_logs', icon:'logs', isLogs:true}
    ],
    TILE_SIZES: ['sm','md','lg'],
    FONT_SIZES: ['sm','md','lg'],
    render: function($c) {
      var info = S.startInfo, tiles = info.tiles || [];
      var pg = info.pages || {};
      var infoTiles = Pages.status.INFO_TILES.filter(function(t) {
        if (t.isLogs && pg.logs === false) return false;
        if (t.needsOutage && pg.outage === false) return false;
        if (t.needsPower && !info.PowerGraph) return false;
        return true;
      });
      S.tileConfig = tiles;
      S.gauges = [];
      S.editMode = false;
      S.infoTileCount = infoTiles.length;
      /* Extract chart title from the first powergraph tile */
      S.chartTitle = null;
      for (var ct = 0; ct < tiles.length; ct++) {
        if ((tiles[ct].type||'').toLowerCase() === 'graph') { S.chartTitle = tiles[ct].title; break; }
      }

      /* Special (non-gauge) tiles that participate in ordering */
      var specialKeys = [];
      if (info.PowerGraph && window.Chart) specialKeys.push('chart');
      specialKeys.push('clock');
      specialKeys.push('weather');
      S.specialKeys = specialKeys;

      /* Build string-key map for all tiles */
      var km = Store.buildKeyMap(infoTiles, tiles, specialKeys);
      S.keyMap = km;  /* { allKeys, numToKey, keyToGauge } */

      var order = Store.getTileOrder(km.allKeys, km.numToKey);
      var detailView = !!Store.get('detailView');
      var alwaysDetail = !!Store.get('alwaysDetail');
      var h = '<div class="dash-header">' +
        '<div class="page-title">' + icon('status') + ' Dashboard</div>' +
        '</div>';

      var self = Pages.status;

      /* --- Tile grid --- */
      h += '<div id="tile-grid" class="tile-grid">';
      for (var oi = 0; oi < order.length; oi++) {
        var key = order[oi];
        if (Store.isTileHidden(key)) continue;
        if (key === 'chart') {
          h += self._chartTileHtml();
        } else if (key === 'clock') {
          h += self._clockTileHtml();
        } else if (key === 'weather') {
          /* Auto-hide weather tile when no weather data has ever been received */
          if (!S.weather && !Store.get('weatherSeen')) continue;
          h += self._weatherTileHtml();
        } else if (km.keyToGauge[key] !== undefined) {
          var gi = km.keyToGauge[key];
          var t = tiles[gi];
          if (!t) continue;
          h += self._tileHtml(key, gi, t);
        } else {
          /* Info tile — find by id */
          var infoIdx = -1;
          for (var ii = 0; ii < infoTiles.length; ii++) { if (infoTiles[ii].id === key) { infoIdx = ii; break; } }
          if (infoIdx >= 0) h += self._infoTileHtml(key, infoTiles[infoIdx]);
        }
      }

      h += '</div>'; // tile-grid

      /* --- Hidden tile drawer (shown in edit mode) --- */
      h += '<div id="tile-drawer" class="tile-drawer" style="display:none">' +
        '<div class="view-mode-label edit-detail-toggle" id="view-mode-toggle" title="Switch to a text-only status view">' +
        '<label class="toggle"><input type="checkbox" id="detail-view-cb"' + (detailView ? ' checked' : '') + '>' +
        '<span class="toggle-slider"></span></label>' +
        '<span>Disable graphical Dashboard</span></div>' +
        '<div class="view-mode-label edit-detail-toggle" id="always-detail-toggle" title="Keep the Detailed Status section always visible">' +
        '<label class="toggle"><input type="checkbox" id="always-detail-cb"' + (alwaysDetail ? ' checked' : '') + '>' +
        '<span class="toggle-slider"></span></label>' +
        '<span>Always Show Detailed Status</span></div>' +
        '<div class="tile-drawer-header">' + icon('status') +
        ' <span>Hidden Tiles</span>' +
        '<button class="btn btn-sm btn-outline" id="dash-reset">'+btnIcon('refresh')+' Reset Layout</button></div>' +
        '<div id="tile-drawer-list" class="tile-drawer-list"></div></div>';

      /* --- Status text (collapsible, auto-expanded in detail view) --- */
      h += '<div class="card status-panel-card mt-2">' +
        '<div class="card-header status-panel-toggle" id="status-panel-hdr" style="cursor:pointer;user-select:none">' +
        icon('logs') + ' <span>Detailed Status</span>' +
        '<svg class="status-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-left:auto;transition:transform .2s"><polyline points="6 9 12 15 18 9"/></svg>' +
        '</div>' +
        '<div id="status-panel" class="status-panel" style="display:' + (detailView || alwaysDetail ? 'block' : 'none') + '">' +
        '<div class="text-muted text-center">Loading status\u2026</div></div></div>';

      $c.html(h);

      /* Init gauges */
      for (var goi = 0; goi < order.length; goi++) {
        var gKey = order[goi];
        if (Store.isTileHidden(gKey)) continue;
        var gi2 = km.keyToGauge[gKey];
        if (gi2 !== undefined) {
          self._initGauge(gKey, gi2, tiles[gi2]);
        }
      }

      /* Init power chart */
      if (info.PowerGraph && window.Chart && !Store.isTileHidden('chart')) {
        self._initChart();
        self._fetchChartData();
      }

      /* Init clock */
      if (!Store.isTileHidden('clock')) self._initClock();

      /* Init weather tile data */
      if (S.weather) {
        Store.set('weatherSeen', true);
        if (!Store.isTileHidden('weather')) self._updateWeatherTile();
      }

      /* Fetch outage data for Line Status tile (one-shot) */
      if (pg.outage !== false) self._fetchOutageSubs();

      /* --- Event bindings --- */

      /* Apply detail view mode */
      if (detailView) {
        $('#tile-grid').hide();
        $('#status-panel-hdr').find('.status-chevron').css('transform', 'rotate(180deg)');
      } else if (alwaysDetail) {
        $('#status-panel-hdr').find('.status-chevron').css('transform', 'rotate(180deg)');
      }

      /* Detail view toggle */
      $('#detail-view-cb').on('change', function() {
        var on = $(this).is(':checked');
        Store.set('detailView', on);
        if (on) {
          $('#tile-grid').slideUp(250);
          $('#status-panel').slideDown(250);
          $('#status-panel-hdr').find('.status-chevron').css('transform', 'rotate(180deg)');
          /* Auto-enable Always Show Detailed Status */
          if (!$('#always-detail-cb').is(':checked')) {
            $('#always-detail-cb').prop('checked', true).trigger('change');
          }
        } else {
          $('#tile-grid').slideDown(250);
          if (!$('#always-detail-cb').is(':checked')) {
            $('#status-panel').slideUp(200);
            $('#status-panel-hdr').find('.status-chevron').css('transform', '');
          }
        }
      });

      /* Always show detailed status toggle */
      $('#always-detail-cb').on('change', function() {
        var on = $(this).is(':checked');
        Store.set('alwaysDetail', on);
        if (on) {
          $('#status-panel').slideDown(250);
          $('#status-panel-hdr').find('.status-chevron').css('transform', 'rotate(180deg)');
        } else if (!$('#detail-view-cb').is(':checked')) {
          $('#status-panel').slideUp(200);
          $('#status-panel-hdr').find('.status-chevron').css('transform', '');
        }
      });

      /* Status panel toggle */
      $('#status-panel-hdr').on('click', function() {
        var $body = $('#status-panel');
        var open = $body.is(':visible');
        $body.slideToggle(200);
        $(this).find('.status-chevron').css('transform', open ? '' : 'rotate(180deg)');
      });

      /* Clock mode toggle */
      $c.on('click', '.clock-mode-btn', function() {
        var mode = $(this).data('cmode');
        Store.set('clockMode', mode);
        $(this).siblings('.clock-mode-btn').removeClass('active');
        $(this).addClass('active');
        $('#clock-face').empty();
        self._renderClock();
      });

      /* Edit/customize toggle */
      $('#customize-btn').off('click').on('click', function() {
        S.editMode = !S.editMode;
        $(this).toggleClass('edit-active', S.editMode);
        var $g = $('#tile-grid');
        $g.toggleClass('editing', S.editMode);
        $g.find('.tile').attr('draggable', S.editMode ? 'true' : 'false');
        $g.find('.tile-edit-controls').toggle(S.editMode);
        if (S.editMode) {
          self._buildDrawer();
          $('#tile-drawer').slideDown(200);
        } else {
          $('#tile-drawer').slideUp(200);
        }
      });

      /* Hide tile (X button) */
      $c.on('click', '.tile-hide-btn', function(e) {
        e.stopPropagation();
        var key = $(this).closest('.tile').data('tile');
        if (key === undefined || key === null) return;
        Store.setTileHidden(key, true);
        $(this).closest('.tile').fadeOut(200, function() {
          $(this).remove();
          self._buildDrawer();
        });
      });

      /* Tile size controls */
      $c.on('click', '.tile-size-btn', function(e) {
        e.stopPropagation();
        var $tile = $(this).closest('.tile');
        var key = $tile.data('tile');
        var dir = $(this).data('dir');
        var gtype = $tile.attr('data-gtype');
        /* Arc gauge: cap at lg (2 columns) */
        var maxSize = (gtype === 'arc') ? 'lg' : null;
        var sizes = Pages.status.TILE_SIZES;
        var cur = $tile.data('size') || 'md';
        var ci = sizes.indexOf(cur);
        var maxIdx = maxSize ? sizes.indexOf(maxSize) : sizes.length - 1;
        var ni = dir === 'up' ? Math.min(ci+1, maxIdx) : Math.max(ci-1, 0);
        var ns = sizes[ni];
        $tile.data('size', ns)
          .removeClass('tile-sm tile-md tile-lg')
          .addClass('tile-' + ns);
        Store.setTileSize(key, ns === 'md' ? null : ns);
        /* Re-init gauge to pick up new size */
        var gi3 = km.keyToGauge[key];
        if (gi3 !== undefined && tiles[gi3]) {
          self._initGauge(key, gi3, tiles[gi3]);
          API.get('gui_status_json').done(function(d) {
            if (d && d.tiles) Pages._updateGauges(d.tiles);
          });
        }
      });

      /* Font size controls (info / text tiles) */
      $c.on('click', '.tile-font-btn', function(e) {
        e.stopPropagation();
        var $tile = $(this).closest('.tile');
        var key = $tile.data('tile');
        var dir = $(this).data('dir');
        var sizes = Pages.status.FONT_SIZES;
        var cur = $tile.data('fontsize') || 'md';
        var ci = sizes.indexOf(cur);
        var ni = dir === 'up' ? Math.min(ci+1, sizes.length-1) : Math.max(ci-1, 0);
        var ns = sizes[ni];
        $tile.data('fontsize', ns)
          .removeClass('tile-font-sm tile-font-md tile-font-lg')
          .addClass('tile-font-' + ns);
        Store.setTileFontSize(key, ns === 'md' ? null : ns);
      });

      /* Change gauge type */
      $c.on('click', '.gauge-pick-btn', function() {
        var $btn = $(this), $tile = $btn.closest('.tile');
        var key = $tile.data('tile');
        var gtype = $btn.data('gtype');
        if (!key || !gtype) return;
        $btn.siblings('.gauge-pick-btn').removeClass('active');
        $btn.addClass('active');
        Store.setGaugeType(key, gtype);
        $tile.attr('data-gtype', gtype);
        /* Enforce size constraints per gauge type */
        if (gtype === 'radial') {
          $tile.removeClass('tile-sm tile-lg').addClass('tile-md').data('size', 'md');
          Store.setTileSize(key, null);
        }
        var gi4 = km.keyToGauge[key];
        if (gi4 !== undefined && tiles[gi4]) {
          self._initGauge(key, gi4, tiles[gi4]);
          /* Rebuild edit controls to reflect new gauge-type constraints */
          $tile.find('.tile-edit-controls').replaceWith(self._editControlsHtml(false, key));
          if (S.editMode) $tile.find('.tile-edit-controls').show();
          /* Refresh the value immediately */
          API.get('gui_status_json').done(function(d) {
            if (d && d.tiles) Pages._updateGauges(d.tiles);
          });
        }
      });

      /* Re-add tile from drawer */
      $c.on('click', '.drawer-tile', function() {
        var key = $(this).data('tile');
        if (key === undefined || key === null) return;
        Store.setTileHidden(key, false);
        /* Mark weather as seen so it persists after re-add */
        if (key === 'weather') Store.set('weatherSeen', true);
        var $new;
        if (key === 'chart') $new = $(self._chartTileHtml());
        else if (key === 'clock') $new = $(self._clockTileHtml());
        else if (key === 'weather') $new = $(self._weatherTileHtml());
        else if (km.keyToGauge[key] !== undefined) {
          var rgi = km.keyToGauge[key];
          $new = $(self._tileHtml(key, rgi, tiles[rgi]));
        } else {
          /* Info tile */
          var rii = -1;
          for (var ri = 0; ri < infoTiles.length; ri++) { if (infoTiles[ri].id === key) { rii = ri; break; } }
          if (rii >= 0) $new = $(self._infoTileHtml(key, infoTiles[rii]));
        }
        if (!$new || !$new.length) return;
        $new.attr('draggable', 'true').hide();
        $new.find('.tile-edit-controls').show();
        $new.appendTo($('#tile-grid'));
        $new.fadeIn(200);
        var rgi2 = km.keyToGauge[key];
        if (rgi2 !== undefined) {
          self._initGauge(key, rgi2, tiles[rgi2]);
        }
        if (key === 'chart' && S.startInfo.PowerGraph && window.Chart) {
          self._initChart(); self._fetchChartData();
        }
        if (key === 'clock') self._initClock();
        if (key === 'weather' && S.weather) self._updateWeatherTile();
        /* Add to order if missing */
        var ord = Store.getTileOrder(km.allKeys);
        if (ord.indexOf(key) === -1) ord.push(key);
        Store.setTileOrder(ord);
        self._buildDrawer();
        /* refresh values */
        API.get('gui_status_json').done(function(d){
          if (d && d.tiles) Pages._updateGauges(d.tiles);
          if (d) self._updateInfoTiles(d);
          if (d && d.Weather) { S.weather = d.Weather; self._updateWeatherTile(); }
        });
      });

      /* Reset layout */
      $c.on('click', '#dash-reset', function() {
        Store.resetDash();
        S.editMode = false;
        $('#customize-btn').removeClass('edit-active');
        Pages.render('status');
      });

      /* Drag and drop — live reflow */
      var _dragRafPending = false;
      $c.on('dragstart', '.tile[draggable="true"]', function(e) {
        self._dragSrc = this;
        $(this).addClass('tile-dragging');
        e.originalEvent.dataTransfer.effectAllowed = 'move';
        e.originalEvent.dataTransfer.setData('text/plain', '');
      });
      $c.on('dragend', '.tile', function() {
        $(this).removeClass('tile-dragging');
        $('#tile-grid .tile').removeClass('tile-drag-over');
        $('#tile-grid .tile-drop-placeholder').remove();
        self._dragSrc = null;
        /* Persist final order (all string keys) */
        var newOrder = [];
        $('#tile-grid').children('.tile').each(function() {
          var ti = $(this).data('tile');
          if (ti !== undefined) newOrder.push(ti);
        });
        /* Append any hidden tiles not in the visible grid */
        var ak = km.allKeys;
        for (var hi = 0; hi < ak.length; hi++) {
          if (newOrder.indexOf(ak[hi]) === -1) newOrder.push(ak[hi]);
        }
        Store.setTileOrder(newOrder);
      });
      /* Helper: find the nearest tile index for a given mouse position */
      function _nearestTileIdx(grid, x, y) {
        var $tiles = $(grid).children('.tile:not(.tile-dragging)');
        if (!$tiles.length) return -1;
        var best = -1, bestDist = Infinity;
        $tiles.each(function(i) {
          var r = this.getBoundingClientRect();
          var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
          var d = Math.abs(x - cx) + Math.abs(y - cy);
          if (d < bestDist) { bestDist = d; best = i; }
        });
        /* If mouse is past the center of the best tile, insert after; else before */
        if (best >= 0) {
          var br = $tiles[best].getBoundingClientRect();
          if (x > br.left + br.width / 2 || y > br.top + br.height / 2) best++;
        }
        return best;
      }
      $c.on('dragover', '.tile', function(e) {
        e.preventDefault();
        e.originalEvent.dataTransfer.dropEffect = 'move';
        if (!self._dragSrc || this === self._dragSrc || _dragRafPending) return;
        var tgt = this;
        _dragRafPending = true;
        requestAnimationFrame(function() {
          _dragRafPending = false;
          if (!self._dragSrc || tgt === self._dragSrc) return;
          var $grid = $('#tile-grid');
          var $src = $(self._dragSrc), $tgt = $(tgt);
          var srcIdx = $grid.children('.tile').index($src);
          var tgtIdx = $grid.children('.tile').index($tgt);
          if (srcIdx < 0 || tgtIdx < 0) return;
          if (srcIdx < tgtIdx) $src.insertAfter($tgt);
          else $src.insertBefore($tgt);
        });
      });
      /* Allow drop on empty grid space */
      $('#tile-grid').on('dragover', function(e) {
        e.preventDefault();
        e.originalEvent.dataTransfer.dropEffect = 'move';
        if (!self._dragSrc || _dragRafPending) return;
        /* Only act if hovering empty space (not a tile) */
        if ($(e.target).closest('.tile').length) return;
        var mx = e.originalEvent.clientX, my = e.originalEvent.clientY;
        _dragRafPending = true;
        requestAnimationFrame(function() {
          _dragRafPending = false;
          if (!self._dragSrc) return;
          var $grid = $('#tile-grid');
          var $src = $(self._dragSrc);
          var $others = $grid.children('.tile:not(.tile-dragging)');
          if (!$others.length) { $grid.append($src); return; }
          var idx = _nearestTileIdx($grid[0], mx, my);
          if (idx <= 0) { $src.insertBefore($others.first()); }
          else if (idx >= $others.length) { $src.insertAfter($others.last()); }
          else { $src.insertBefore($others.eq(idx)); }
        });
      }).on('drop', function(e) {
        e.preventDefault();
      });
      $c.on('drop', '.tile', function(e) {
        e.preventDefault();
        e.stopPropagation();
      });

      /* Chart buttons */
      $c.on('click', '.chart-btn', function() {
        $('.chart-btn').removeClass('active'); $(this).addClass('active');
        Pages.status._loadChart($(this).data('mins'));
      });

      /* Chart size buttons */
      $c.on('click', '.chart-size-btn', function() {
        var sz = $(this).data('csz');
        var $tile = $(this).closest('.tile-chart');
        $tile.removeClass('tile-sm tile-md tile-lg tile-xl').addClass('tile-' + sz);
        $tile.data('size', sz);
        $(this).siblings('.chart-size-btn').removeClass('active');
        $(this).addClass('active');
        Store.setChartSize(sz);
        if (S.chart) S.chart.resize();
      });

      /* Initial data fetch */
      API.get('status_json').done(function(d){ Pages.status.update(d); });
      API.get('gui_status_json').done(function(d){
        if (d && d.tiles) Pages._updateGauges(d.tiles);
        if (d) self._updateInfoTiles(d);
        if (d && d.Weather) {
          S.weather = d.Weather;
          /* Auto-show weather tile when data arrives for the first time */
          if (!Store.get('weatherSeen')) {
            Store.set('weatherSeen', true);
            if (!Store.isTileHidden('weather') && !$('[data-tile="weather"]').length) {
              var $wt = $(self._weatherTileHtml()).hide();
              $wt.appendTo($('#tile-grid'));
              $wt.fadeIn(200);
            }
          }
          self._updateWeatherTile();
        }
      });
    },

    /* --- Special tile HTML builders --- */
    _chartTileHtml: function() {
      var chartSize = Store.getChartSize() || 'xl';
      return '<div class="tile tile-chart tile-' + esc(chartSize) + '" data-tile="chart" data-size="' + esc(chartSize) + '" draggable="false">' +
        '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
        '<div class="tile-drag-handle" title="Drag to reorder">' + icon('monitor') + '</div>' +
        '<div class="tile-edit-controls" style="display:none"><div class="tile-ctrl-row">' +
        '<span class="tile-ctrl-label">Width</span>' +
        '<button class="chart-size-btn' + (chartSize==='md'?' active':'') + '" data-csz="md" title="1 column">1</button>' +
        '<button class="chart-size-btn' + (chartSize==='lg'?' active':'') + '" data-csz="lg" title="2 columns">2</button>' +
        '<button class="chart-size-btn' + (chartSize==='xl'?' active':'') + '" data-csz="xl" title="3 columns">3</button>' +
        '</div></div>' +
        '<div class="tile-title">' + esc(S.chartTitle || 'Power Output') + '</div>' +
        '<div class="chart-wrap"><canvas id="pwr-chart"></canvas></div>' +
        '<div class="chart-controls">' +
        '<button class="chart-btn" data-mins="60">1h</button>' +
        '<button class="chart-btn" data-mins="360">6h</button>' +
        '<button class="chart-btn" data-mins="1440">24h</button>' +
        '<button class="chart-btn" data-mins="10080">7d</button>' +
        '<button class="chart-btn active" data-mins="43200">30d</button>' +
        '</div></div>';
    },

    _clockTileHtml: function() {
      var savedSize = Store.getTileSize('clock') || 'sm';
      var clockMode = Store.get('clockMode', 'digital');
      return '<div class="tile tile-clock tile-' + esc(savedSize) + '" data-tile="clock" data-size="' + esc(savedSize) + '" draggable="false">' +
        '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
        '<div class="tile-drag-handle" title="Drag to reorder">' + icon('clock') + '</div>' +
        '<div class="tile-edit-controls" style="display:none"><div class="tile-ctrl-row">' +
        '<span class="tile-ctrl-label">Size</span>' +
        '<button class="tile-size-btn" data-dir="down" title="Smaller">&minus;</button>' +
        '<button class="tile-size-btn" data-dir="up" title="Larger">+</button>' +
        '</div><div class="tile-ctrl-row">' +
        '<span class="tile-ctrl-label">Style</span>' +
        '<button class="clock-mode-btn' + (clockMode==='digital'?' active':'') + '" data-cmode="digital" title="Digital">D</button>' +
        '<button class="clock-mode-btn' + (clockMode==='analog'?' active':'') + '" data-cmode="analog" title="Analog">A</button>' +
        '</div></div>' +
        '<div class="tile-title">Clock</div>' +
        '<div id="clock-face"></div></div>';
    },

    _weatherTileHtml: function() {
      var savedSize = Store.getTileSize('weather') || 'md';
      return '<div class="tile tile-weather tile-' + esc(savedSize) + '" data-tile="weather" data-size="' + esc(savedSize) + '" draggable="false">' +
        '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
        '<div class="tile-drag-handle" title="Drag to reorder">' + icon('cloud') + '</div>' +
        '<div class="tile-edit-controls" style="display:none"><div class="tile-ctrl-row">' +
        '<span class="tile-ctrl-label">Size</span>' +
        '<button class="tile-size-btn" data-dir="down" title="Smaller">&minus;</button>' +
        '<button class="tile-size-btn" data-dir="up" title="Larger">+</button>' +
        '</div></div>' +
        '<div class="tile-title">Weather</div>' +
        '<div id="weather-tile-body" class="weather-body">' +
        '<div class="text-muted" style="font-size:.8rem;text-align:center;padding:16px 0">No weather data</div>' +
        '</div></div>';
    },

    _infoTileHtml: function(idx, info) {
      var savedSize = Store.getTileSize(idx) || 'md';
      var savedFont = Store.getTileFontSize(idx) || 'md';
      /* Logs tile has special body */
      if (info.isLogs) {
        return '<div class="tile tile-info tile-logs tile-' + esc(savedSize) + ' tile-font-' + esc(savedFont) + '" ' +
          'data-tile="' + idx + '" data-size="' + esc(savedSize) + '" data-fontsize="' + esc(savedFont) + '" draggable="false">' +
          '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
          '<div class="tile-drag-handle" title="Drag to reorder">' + icon(info.icon) + '</div>' +
          Pages.status._editControlsHtml(true) +
          '<div class="tile-title">' + esc(info.title) + '</div>' +
          '<div class="tile-logs-body" id="info-logs-body">'+
          '<div class="text-muted" style="font-size:.75rem;text-align:center;padding:8px 0">No log data</div></div></div>';
      }
      var subsHtml = '';
      if (info.subs && info.subs.length) {
        subsHtml = '<div class="tile-subs" id="info-subs-' + esc(info.id) + '">';
        for (var s = 0; s < info.subs.length; s++) {
          subsHtml += '<div class="tile-sub"><span class="tile-sub-label">' + esc(info.subs[s].label) + '</span>' +
            '<span class="tile-sub-val" data-field="' + esc(info.subs[s].field) + '">--</span></div>';
        }
        subsHtml += '</div>';
      }
      return '<div class="tile tile-info tile-' + esc(savedSize) + ' tile-font-' + esc(savedFont) + '" ' +
        'data-tile="' + idx + '" data-size="' + esc(savedSize) + '" data-fontsize="' + esc(savedFont) + '" draggable="false">' +
        '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
        '<div class="tile-drag-handle" title="Drag to reorder">' + icon(info.icon) + '</div>' +
        Pages.status._editControlsHtml(true) +
        '<div class="tile-title">' + esc(info.title) + '</div>' +
        '<div class="tile-info-value" id="info-val-' + esc(info.id) + '">--</div>' +
        subsHtml + '</div>';
    },

    _tileHtml: function(idx, gaugeIdx, t) {
      var self = Pages.status;
      var sub = (t.subtype||'').toLowerCase();
      var fixed = self._FIXED_GAUGES[sub];
      if (fixed === 'thermo') return self._thermoTileHtml(idx, t);
      if (fixed === 'wifibar') return self._wifiTileHtml(idx, t, sub);
      var fuel = /fuel/i.test(t.type||'') || /fuel/i.test(t.title||'');
      var gtype = fuel ? 'fuel' : (Store.getGaugeType(idx) || self._defaultGaugeType(t.title, sub));
      var defaultSize = t['default-size'] === 3 ? 'lg' : 'md';
      /* Radial: force sm; arc: cap at lg */
      var savedSize = Store.getTileSize(idx) || defaultSize;
      if (gtype === 'radial' || gtype === 'fuel') savedSize = 'md';
      else if (gtype === 'arc' && savedSize === 'lg') savedSize = 'lg';
      var savedFont = Store.getTileFontSize(idx) || 'md';
      return '<div class="tile tile-' + esc(savedSize) + ' tile-font-' + esc(savedFont) + '" ' +
        'data-tile="' + idx + '" data-size="' + esc(savedSize) + '" data-fontsize="' + esc(savedFont) + '" data-gtype="' + esc(gtype) + '" draggable="false">' +
        '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
        '<div class="tile-drag-handle" title="Drag to reorder">' + icon('status') + '</div>' +
        Pages.status._editControlsHtml(false, idx) +
        '<div class="tile-title">' + esc(t.title) + '</div>' +
        '<div class="tile-gauge" id="gw-' + idx + '"></div>' +
        '<div class="tile-value" id="tile-val-' + idx + '">--</div></div>';
    },

    /* --- Temperature thermometer tile — classic vertical thermometer --- */
    _thermoTileHtml: function(idx, t) {
      var max = t.maximum || 100, min = t.minimum || 0;
      /* Vertical thermometer: tube (x=19..41, rounded top) + bulb (cx=30, cy=118, r=18) */
      var bp = 'M19,16 A11,11 0 0,1 41,16 L41,103.7 A18,18 0 1,1 19,103.7 Z';
      return '<div class="tile tile-md tile-thermo" data-tile="' + idx + '" data-size="md" data-gtype="thermo" ' +
        'data-min="' + min + '" data-max="' + max + '" draggable="false">' +
        '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
        '<div class="tile-drag-handle" title="Drag to reorder">' + icon('status') + '</div>' +
        '<div class="tile-edit-controls" style="display:none"></div>' +
        '<div class="tile-title">' + esc(t.title) + '</div>' +
        '<div class="thermo-wrap" id="gw-' + idx + '">' +
          '<svg class="thermo-svg" viewBox="0 0 70 140">' +
            '<defs>' +
              '<clipPath id="tclip-'+idx+'">' +
                '<path d="'+bp+'"/>' +
              '</clipPath>' +
              '<linearGradient id="tgrad-'+idx+'" gradientUnits="userSpaceOnUse" x1="0" y1="104" x2="0" y2="5">' +
                '<stop offset="0%" stop-color="#4CAF50"/>' +
                '<stop offset="25%" stop-color="#8BC34A"/>' +
                '<stop offset="50%" stop-color="#FFEB3B"/>' +
                '<stop offset="75%" stop-color="#FF9800"/>' +
                '<stop offset="100%" stop-color="#F44336"/>' +
              '</linearGradient>' +
            '</defs>' +
            /* thermometer body background */
            '<path d="'+bp+'" class="thermo-body"/>' +
            /* coloured fill (clipped to thermometer shape) */
            '<rect class="thermo-fill" id="thermo-fill-'+idx+'" x="0" y="104" width="70" height="140" ' +
              'clip-path="url(#tclip-'+idx+')" fill="url(#tgrad-'+idx+')"/>' +
            /* outline stroke */
            '<path d="'+bp+'" class="thermo-outline"/>' +
            /* tick marks on the right side */
            '<g class="thermo-ticks" id="thermo-ticks-'+idx+'"></g>' +
          '</svg>' +
        '</div>' +
        '<div class="thermo-val" id="thermo-cval-' + idx + '">--&deg;</div>' +
        '<div class="thermo-unit" id="thermo-unit-' + idx + '">&deg;C</div></div>';
    },

    /* --- WiFi signal tile — classic WiFi fan icon --- */
    _wifiTileHtml: function(idx, t, sub) {
      var isPct = sub === 'wifipercent';
      return '<div class="tile tile-md tile-wifi" data-tile="' + idx + '" data-size="md" data-gtype="wifibar" ' +
        'data-wifi-pct="' + (isPct ? '1' : '0') + '" draggable="false">' +
        '<button class="tile-hide-btn" title="Hide tile">&times;</button>' +
        '<div class="tile-drag-handle" title="Drag to reorder">' + icon('status') + '</div>' +
        '<div class="tile-edit-controls" style="display:none"></div>' +
        '<div class="tile-title">' + esc(t.title) + '</div>' +
        '<div class="wifi-wrap" id="gw-' + idx + '">' +
          '<svg class="wifi-svg" viewBox="0 0 24 24">' +
            '<path id="wifi-a3-'+idx+'" class="wifi-arc wifi-arc-dim" d="M1.42 9a16.02 16.02 0 0121.16 0" fill="none" stroke-width="2.2" stroke-linecap="round"/>' +
            '<path id="wifi-a2-'+idx+'" class="wifi-arc wifi-arc-dim" d="M5 12.55a11 11 0 0114 0" fill="none" stroke-width="2.2" stroke-linecap="round"/>' +
            '<path id="wifi-a1-'+idx+'" class="wifi-arc wifi-arc-dim" d="M8.53 16.11a6 6 0 016.95 0" fill="none" stroke-width="2.2" stroke-linecap="round"/>' +
            '<circle id="wifi-dot-'+idx+'" class="wifi-dot wifi-arc-dim" cx="12" cy="20" r="1.4"/>' +
          '</svg>' +
        '</div>' +
        '<div class="wifi-pct" id="wifi-pct-' + idx + '">--%</div>' +
        '<div class="wifi-dbm" id="wifi-dbm-' + idx + '">-- dBm</div></div>';
    },

    _editControlsHtml: function(showFontCtrl, tileKey) {
      var self = Pages.status;
      /* Determine the current gauge type for this tile to adjust controls */
      var gtype = null, isFuel = false, isFixed = false;
      if (tileKey !== undefined && S.keyMap && S.keyMap.keyToGauge[tileKey] !== undefined) {
        var gi = S.keyMap.keyToGauge[tileKey];
        var tc = (S.tileConfig && S.tileConfig[gi]) ? S.tileConfig[gi] : null;
        isFuel = tc && (/fuel/i.test(tc.type||'') || /fuel/i.test(tc.title||''));
        var sub = tc ? (tc.subtype||'').toLowerCase() : '';
        isFixed = !!self._FIXED_GAUGES[sub];
        gtype = isFixed ? self._FIXED_GAUGES[sub]
              : isFuel ? 'fuel'
              : (Store.getGaugeType(tileKey) || self._defaultGaugeType(tc ? tc.title : '', sub));
      }
      /* Fixed gauges (thermo, wifibar): no controls at all */
      if (isFixed) return '<div class="tile-edit-controls" style="display:none"></div>';
      /* Radial & fuel: no size control. Arc: size up to lg only. */
      var showSize = (gtype !== 'radial' && gtype !== 'fuel');
      var h = '<div class="tile-edit-controls" style="display:none">';
      if (showSize) {
        h += '<div class="tile-ctrl-row">' +
          '<span class="tile-ctrl-label">Size</span>' +
          '<button class="tile-size-btn" data-dir="down" title="Smaller">&minus;</button>' +
          '<button class="tile-size-btn" data-dir="up" title="Larger">+</button>' +
          '</div>';
      }
      if (showFontCtrl) {
        h += '<div class="tile-ctrl-row">' +
          '<span class="tile-ctrl-label">Font</span>' +
          '<button class="tile-font-btn" data-dir="down" title="Smaller font">A&minus;</button>' +
          '<button class="tile-font-btn" data-dir="up" title="Larger font">A+</button>' +
          '</div>';
      }
      /* Gauge style picker — hide for fuel tiles (only radial/fuel work) */
      if (tileKey !== undefined && S.keyMap && S.keyMap.keyToGauge[tileKey] !== undefined && !isFuel) {
        var cur = gtype || 'radial';
        h += '<div class="tile-ctrl-row gauge-type-picker">' +
          '<span class="tile-ctrl-label">Style</span>';
        for (var g = 0; g < self.GAUGE_TYPES.length; g++) {
          var gt = self.GAUGE_TYPES[g];
          h += '<button class="gauge-pick-btn' + (gt === cur ? ' active' : '') + '" data-gtype="' + gt + '" title="' + gt + '">' + self.GAUGE_TYPE_LABELS[gt] + '</button>';
        }
        h += '</div>';
      }
      h += '</div>';
      return h;
    },

    _initGauge: function(idx, gaugeIdx, gt) {
      var $w = $('#gw-'+idx);
      if (!$w.length || !gt) return;
      var self = Pages.status;
      var sub = (gt.subtype||gt.type||'').toLowerCase();
      /* Fixed gauges are rendered by _tileHtml — skip standard init */
      if (self._FIXED_GAUGES[sub]) return;
      var fuel = /fuel/i.test(gt.type||'') || /fuel/i.test(gt.title||'');
      var gtype = fuel ? 'fuel' : (Store.getGaugeType(idx) || self._defaultGaugeType(gt.title, sub));
      /* Tag the tile with its gauge type for CSS */
      $w.closest('.tile').attr('data-gtype', gtype);
      var zones = GenmonGauge.parseZones ? GenmonGauge.parseZones(gt.colorzones) : [];
      var labels = GenmonGauge.parseLabels ? GenmonGauge.parseLabels(gt.labels) : [];
      $w.empty();
      switch (gtype) {
        case 'fuel':
          S.gauges[gaugeIdx] = new GenmonFuelGauge($w[0], {
            min:gt.minimum||0, max:gt.maximum||100, title:gt.title||'', units:gt.units||'%'
          });
          break;
        case 'hbar':
          S.gauges[gaugeIdx] = new GenmonHBar($w[0], {
            min:gt.minimum||0, max:gt.maximum||100,
            zones:zones, labels:labels, units:gt.units||''
          });
          break;
        case 'arc':
          S.gauges[gaugeIdx] = new GenmonArc($w[0], {
            min:gt.minimum||0, max:gt.maximum||100,
            zones:zones, units:gt.units||''
          });
          break;
        default: /* radial */
          S.gauges[gaugeIdx] = new GenmonGauge($w[0], {
            min:gt.minimum||0, max:gt.maximum||100,
            labels:labels, zones:zones,
            divisions:gt.divisions||10, subdivisions:gt.subdivisions||2,
            title:gt.title||'', units:gt.units||''
          });
          break;
      }
    },

    _buildDrawer: function() {
      var tiles = S.tileConfig || [], infoTiles = Pages.status.INFO_TILES, h = '';
      var km = S.keyMap;
      if (!km) return;
      var specialTitles = {chart: S.chartTitle || 'Power Output', clock: 'Clock', weather: 'Weather'};
      for (var i = 0; i < km.allKeys.length; i++) {
        var key = km.allKeys[i];
        /* Show weather in drawer if auto-hidden (no data) or explicitly hidden */
        var isHidden = Store.isTileHidden(key);
        var isAutoHidden = (key === 'weather' && !isHidden && !S.weather && !Store.get('weatherSeen') && !$('[data-tile="weather"]').length);
        if (!isHidden && !isAutoHidden) continue;
        var title;
        if (specialTitles[key]) {
          title = specialTitles[key];
        } else if (km.keyToGauge[key] !== undefined) {
          title = tiles[km.keyToGauge[key]] ? tiles[km.keyToGauge[key]].title : '?';
        } else {
          /* Info tile */
          title = key;
          for (var ii = 0; ii < infoTiles.length; ii++) { if (infoTiles[ii].id === key) { title = infoTiles[ii].title; break; } }
        }
        h += '<div class="drawer-tile" data-tile="' + esc(key) + '">' +
          '<span class="drawer-tile-icon">+</span>' +
          '<span>' + esc(title) + '</span></div>';
      }
      $('#tile-drawer-list').html(h || '<div class="text-muted">All tiles are visible.</div>');
    },

    _updateInfoTiles: function(d) {
      var infoTiles = Pages.status.INFO_TILES;
      for (var i = 0; i < infoTiles.length; i++) {
        var it = infoTiles[i];
        /* Logs tile — special rendering */
        if (it.isLogs) {
          var $lb = $('#info-logs-body');
          var _logs = d.RecentLogs || S._cachedLogs;
          if ($lb.length && _logs) {
            var logs = _logs;
            var html = '';
            /* logs can be {Title: string} or [{Title: [entries]}] */
            if (Array.isArray(logs)) {
              for (var li = 0; li < logs.length; li++) {
                var obj = logs[li];
                for (var k in obj) {
                  if (!obj.hasOwnProperty(k)) continue;
                  var val = Array.isArray(obj[k]) ? (obj[k][0] || '') : obj[k];
                  html += '<div class="log-entry"><span class="log-label">' + esc(k) + '</span>' +
                    '<span class="log-text" title="' + esc(val) + '">' + esc(val) + '</span></div>';
                }
              }
            } else {
              for (var key in logs) {
                if (!logs.hasOwnProperty(key)) continue;
                var v = logs[key];
                if (typeof v !== 'string') v = Array.isArray(v) ? (v[0] || '') : String(v);
                html += '<div class="log-entry"><span class="log-label">' + esc(key) + '</span>' +
                  '<span class="log-text" title="' + esc(v) + '">' + esc(v) + '</span></div>';
              }
            }
            if (html) { $lb.html(html); }
            else { $lb.html('<div class="text-muted" style="font-size:.85rem;padding:6px 0">No recent log entries.</div>'); }
          }
          continue;
        }
        var $el = $('#info-val-' + it.id);
        if ($el.length) {
          var val = d[it.field] || '--';
          /* Round numeric kwOutput and append unit */
          if (it.field === 'kwOutput' && val !== '--') {
            var kwn = parseFloat(val);
            if (!isNaN(kwn)) val = roundNum(kwn) + ' kW';
          }
          /* Fallback: if power output is blank, pull from the power gauge tile */
          if (val === '--' && it.field === 'kwOutput' && S._lastGaugeTiles && S.tileConfig) {
            for (var pi = 0; pi < S.tileConfig.length; pi++) {
              if ((S.tileConfig[pi].subtype||'').toLowerCase() === 'power' && S._lastGaugeTiles[pi]) {
                var gv = S._lastGaugeTiles[pi];
                var txt = gv.text || ((gv.value != null ? roundNum(gv.value) : '') + ' ' + (S.tileConfig[pi].units||'')).trim();
                if (txt) { val = txt; break; }
              }
            }
          }
          $el.text(val);
        }
        /* Fallback: main value from outage data */
        if ($el.length && (val === '--' || val === '0V' || val === '0 V') && it.field === 'UtilityVoltage'
            && S._outageSubs && S._outageSubs.UtilityVoltage !== undefined) {
          $el.text(S._outageSubs.UtilityVoltage);
        }
        /* Update sub-values */
        if (it.subs) {
          var $subs = $('#info-subs-' + it.id);
          $subs.find('.tile-sub-val').each(function() {
            var f = $(this).data('field');
            if (f) {
              var v = d[f];
              /* Fallback: check cached status_json line data */
              if (v === undefined && S._lineSubs && S._lineSubs[f] !== undefined) v = S._lineSubs[f];
              /* Fallback: derive from gauge tile data when backend omits the field */
              if (v === undefined && S._lastGaugeTiles && S.tileConfig) {
                var gMap = {Frequency:'frequency', RPM:'rpm', OutputVoltage:'linevolts',
                            BatteryVoltage:'batteryvolts'};
                var wantSensor = gMap[f];
                if (wantSensor) {
                  for (var gi = 0; gi < S.tileConfig.length; gi++) {
                    var st = (S.tileConfig[gi].subtype||'').toLowerCase();
                    if (st === wantSensor && S._lastGaugeTiles[gi]) {
                      v = S._lastGaugeTiles[gi].text || roundNum(S._lastGaugeTiles[gi].value);
                      break;
                    }
                  }
                }
              }
              /* Fallback: check outage data for utility fields */
              if (v === undefined && S._outageSubs && S._outageSubs[f] !== undefined) v = S._outageSubs[f];
              if (v !== undefined) $(this).text(v);
            }
          });
        }
      }
    },

    /** Fetch outage_json once and cache utility voltage fields for the Line Status tile */
    _fetchOutageSubs: function() {
      API.get('outage_json').done(function(d) {
        if (!d) return;
        var items = d.Outage || d.outage || [];
        if (!Array.isArray(items)) return;
        var map = {
          'Utility Voltage': 'UtilityVoltage',
          'Utility Voltage Maximum': 'UtilityMaxVoltage',
          'Utility Voltage Minimum': 'UtilityMinVoltage',
          'Utility Threshold Voltage': 'UtilityThresholdVoltage'
        };
        var subs = {};
        for (var i = 0; i < items.length; i++) {
          var obj = items[i];
          for (var k in obj) {
            if (obj.hasOwnProperty(k) && map[k]) subs[map[k]] = obj[k];
          }
        }
        if (Object.keys(subs).length) S._outageSubs = subs;
      });
    },

    /* --- Thermometer gauge update --- */
    _updateThermo: function(domIdx, t) {
      var $tile = $('[data-tile="'+domIdx+'"]');
      if (!$tile.length) return;
      var val = parseFloat(t.value) || 0;
      var min = parseFloat($tile.attr('data-min')) || 0;
      var max = parseFloat($tile.attr('data-max')) || 100;
      var pct = Math.max(0, Math.min(1, (val - min) / (max - min)));
      /* Fill from y=104 (0%) up to y=5 (100%) */
      var fillY = 104 - pct * 99;
      $('#thermo-fill-'+domIdx).attr('y', fillY.toFixed(1));
      /* Value text */
      var dispVal = Math.round(val * 10) / 10;
      $('#thermo-cval-'+domIdx).text(dispVal + '\u00B0');
      /* Tick marks (generate once) */
      var $tg = $('#thermo-ticks-'+domIdx);
      if (!$tg.children().length) {
        var tickHtml = '';
        for (var i = 0; i <= 10; i++) {
          var y = 16 + (88 / 10) * i;
          var major = (i % 5 === 0);
          tickHtml += '<line x1="42" y1="'+y.toFixed(1)+'" x2="'+(major?55:50)+'" y2="'+y.toFixed(1)+'" class="thermo-tick'+(major?' major':'')+'"/>';
        }
        tickHtml += '<text class="thermo-label" x="57" y="19" text-anchor="start">' + max + '</text>';
        tickHtml += '<text class="thermo-label" x="57" y="106" text-anchor="start">' + min + '</text>';
        $tg.html(tickHtml);
      }
      /* Unit label */
      var unit = (t.text && t.text.indexOf('F') !== -1) ? '\u00B0F' : '\u00B0C';
      $('#thermo-unit-'+domIdx).text(unit);
    },

    /* --- WiFi signal update --- */
    _updateWifi: function(domIdx, t) {
      var $tile = $('[data-tile="'+domIdx+'"]');
      if (!$tile.length) return;
      var isPct = $tile.attr('data-wifi-pct') === '1';
      var raw = parseFloat(t.value) || 0;
      var dbm, pct;
      if (isPct) {
        pct = Math.round(Math.max(0, Math.min(100, raw)));
        dbm = Math.round(-30 - (100 - pct) * 0.6);
      } else {
        dbm = -Math.abs(raw);
        pct = Math.round(Math.max(0, Math.min(100, (dbm + 90) / 60 * 100)));
      }
      var arcs = pct >= 66 ? 3 : pct >= 33 ? 2 : pct > 0 ? 1 : 0;
      /* Single color: red(0) → yellow(60) → green(120) mapped to 0-100% */
      var hue = Math.round(pct * 1.2);          /* 0→0°  50→60°  100→120° */
      var col = 'hsl(' + hue + ',85%,45%)';
      for (var a = 1; a <= 3; a++) {
        var on = a <= arcs;
        var $arc = $('#wifi-a'+a+'-'+domIdx);
        $arc.toggleClass('wifi-arc-on', on).toggleClass('wifi-arc-dim', !on);
        if (on) { $arc.attr('stroke', col); } else { $arc.removeAttr('stroke'); }
      }
      var $dot = $('#wifi-dot-'+domIdx);
      $dot.toggleClass('wifi-arc-on', arcs > 0).toggleClass('wifi-arc-dim', arcs === 0);
      if (arcs > 0) { $dot.attr('fill', col); } else { $dot.removeAttr('fill'); }
      $('#wifi-pct-'+domIdx).text(pct + '%');
      $('#wifi-dbm-'+domIdx).text(dbm + ' dBm');
    },

    /* --- Weather tile helpers --- */
    _weatherConditionIcon: function(condition) {
      /* Map OWM detailed status to an SVG icon */
      var c = (condition || '').toLowerCase();
      if (/clear|sunny/.test(c))
        return '<svg class="wthr-icon wthr-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" fill="currentColor"/>' +
          '<g stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
          '<line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>' +
          '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>' +
          '<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>' +
          '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>' +
          '</g></svg>';
      if (/few clouds|scattered/.test(c))
        return '<svg class="wthr-icon wthr-partcloud" viewBox="0 0 24 24"><circle cx="8" cy="8" r="4" fill="currentColor" opacity=".7"/>' +
          '<g stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity=".5">' +
          '<line x1="8" y1="1" x2="8" y2="2.5"/><line x1="2" y1="8" x2="3.5" y2="8"/>' +
          '<line x1="3.17" y1="3.17" x2="4.23" y2="4.23"/><line x1="12.83" y1="3.17" x2="11.77" y2="4.23"/></g>' +
          '<path d="M18 14h-1.26A6 6 0 007 16h11a4 4 0 000-8 4.07 4.07 0 00-.76.07" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
      if (/cloud|overcast|broken/.test(c))
        return '<svg class="wthr-icon wthr-cloud" viewBox="0 0 24 24"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
      if (/rain|drizzle|shower/.test(c))
        return '<svg class="wthr-icon wthr-rain" viewBox="0 0 24 24"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" fill="none" stroke="currentColor" stroke-width="2"/>' +
          '<g stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity=".6">' +
          '<line x1="8" y1="22" x2="7" y2="25"/><line x1="12" y1="22" x2="11" y2="25"/><line x1="16" y1="22" x2="15" y2="25"/></g></svg>';
      if (/thunder|storm/.test(c))
        return '<svg class="wthr-icon wthr-storm" viewBox="0 0 24 24"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" fill="none" stroke="currentColor" stroke-width="2"/>' +
          '<polyline points="13 16 11 20 14 20 12 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      if (/snow|sleet|blizzard/.test(c))
        return '<svg class="wthr-icon wthr-snow" viewBox="0 0 24 24"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" fill="none" stroke="currentColor" stroke-width="2"/>' +
          '<g fill="currentColor" opacity=".6"><circle cx="8" cy="23" r="1"/><circle cx="12" cy="23" r="1"/><circle cx="16" cy="23" r="1"/></g></svg>';
      if (/mist|fog|haze|smoke/.test(c))
        return '<svg class="wthr-icon wthr-fog" viewBox="0 0 24 24">' +
          '<g stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
          '<line x1="3" y1="10" x2="21" y2="10"/><line x1="5" y1="14" x2="19" y2="14"/><line x1="7" y1="18" x2="17" y2="18"/></g></svg>';
      /* fallback: generic cloud */
      return '<svg class="wthr-icon wthr-cloud" viewBox="0 0 24 24"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
    },

    _updateWeatherTile: function() {
      var $body = $('#weather-tile-body');
      if (!$body.length) return;
      var w = S.weather;
      if (!w || !w.length) {
        $body.html('<div class="text-muted" style="font-size:.8rem;text-align:center;padding:16px 0">No weather data</div>');
        return;
      }
      /* Parse the array of {key: value} dicts into a flat map */
      var m = {};
      for (var i = 0; i < w.length; i++) {
        var obj = w[i];
        for (var k in obj) { if (obj.hasOwnProperty(k)) m[k] = obj[k]; }
      }
      var temp = m['Current Temperature'] || '--';
      var cond = m['Conditions'] || '';
      var humidity = m['Humidity'] || '';
      var wind = m['Wind'] || '';
      var clouds = m['Cloud Coverage'] || '';

      var h = '<div class="wthr-main">' +
        '<div class="wthr-icon-wrap">' + Pages.status._weatherConditionIcon(cond) + '</div>' +
        '<div class="wthr-temp">' + esc(temp) + '</div>' +
        '</div>';
      if (cond) h += '<div class="wthr-cond">' + esc(cond) + '</div>';
      var details = [];
      if (humidity) details.push('<span>' + icon('droplet') + ' ' + esc(humidity) + '</span>');
      if (wind) details.push('<span>' + icon('wind') + ' ' + esc(wind) + '</span>');
      if (clouds) details.push('<span>' + icon('cloud') + ' ' + esc(clouds) + '</span>');
      if (details.length) h += '<div class="wthr-details">' + details.join('') + '</div>';
      $body.html(h);
    },

    update: function(data) {
      if (!data) return;
      /* Extract utility line sub-values from status_json Line section */
      Pages.status._extractLineSubs(data);
      /* Extract recent log entries from status_json */
      Pages.status._extractLogs(data);
      /* Extract Time entries for the clock tile */
      Pages.status._extractClockTimes(data);
      var $p = $('#status-panel');
      var saved = UI.saveOpenSections($p);
      $p.html(UI.renderJson(data));
      /* Default all sections to open unless previously collapsed */
      $p.find('.status-section-title').each(function() {
        var key = $(this).text().trim();
        var shouldOpen = (key in saved) ? saved[key] : true;
        $(this).toggleClass('open', shouldOpen);
        $(this).next('.status-kv').toggle(shouldOpen);
      });
      UI.bindSectionToggles($p);
    },
    _initChart: function() {
      var ctx = document.getElementById('pwr-chart');
      if (!ctx || !window.Chart) return;
      var cs = getComputedStyle(document.documentElement);
      var gridC = cs.getPropertyValue('--chart-grid').trim() || 'rgba(148,163,184,.1)';
      var tickC = cs.getPropertyValue('--chart-tick').trim() || '#94a3b8';
      S.chart = new Chart(ctx, {
        type:'line',
        data:{ datasets:[{
          label:'kW', data:[], borderColor:'#3b82f6',
          backgroundColor:'rgba(59,130,246,.1)', tension:0, fill:true,
          pointRadius:3, pointBackgroundColor:'#3b82f6', pointBorderColor:'#3b82f6'
        }]},
        options:{
          responsive:true, maintainAspectRatio:false,
          scales:{
            x:{type:'linear', display:true, grid:{color:gridC}, ticks:{
              color:tickC, maxTicksLimit:8, maxRotation:0, autoSkip:true, font:{size:10},
              callback: function(val) {
                var d = new Date(val);
                var mm = String(d.getMonth()+1).padStart(2,'0');
                var dd = String(d.getDate()).padStart(2,'0');
                var hh = String(d.getHours()).padStart(2,'0');
                var mi = String(d.getMinutes()).padStart(2,'0');
                var span = this.max - this.min;
                /* 7d+: date only */
                if (span > 6 * 86400000) return mm+'/'+dd;
                /* 24h-7d: date + time */
                if (span > 86400000) return mm+'/'+dd+' '+hh+':'+mi;
                return hh+':'+mi;
              }
            },
            afterBuildTicks: function(axis) {
              var span = axis.max - axis.min;
              /* For 7d+: generate ticks at midnight boundaries */
              if (span > 6 * 86400000) {
                var step = span > 20 * 86400000 ? 3 : 1; /* every 3 days for 30d, every day for 7d */
                var ticks = [];
                var d = new Date(axis.min);
                d.setHours(0,0,0,0); d.setDate(d.getDate()+1); /* start at next midnight */
                while (d.getTime() <= axis.max) {
                  ticks.push({value: d.getTime()});
                  d.setDate(d.getDate() + step);
                }
                axis.ticks = ticks;
              }
            }},
            y:{display:true, grid:{color:gridC}, ticks:{color:tickC}, beginAtZero:true}
          },
          plugins:{legend:{display:false},tooltip:{callbacks:{title:function(items){
            if(!items.length)return '';
            var d=new Date(items[0].parsed.x);
            var mm=String(d.getMonth()+1).padStart(2,'0');
            var dd=String(d.getDate()).padStart(2,'0');
            var hh=String(d.getHours()).padStart(2,'0');
            var mi=String(d.getMinutes()).padStart(2,'0');
            return mm+'/'+dd+' '+hh+':'+mi;
          }}}}, animation:{duration:400}
        }
      });
    },
    _fetchChartData: function() {
      API.get('power_log_json?power_log_json=43200', 20000).done(function(d) {
        if (!d || !Array.isArray(d)) return;
        /* Parse once — data arrives newest-first; build chronological array */
        var parsed = [];
        for (var i = d.length - 1; i >= 0; i--) {
          var p = d[i];
          var raw = p[0] || '';
          var val = parseFloat(p[1]) || 0;
          var dt = null;
          try {
            /* Expect locale timestamp like "MM/DD/YY HH:MM:SS" */
            var parts = raw.split(' ');
            if (parts.length === 2) {
              var dp = parts[0].split('/');
              var tp = parts[1].split(':');
              if (dp.length === 3 && tp.length >= 2) {
                var yr = parseInt(dp[2], 10);
                if (yr < 100) yr += 2000;
                dt = new Date(yr, parseInt(dp[0], 10) - 1, parseInt(dp[1], 10),
                              parseInt(tp[0], 10), parseInt(tp[1], 10), parseInt(tp[2] || 0, 10));
              }
            }
          } catch(e) {}
          parsed.push({ raw: raw, val: val, date: dt });
        }
        S.chartRawData = parsed;
        var $active = $('#tile-grid .chart-btn.active');
        var mins = $active.length ? $active.data('mins') : 43200;
        Pages.status._loadChart(mins);
      });
    },
    _loadChart: function(mins) {
      var data = S.chartRawData;
      if (!S.chart || !data) return;
      var now = new Date();
      var cutoff = new Date(now.getTime() - mins * 60000);
      var points = [];
      for (var i = 0; i < data.length; i++) {
        var p = data[i];
        if (!p.date) continue;
        if (p.date < cutoff) continue;
        points.push({x: p.date.getTime(), y: p.val});
      }
      /* No data in range: flat line at last known value (usually 0) */
      if (!points.length && data.length) {
        var last = 0;
        for (var j = data.length - 1; j >= 0; j--) {
          if (data[j].date) { last = data[j].val; break; }
        }
        points = [{x: cutoff.getTime(), y: last}, {x: now.getTime(), y: last}];
      }
      /* Extrapolate edges: extend first value back to cutoff, last value forward to now */
      if (points.length) {
        if (points[0].x > cutoff.getTime()) {
          points.unshift({x: cutoff.getTime(), y: points[0].y});
        }
        if (points[points.length-1].x < now.getTime()) {
          points.push({x: now.getTime(), y: points[points.length-1].y});
        }
      }
      /* Remove any leftover no-data overlay */
      var $wrap = $('#pwr-chart').closest('.chart-wrap');
      $wrap.find('.chart-nodata').remove();
      /* Set time bounds so the axis is proportional */
      S.chart.options.scales.x.min = cutoff.getTime();
      S.chart.options.scales.x.max = now.getTime();
      S.chart.data.datasets[0].data = points;
      S.chart.update();
    },

    /* --- Clock tile (dual-time: Monitor + Generator) --- */
    _clockTimer: null,
    _monitorSnap: null,   /* { epoch, receivedAt } */
    _generatorSnap: null,
    _STALE_MS: 10000,

    /**
     * Parse genmon time string like "Saturday March 07, 2026 19:16:39"
     * or "Saturday March 7, 2026 19:17" (no seconds). Returns epoch ms or null.
     */
    _parseTimeStr: function(s) {
      if (!s) return null;
      var m = s.match(/\w+\s+(\w+)\s+(\d+),?\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?/);
      if (!m) return null;
      var months = {January:0,February:1,March:2,April:3,May:4,June:5,
                    July:6,August:7,September:8,October:9,November:10,December:11};
      var mon = months[m[1]];
      if (mon === undefined) return null;
      return { epoch: new Date(+m[3], mon, +m[2], +m[4], +m[5], m[6] ? +m[6] : 0).getTime(), hasSeconds: !!m[6] };
    },

    /** Extract recent log entries from status_json "Last Log Entries" section.
     *  Caches on S._cachedLogs for fallback when gui_status_json lacks RecentLogs. */
    _extractLogs: function(data) {
      if (!data) return;
      var items = data.Status || data;
      if (!Array.isArray(items)) return;
      for (var i = 0; i < items.length; i++) {
        var obj = items[i];
        if (obj && obj['Last Log Entries']) {
          var lle = obj['Last Log Entries'];
          var logs = lle.Logs || lle;
          if (logs && typeof logs === 'object' && Object.keys(logs).length) {
            S._cachedLogs = logs;
          }
          return;
        }
      }
    },

    /** Extract utility line sub-values from status_json Line section.
     *  Maps "Utility Max Voltage" etc. to the field names used by INFO_TILES. */
    _extractLineSubs: function(data) {
      if (!data) return;
      var fieldMap = {
        'Utility Max Voltage': 'UtilityMaxVoltage',
        'Utility Min Voltage': 'UtilityMinVoltage',
        'Utility Threshold Voltage': 'UtilityThresholdVoltage'
      };
      var items = data.Status || data;
      if (!Array.isArray(items)) return;
      for (var i = 0; i < items.length; i++) {
        var obj = items[i];
        if (obj && obj.Line && Array.isArray(obj.Line)) {
          var subs = {};
          for (var li = 0; li < obj.Line.length; li++) {
            var entry = obj.Line[li];
            for (var k in entry) {
              if (entry.hasOwnProperty(k) && fieldMap[k]) {
                subs[fieldMap[k]] = entry[k];
              }
            }
          }
          S._lineSubs = subs;
          return;
        }
      }
    },

    /** Extract Monitor Time / Generator Time from status_json data */
    _extractClockTimes: function(data) {
      if (!data) return;
      var self = Pages.status, timeArr = null;
      /* status_json returns {Status:[...,{Time:[...]},...]}} */
      var arr = Array.isArray(data) ? data
              : (data.Status && Array.isArray(data.Status)) ? data.Status
              : null;
      if (arr) {
        for (var i = 0; i < arr.length; i++) {
          if (arr[i] && arr[i].Time) { timeArr = arr[i].Time; break; }
        }
      } else if (data.Time) { timeArr = data.Time; }
      if (!Array.isArray(timeArr)) return;
      var now = Date.now();
      for (var j = 0; j < timeArr.length; j++) {
        var e = timeArr[j];
        if (e['Monitor Time'])   { var mt = self._parseTimeStr(e['Monitor Time']);   if (mt) self._monitorSnap   = {epoch:mt.epoch, receivedAt:now, hasSeconds:mt.hasSeconds}; }
        if (e['Generator Time']) { var gt = self._parseTimeStr(e['Generator Time']); if (gt) self._generatorSnap = {epoch:gt.epoch, receivedAt:now, hasSeconds:gt.hasSeconds}; }
      }
    },

    /** Advance snapshot by wall-clock elapsed time; flag stale after 10 s */
    _interpolate: function(snap) {
      if (!snap) return null;
      var elapsed = Date.now() - snap.receivedAt;
      var epoch = snap.hasSeconds ? snap.epoch + elapsed : snap.epoch;
      return { date: new Date(epoch), stale: elapsed > Pages.status._STALE_MS, hasSeconds: snap.hasSeconds };
    },

    _initClock: function() {
      var self = Pages.status;
      self._renderClock();
      clearInterval(self._clockTimer);
      self._clockTimer = setInterval(function() { self._renderClock(); }, 1000);
    },

    _renderClock: function() {
      var $f = $('#clock-face');
      if (!$f.length) { clearInterval(Pages.status._clockTimer); return; }
      var self = Pages.status;
      var mSnap = self._interpolate(self._monitorSnap);
      var gSnap = self._interpolate(self._generatorSnap);
      if (Store.get('clockMode', 'digital') === 'analog') {
        self._renderAnalogClock($f, mSnap, gSnap);
      } else {
        self._renderDigitalClock($f, mSnap, gSnap);
      }
    },

    _renderDigitalClock: function($f, mSnap, gSnap) {
      var pad = function(n) { return n < 10 ? '0'+n : ''+n; };
      var timeBlock = function(snap, label, cssClass) {
        if (!snap) return '<div class="clk-block ' + cssClass + ' clock-stale">' +
          '<div class="clk-lbl">' + label + '</div>' +
          '<div class="clk-time"><span class="clk-digits">--:--</span></div></div>';
        var d = snap.date, h = d.getHours(), use24 = S.useMetric;
        var ampm = h >= 12 ? 'PM' : 'AM', hDisp = use24 ? h : (h % 12 || 12);
        return '<div class="clk-block ' + cssClass + (snap.stale ? ' clock-stale' : '') + '">' +
          '<div class="clk-lbl">' + label + '</div>' +
          '<div class="clk-time">' +
            '<span class="clk-digits">' + pad(hDisp) + '<span class="clk-sep">:</span>' + pad(d.getMinutes()) + '</span>' +
            (snap.hasSeconds
              ? '<span class="clk-right"><span class="clk-sec">' + pad(d.getSeconds()) + '</span>' +
                (use24 ? '' : '<span class="clk-ampm">' + ampm + '</span>') + '</span>'
              : (use24 ? '' : '<span class="clk-right"><span class="clk-ampm">' + ampm + '</span></span>')
            ) +
          '</div></div>';
      };
      var dateLine = '';
      if (mSnap && mSnap.date) {
        var days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
        var mos  = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        var d = mSnap.date;
        dateLine = days[d.getDay()] + ', ' + mos[d.getMonth()] + ' ' + d.getDate();
      }
      $f.removeClass('clock-analog-wrap').html(
        '<div class="clock-digital clock-dual">' +
          timeBlock(mSnap, 'Monitor', 'clk-mon') +
          '<div class="clk-divider"></div>' +
          timeBlock(gSnap, 'Generator', 'clk-gen') +
          (dateLine ? '<div class="clock-date">' + dateLine + '</div>' : '') +
        '</div>'
      );
    },

    _renderAnalogClock: function($f, mSnap, gSnap) {
      var snap = mSnap || gSnap;
      if (!snap) {
        if (!$f.find('.analog-clock-svg').length)
          $f.html('<div class="text-muted" style="font-size:.75rem;text-align:center;padding:12px">Waiting for time data\u2026</div>');
        return;
      }
      var now = snap.date;
      var h = now.getHours() % 12, m = now.getMinutes(), s = now.getSeconds();
      var hAngle = (h + m/60) * 30, mAngle = (m + s/60) * 6, sAngle = s * 6;
      if (!$f.find('.analog-clock-svg').length) {
        var svg = '<svg class="analog-clock-svg" viewBox="0 0 100 100" width="100%" height="100%">' +
          '<defs><filter id="clk-shadow" x="-10%" y="-10%" width="120%" height="120%">' +
            '<feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-opacity=".15"/></filter></defs>' +
          '<circle cx="50" cy="50" r="48" fill="var(--clock-face)" stroke="var(--clock-ring)" stroke-width="1.2" filter="url(#clk-shadow)"/>' +
          '<circle cx="50" cy="50" r="46" fill="none" stroke="var(--clock-inner-ring)" stroke-width="0.3"/>';
        var nums = {0:'12', 3:'3', 6:'6', 9:'9'};
        for (var i = 0; i < 12; i++) {
          var a = i * 30, rad = (a - 90) * Math.PI / 180;
          if (nums[i] !== undefined) {
            var nr = 37;
            svg += '<text x="'+(50+nr*Math.cos(rad))+'" y="'+(50+nr*Math.sin(rad))+'" ' +
              'text-anchor="middle" dominant-baseline="central" ' +
              'fill="var(--clock-tick-major)" font-size="7" font-weight="600" ' +
              'font-family="system-ui,sans-serif">' + nums[i] + '</text>';
          } else {
            var r1 = 41, r2 = 44;
            svg += '<line x1="'+(50+r1*Math.cos(rad))+'" y1="'+(50+r1*Math.sin(rad))+'" ' +
              'x2="'+(50+r2*Math.cos(rad))+'" y2="'+(50+r2*Math.sin(rad))+'" ' +
              'stroke="var(--clock-tick-minor)" stroke-width=".7" stroke-linecap="round"/>';
          }
        }
        for (var mi = 0; mi < 60; mi++) {
          if (mi % 5 === 0) continue;
          var ma = mi * 6, mrad = (ma - 90) * Math.PI / 180;
          svg += '<circle cx="'+(50+43*Math.cos(mrad))+'" cy="'+(50+43*Math.sin(mrad))+'" r=".35" fill="var(--clock-dot)"/>';
        }
        svg += '<path id="clk-h" d="M48.5,50 L50,22 L51.5,50 Z" fill="var(--clock-hour)" stroke="var(--clock-hour)" stroke-width=".3" stroke-linejoin="round"/>' +
          '<path id="clk-m" d="M49.2,50 L50,14 L50.8,50 Z" fill="var(--clock-minute)" stroke="var(--clock-minute)" stroke-width=".2" stroke-linejoin="round"/>' +
          '<line id="clk-s" x1="50" y1="56" x2="50" y2="12" stroke="var(--accent)" stroke-width=".6" stroke-linecap="round"/>' +
          '<circle cx="50" cy="50" r="2.5" fill="var(--clock-hub)" stroke="var(--clock-hub-ring)" stroke-width=".5"/>' +
          '<circle cx="50" cy="50" r="1.2" fill="var(--accent)"/>' +
          '<text id="clk-lbl" x="50" y="66" text-anchor="middle" fill="var(--clock-tick-minor)" font-size="4" font-family="system-ui,sans-serif">Monitor</text>' +
          '</svg>' +
          '<div id="clk-gen-line" class="clock-gen-line"></div>';
        $f.addClass('clock-analog-wrap').html(svg);
      }
      $f.find('#clk-h').attr('transform', 'rotate('+hAngle+' 50 50)');
      $f.find('#clk-m').attr('transform', 'rotate('+mAngle+' 50 50)');
      $f.find('#clk-s').toggle(!!snap.hasSeconds).attr('transform', 'rotate('+sAngle+' 50 50)');
      $f.find('.analog-clock-svg').toggleClass('clock-stale-svg', !!snap.stale);
      /* Generator time line below dial */
      var pad = function(n) { return n < 10 ? '0'+n : ''+n; };
      var $gl = $f.find('#clk-gen-line');
      if (gSnap && gSnap.date) {
        var gd = gSnap.date, gh = gd.getHours(), use24 = S.useMetric;
        var gampm = gh >= 12 ? 'PM' : 'AM', ghDisp = use24 ? gh : (gh % 12 || 12);
        var gTime = pad(ghDisp) + ':' + pad(gd.getMinutes()) + (gSnap.hasSeconds ? ':' + pad(gd.getSeconds()) : '');
        $gl.html('Gen ' + gTime + (use24 ? '' : ' ' + gampm))
           .toggleClass('clock-stale', !!gSnap.stale);
      } else {
        $gl.html('Gen --:--');
      }
    }
  },

  /* ========== MAINTENANCE ========== */
  maintenance: {
    cmd: 'maint_json',
    _CMD_INFO: {
      starttransfer: {title:'Start Generator + Transfer', cls:'btn-success', desc:'Generator will start, warm up, then activate the transfer switch. Your house will run on generator power.'},
      start:         {title:'Start Generator (No Transfer)', cls:'btn-primary', desc:'Generator will start, warm up and run idle without activating the transfer switch. Your house stays on utility power.'},
      stop:          {title:'Stop Generator', cls:'btn-danger', desc:'Generator will stop. If it is powering a load, the transfer switch will deactivate first and there will be a cool-down period.'},
      auto:          {title:'Auto', cls:'btn-outline', desc:'Generator will automatically start and transfer in case of a power outage. This is the normal operating mode.'},
      off:           {title:'Off', cls:'btn-outline', desc:'Generator is turned off and will NOT start automatically in case of a power outage.'},
      manual:        {title:'Manual', cls:'btn-outline', desc:'Generator will start, warm up and run idle without activating the transfer switch.'},
      resetalarm:    {title:'Reset Alarm', cls:'btn-danger', desc:'Reset the alarm condition on your generator.'},
      ackalarm:      {title:'Acknowledge Alarm', cls:'btn-outline', desc:'Acknowledge the alarm condition on your generator.'}
    },
    render: function($c) {
      var info = S.startInfo;
      var h = '<div class="page-title">' + icon('maintenance') + ' Maintenance</div>';

      /* ── Generator Control ── */
      if (info.RemoteCommands) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('power') + ' Generator Control</div><div class="card-body">';
        h += '<div id="sw-state" class="maint-switch-state mb-2">' +
          '<span class="kv-key">Current Switch Position</span> ' +
          '<span class="maint-sw-badge">' + esc(S.switchState) + '</span></div>';

        /* Generator actions */
        h += '<div class="maint-cmd-section">' +
          '<div class="maint-cmd-label">Generator Actions</div>' +
          '<p class="form-hint" style="margin:0 0 8px">Start or stop the generator. Starting with transfer powers your house from the generator.</p>' +
          '<div class="btn-group flex-wrap">';
        if (info.RemoteTransfer)
          h += '<button class="btn btn-success btn-sm" data-cmd="starttransfer">'+btnIcon('play')+' Start + Transfer</button>';
        h += '<button class="btn btn-primary btn-sm" data-cmd="start">'+btnIcon('play')+' Start (No Transfer)</button>' +
          '<button class="btn btn-danger btn-sm" data-cmd="stop">'+btnIcon('stop')+' Stop Generator</button>' +
          '</div></div>';

        /* Switch position */
        if (info.RemoteButtons) {
          h += '<div class="maint-cmd-section">' +
            '<div class="maint-cmd-label">Switch Position</div>' +
            '<p class="form-hint" style="margin:0 0 8px">Set the generator\'s operating mode. Auto is the normal setting for automatic outage protection.</p>' +
            '<div class="btn-group flex-wrap">' +
            '<button class="btn btn-outline btn-sm" data-cmd="auto">Auto</button>' +
            '<button class="btn btn-outline btn-sm" data-cmd="off">Off</button>' +
            '<button class="btn btn-outline btn-sm" data-cmd="manual">Manual</button>' +
            '</div></div>';
        }

        /* Alarms */
        if (info.ResetAlarms || info.AckAlarms) {
          h += '<div class="maint-cmd-section">' +
            '<div class="maint-cmd-label">Alarm Control</div>' +
            '<div class="btn-group flex-wrap">';
          if (info.ResetAlarms)
            h += '<button class="btn btn-danger btn-sm" data-cmd="resetalarm">'+btnIcon('refresh')+' Reset Alarm</button>';
          if (info.AckAlarms)
            h += '<button class="btn btn-outline btn-sm" data-cmd="ackalarm">'+btnIcon('check')+' Acknowledge Alarm</button>';
          h += '</div></div>';
        }
        h += '</div></div>';
      }

      /* ── Exercise Schedule ── */
      if (info.ExerciseControls) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('clock') + ' Exercise Schedule</div><div class="card-body">' +
          '<div id="ex-info" class="maint-exercise-current mb-2">Loading…</div>' +
          '<div id="ex-data"></div>' +
          '<div class="form-row">' +
          '<div class="form-group"><label class="form-label">Day</label>' +
          '<select class="form-select" id="ex-day">' +
          'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday'.split(',').map(function(d){
            return '<option>'+d+'</option>';
          }).join('') + '</select></div>' +
          '<div class="form-group"><label class="form-label">Time</label>' +
          '<input class="form-input" type="time" id="ex-time" value="12:00"></div>' +
          '<div class="form-group"><label class="form-label">Frequency</label>' +
          '<select class="form-select" id="ex-freq">' +
          '<option>Weekly</option><option>Biweekly</option><option>Monthly</option></select></div></div>';
        if (info.WriteQuietMode)
          h += '<div class="mb-2"><label class="checkbox-label"><input type="checkbox" id="ex-quiet"> Quiet Mode</label>' +
            '<div class="form-hint">Exercise without engaging the transfer switch</div></div>';
        h += '<div class="form-actions" style="border:none;padding:0;margin:0">' +
          '<button class="btn btn-primary btn-sm" id="ex-save">'+btnIcon('save')+' Save Schedule</button></div></div></div>';
      }

      /* ── Set Generator Time ── */
      if (info.SetGenTime) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('clock') + ' Generator Time</div><div class="card-body">' +
          '<p class="form-hint" style="margin:0 0 10px">Synchronize the generator\'s internal clock with the monitor\'s system time. This may take up to one minute.</p>' +
          '<button class="btn btn-outline btn-sm" id="maint-settime">'+btnIcon('clock')+' Set Generator Time</button></div></div>';
      }

      /* ── Reset Power Log / Fuel Estimates ── */
      if (info.PowerGraph) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('trash') + ' Reset Power Log &amp; Fuel Estimate</div><div class="card-body">' +
          '<p class="form-hint" style="margin:0 0 10px">Clear the power log and reset fuel consumption estimates. Use this after refilling your fuel tank so the fuel estimate starts fresh.</p>' +
          '<button class="btn btn-danger btn-sm" id="maint-reset-power">'+btnIcon('trash')+' Reset Power Log &amp; Fuel Estimate</button></div></div>';
      }

      /* ── Custom buttons ── */
      if (info.buttons && info.buttons.length) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('cpu') + ' Custom Commands</div><div class="card-body">';
        info.buttons.forEach(function(b, idx) {
          var hasInputs = b.command_sequence && b.command_sequence.some(function(c){ return !!c.input_title; });
          h += '<div class="custom-cmd-row mb-2">';
          h += '<button class="btn btn-outline btn-sm custom-btn" data-bi="'+idx+'">' + esc(b.title) + '</button>';
          if (hasInputs) {
            b.command_sequence.forEach(function(c, ci) {
              if (!c.input_title) return;
              h += ' <input type="text" class="input input-sm custom-cmd-input" id="cmd-input-'+idx+'-'+ci+'"' +
                ' placeholder="' + esc(c.input_title) + '"' +
                (c.tooltip ? ' title="' + esc(c.tooltip) + '"' : '') +
                ' style="width:140px;display:inline-block">';
            });
          }
          h += '</div>';
        });
        h += '</div></div>';
      }

      /* ── Maintenance data from backend ── */
      h += '<div id="maint-data"><div class="text-muted text-center">Loading…</div></div>';

      $c.html(h);

      /* ── Populate exercise from gui_status ── */
      Pages.maintenance._populateExercise();

      /* ── Remote command handler ── */
      $c.on('click', '[data-cmd]', function() {
        var cmd = $(this).data('cmd');
        if (info.LoginActive && !S.writeAccess) { Modal.alert('Denied','Write access required.'); return; }
        var ci = Pages.maintenance._CMD_INFO[cmd];
        var msg = ci ? ci.desc : ('Send command: ' + cmd + '?');
        Modal.confirm(ci ? ci.title : 'Confirm', msg, function() {
          API.set('setremote', cmd).done(function(){ Modal.alert('Sent', (ci?ci.title:cmd) + ' command sent.'); });
        });
      });

      /* ── Save exercise ── */
      $('#ex-save').on('click', function() {
        var val = $('#ex-day').val()+','+$('#ex-time').val()+','+$('#ex-freq').val();
        API.set('setexercise', val).done(function(){ Modal.alert('Saved','Exercise schedule updated.'); })
          .fail(function(){ Modal.alert('Error','Failed to save.'); });
        if (info.WriteQuietMode) API.set('setquiet', $('#ex-quiet').is(':checked')?'On':'Off');
      });

      /* ── Set Generator Time ── */
      $('#maint-settime').on('click', function() {
        Modal.confirm('Set Generator Time',
          'Synchronize the generator clock with the monitor system time? This may take up to one minute.',
          function() {
            API.set('settime', ' ').done(function(){ Modal.alert('OK','Generator time set.'); })
              .fail(function(){ Modal.alert('Error','Failed to set time.'); });
          });
      });

      /* ── Reset Power Log ── */
      $('#maint-reset-power').on('click', function() {
        Modal.confirm('Reset Power Log',
          'This will delete the power log and reset fuel consumption estimates. Use this after refilling your fuel tank. Continue?',
          function() {
            API.set('power_log_clear', ' ').done(function(){ Modal.alert('OK','Power log and fuel estimate have been reset.'); })
              .fail(function(){ Modal.alert('Error','Failed to reset power log.'); });
          });
      });

      /* ── Custom button handler ── */
      $c.on('click', '.custom-btn', function() {
        var idx = $(this).data('bi');
        var b = info.buttons[idx];
        if (!b) return;
        if (b.command_sequence && b.command_sequence.length) {
          var seq = JSON.parse(JSON.stringify(b.command_sequence));
          /* Gather values from inline inputs */
          var valid = true;
          seq.forEach(function(c, ci) {
            if (!c.input_title) return;
            var val = $('#cmd-input-'+idx+'-'+ci).val() || '';
            if (c.bounds_regex) {
              try {
                if (!new RegExp(c.bounds_regex).test(val)) {
                  Modal.alert('Invalid Input', 'Value for "' + esc(c.input_title) + '" does not match the required format.');
                  valid = false;
                  return;
                }
              } catch(e) { /* bad regex, skip check */ }
            }
            if (c.type === 'int') {
              c.value = parseInt(val, 10) || 0;
            } else {
              c.value = val;
            }
          });
          if (!valid) return;
          Modal.confirm('Confirm', 'Execute command: ' + esc(b.title) + '?', function() {
            API.set('set_button_command', JSON.stringify([{onewordcommand: b.onewordcommand || b.title, command_sequence: seq}]))
              .done(function(r){ var msg = String(r).trim().replace(/^"+|"+$/g, ''); Modal.alert('Done', msg === 'OK' ? 'Command executed.' : esc(msg)); })
              .fail(function(){ Modal.alert('Error','Failed to send command.'); });
          });
        } else {
          Modal.confirm('Confirm', 'Execute command: ' + esc(b.title) + '?', function() {
            API.set('set_button_command', JSON.stringify(b.onewordcommand||b.title))
              .done(function(r){ var msg = String(r).trim().replace(/^"+|"+$/g, ''); Modal.alert('Done', msg === 'OK' ? 'Command executed.' : esc(msg)); });
          });
        }
      });

      /* ── Initial fetch ── */
      API.get('maint_json').done(function(d){ Pages.maintenance.update(d); });
    },
    _populateExercise: function() {
      /* Try to get current exercise schedule from last polled gui_status into form */
      API.get('gui_status_json').done(function(d) {
        if (!d || !d.ExerciseInfo) return;
        var ei = d.ExerciseInfo;
        if (ei.Day) $('#ex-day').val(ei.Day);
        if (ei.Hour != null && ei.Minute != null)
          $('#ex-time').val(String(ei.Hour).padStart(2,'0')+':'+String(ei.Minute).padStart(2,'0'));
        if (ei.Frequency) $('#ex-freq').val(ei.Frequency);
        if (ei.QuietMode === 'On') $('#ex-quiet').prop('checked', true);
        /* show current schedule text */
        var txt = (ei.Frequency||'Weekly')+' '+( ei.Day||'')+' '+
          String(ei.Hour||0).padStart(2,'0')+':'+String(ei.Minute||0).padStart(2,'0');
        if (ei.QuietMode) txt += ' — Quiet Mode ' + ei.QuietMode;
        $('#ex-info').html('<span class="kv-key">Current Schedule</span> <span class="kv-val" style="font-weight:600">'+esc(txt)+'</span>');
      });
    },
    _renderMaintData: function(data) {
      /* Render maint_json as cards similar to Monitor page */
      var sections = data.Maintenance || data.maintenance || [];
      if (!Array.isArray(sections) || !sections.length) {
        UI.refreshJsonPanel($('#maint-data'), data);
        return;
      }
      var h = '';
      /* Group flat kv pairs vs sub-sections */
      var flat = [], subs = [];
      sections.forEach(function(item) {
        for (var k in item) {
          if (!item.hasOwnProperty(k)) continue;
          if (Array.isArray(item[k])) {
            subs.push({name: k, items: item[k]});
          } else {
            flat.push({key: k, val: item[k]});
          }
        }
      });
      if (flat.length) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('about') + ' Generator Info</div><div class="card-body">';
        flat.forEach(function(f) {
          h += '<div class="kv-row"><span class="kv-key">'+esc(f.key)+'</span><span class="kv-val">'+esc(f.val!=null?f.val:'--')+'</span></div>';
        });
        h += '</div></div>';
      }
      var exHtml = '';
      function _collectExKv(items) {
        if (!Array.isArray(items)) return;
        items.forEach(function(item) {
          if (item && typeof item === 'object') {
            for (var k in item) {
              if (!item.hasOwnProperty(k)) continue;
              if (Array.isArray(item[k])) { _collectExKv(item[k]); }
              else {
                /* Skip "Exercise Time" — already shown formatted in #ex-info */
                var kl = k.toLowerCase();
                if (kl === 'exercise time' || kl === 'exercise frequency') continue;
                exHtml += '<div class="kv-row"><span class="kv-key">'+esc(k)+'</span><span class="kv-val">'+esc(item[k]!=null?item[k]:'--')+'</span></div>';
              }
            }
          }
        });
      }
      subs.forEach(function(s) {
        var nl = s.name.toLowerCase();
        /* Merge any Exercise section into the Exercise Schedule card */
        if (nl === 'exercise' || nl === 'exercise time') {
          _collectExKv(s.items);
          return;
        }
        h += '<div class="card mb-2"><div class="card-header">' + icon('maintenance') + ' '+esc(s.name)+'</div><div class="card-body">';
        if (Array.isArray(s.items)) {
          s.items.forEach(function(item) {
            if (item && typeof item === 'object') {
              for (var k in item) {
                if (item.hasOwnProperty(k))
                  h += '<div class="kv-row"><span class="kv-key">'+esc(k)+'</span><span class="kv-val">'+esc(item[k]!=null?item[k]:'--')+'</span></div>';
              }
            }
          });
        }
        h += '</div></div>';
      });
      if (exHtml) $('#ex-data').html(exHtml);
      $('#maint-data').html(h);
    },
    update: function(data) {
      if (!data) return;
      Pages.maintenance._renderMaintData(data);
      $('#sw-state').html(
        '<span class="kv-key">Current Switch Position</span> ' +
        '<span class="maint-sw-badge">' + esc(S.switchState) + '</span>');
    }
  },

  /* ========== OUTAGE ========== */
  outage: {
    cmd: 'outage_json',
    render: function($c) {
      $c.html('<div class="page-title">'+icon('outage')+' Outage Log</div>' +
        '<div id="outage-data"><div class="text-muted text-center">Loading…</div></div>');
      API.get('outage_json').done(function(d){ Pages.outage.update(d); });
    },
    update: function(d) {
      if (!d) return;
      var sections = d.Outage || d.outage || [];
      if (!Array.isArray(sections) || !sections.length) {
        UI.refreshJsonPanel($('#outage-data'), d);
        return;
      }
      var secIcons = {
        'Outage Log': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
      };
      var flat = [], subs = [];
      sections.forEach(function(item) {
        for (var k in item) {
          if (!item.hasOwnProperty(k)) continue;
          var v = item[k];
          if (Array.isArray(v)) {
            subs.push({name:k, items:v});
          } else if (v && typeof v === 'object') {
            subs.push({name:k, items:v});
          } else {
            flat.push({key:k, val:v});
          }
        }
      });
      var h = '';
      if (flat.length) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('outage') + ' Outage Status</div><div class="card-body">';
        flat.forEach(function(f) {
          var cls = '';
          var kl = f.key.toLowerCase();
          if (kl === 'system in outage') cls = (String(f.val).toLowerCase() === 'yes') ? ' mon-val-warn' : ' mon-val-ok';
          h += '<div class="kv-row"><span class="kv-key">'+esc(f.key)+'</span><span class="kv-val'+cls+'">'+esc(f.val!=null?f.val:'--')+'</span></div>';
        });
        h += '</div></div>';
      }
      subs.forEach(function(s) {
        var ic = secIcons[s.name] || '';
        h += '<div class="card mb-2"><div class="card-header">' + ic + ' ' + esc(s.name) + '</div><div class="card-body">';
        var items = Array.isArray(s.items) ? s.items : [s.items];
        items.forEach(function(item) {
          if (typeof item === 'string') {
            h += '<div class="kv-row" style="padding:4px 0;font-size:.85rem">' + esc(item) + '</div>';
          } else if (item && typeof item === 'object') {
            for (var k in item) {
              if (item.hasOwnProperty(k))
                h += '<div class="kv-row"><span class="kv-key">'+esc(k)+'</span><span class="kv-val">'+esc(item[k]!=null?item[k]:'--')+'</span></div>';
            }
          }
        });
        h += '</div></div>';
      });
      $('#outage-data').html(h || '<div class="text-muted text-center">No outage data.</div>');
    }
  },

  /* ========== LOGS ========== */
  logs: {
    cmd: 'logs_json',
    render: function($c) {
      $c.html(
        '<div class="page-title">' + icon('logs') + ' Logs</div>' +
        '<div id="cal-heatmap" class="cal-heatmap-wrap"></div>' +
        '<div id="logs-data"><div class="text-muted text-center">Loading…</div></div>'
      );
      API.get('logs_json').done(function(d){ Pages.logs.update(d); });
    },
    update: function(d) {
      Pages.logs._renderLogCards(d);
      Pages.logs._buildCalendar(d);
    },
    /* Flatten [{"Alarm Log":[...]},{"Run Log":[...]}] into {"Alarm Log":[...],"Run Log":[...]} */
    _flattenLogs: function(raw) {
      if (!Array.isArray(raw)) return raw;
      var out = {};
      for (var i = 0; i < raw.length; i++) {
        var item = raw[i];
        if (item && typeof item === 'object') {
          for (var k in item) { if (item.hasOwnProperty(k)) out[k] = item[k]; }
        }
      }
      return out;
    },
    _renderLogCards: function(d) {
      if (!d || !d.Logs) { UI.refreshJsonPanel($('#logs-data'), d); return; }
      var logs = this._flattenLogs(d.Logs);
      var secIcons = {
        'Alarm Log':   icon('warning'),
        'Service Log': icon('maintenance'),
        'Run Log':     icon('play')
      };
      var h = '';
      for (var logName in logs) {
        if (!logs.hasOwnProperty(logName)) continue;
        var entries = logs[logName];
        var ic = secIcons[logName] || icon('logs');
        h += '<div class="card mb-2"><div class="card-header">' + ic + ' ' + esc(logName);
        if (Array.isArray(entries)) h += ' <span class="badge" style="font-size:.7rem;margin-left:6px;background:var(--bg-3);padding:2px 8px;border-radius:10px">' + entries.length + '</span>';
        h += '</div><div class="card-body">';
        if (Array.isArray(entries) && entries.length) {
          entries.forEach(function(e) {
            h += '<div class="kv-row" style="padding:4px 0;font-size:.85rem">' + esc(e) + '</div>';
          });
        } else {
          h += '<div class="text-muted">No entries.</div>';
        }
        h += '</div></div>';
      }
      $('#logs-data').html(h || '<div class="text-muted text-center">No log data.</div>');
    },

    /* ---- Calendar heatmap (GitHub-style 1-year lookback) ---- */
    _parseBuckets: function(d) {
      var buckets = {}; // key = 'YYYY-MM-DD'
      var today = new Date();
      today.setHours(0,0,0,0);
      var oneYearAgo = new Date(today);
      oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);

      var severityMap = function(name) {
        var n = (name || '').toLowerCase();
        if (n.indexOf('alarm') !== -1) return 3;
        if (n.indexOf('service') !== -1) return 2;
        return 1;
      };
      var dateRe = /^\s*(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})\s+(\d{1,2}:\d{2}:\d{2})\s+(.*)$/;

      var flatLogs = Pages.logs._flattenLogs(d.Logs);
      for (var logName in flatLogs) {
        if (!flatLogs.hasOwnProperty(logName)) continue;
        var entries = flatLogs[logName];
        if (!Array.isArray(entries)) continue;
        var sev = severityMap(logName);
        for (var i = 0; i < entries.length; i++) {
          var m = dateRe.exec(entries[i]);
          if (!m) continue;
          var p1 = parseInt(m[1],10), p2 = parseInt(m[2],10), yr = parseInt(m[3],10);
          if (yr < 100) yr += 2000;
          var mm, dd;
          if (S.altDateFmt) { dd = p1; mm = p2; } else { mm = p1; dd = p2; }
          if (mm < 1 || mm > 12 || dd < 1 || dd > 31) continue;
          var entryDate = new Date(yr, mm - 1, dd);
          if (entryDate < oneYearAgo || entryDate > today) continue;
          var key = yr + '-' + ('0'+mm).slice(-2) + '-' + ('0'+dd).slice(-2);
          if (!buckets[key]) buckets[key] = {sev:0, events:[]};
          if (sev > buckets[key].sev) buckets[key].sev = sev;
          buckets[key].events.push(m[5].trim());
        }
      }
      return buckets;
    },

    _buildCalendar: function(d) {
      var $w = $('#cal-heatmap');
      if (!$w.length || !d || !d.Logs) return;

      /* Parse and cache buckets */
      var buckets = Pages.logs._parseBuckets(d);
      Pages.logs._calBuckets = buckets;

      /* Determine how many months to show based on viewport */
      var screenW = window.innerWidth || document.documentElement.clientWidth;
      var totalMonths;
      if (screenW <= 480) totalMonths = 1;
      else if (screenW <= 768) totalMonths = 6;
      else totalMonths = 12;
      Pages.logs._calTotalMonths = totalMonths;
      Pages.logs._calPage = 0;

      Pages.logs._renderCalPage();
    },

    _renderCalPage: function() {
      var $w = $('#cal-heatmap');
      if (!$w.length) return;
      var buckets = Pages.logs._calBuckets || {};
      var totalMonths = Pages.logs._calTotalMonths || 12;
      var page = Pages.logs._calPage || 0;

      var today = new Date();
      today.setHours(0,0,0,0);

      /* For paging: page 0 = most recent N months, page 1 = previous N, etc.
         When totalMonths < 12, we allow paging through the year. */
      var maxPages = Math.ceil(12 / totalMonths);
      if (page >= maxPages) page = maxPages - 1;
      if (page < 0) page = 0;
      Pages.logs._calPage = page;

      /* Calculate start/end for this page */
      var endDate = new Date(today);
      endDate.setMonth(endDate.getMonth() - page * totalMonths);
      var startDate = new Date(endDate);
      startDate.setMonth(startDate.getMonth() - totalMonths);
      /* Snap start to beginning of that week */
      var startDay = new Date(startDate);
      startDay.setDate(startDay.getDate() - startDay.getDay());
      /* Snap end */
      var endDay = new Date(endDate);

      /* Count weeks */
      var tmpD = new Date(startDay);
      var weeks = 0;
      while (tmpD <= endDay) { tmpD.setDate(tmpD.getDate() + 7); weeks++; }
      if (weeks < 1) weeks = 1;

      var CELL = 11, GAP = 2, STEP = CELL + GAP;
      var MONTH_GAP = 6; /* extra px between months */
      var days = 7;
      var LEFT = 32;
      var TOP = 4;
      var BOTTOM_LABEL = 14; /* space below grid for month labels */

      /* Per-cell month gaps: when the 1st of a month appears mid-column,
         cells before the 1st stay at the old x-offset while cells from
         the 1st onward shift right by MONTH_GAP, visually splitting the
         straddling week column into two partial columns. */
      var monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      var lastMonth = -1;
      var gapOffset = 0;
      var monthLabelPositions = [];
      var maxX = LEFT;
      var cellsHtml = '';

      var cursor = new Date(startDay);
      for (var wi = 0; wi < weeks; wi++) {
        for (var dj = 0; dj < 7; dj++) {
          if (cursor > endDay || cursor < startDate) {
            cursor.setDate(cursor.getDate() + 1);
            continue;
          }
          var cm = cursor.getMonth();
          if (cm !== lastMonth) {
            if (lastMonth !== -1) gapOffset += MONTH_GAP;
            var yr = cursor.getFullYear() % 100;
            monthLabelPositions.push({
              x: LEFT + wi * STEP + gapOffset,
              label: monthNames[cm] + " \u2019" + ('0' + yr).slice(-2)
            });
            lastMonth = cm;
          }
          var cellX = LEFT + wi * STEP + gapOffset;
          if (cellX + CELL > maxX) maxX = cellX + CELL;
          var ck = cursor.getFullYear() + '-' + ('0'+(cm+1)).slice(-2) + '-' + ('0'+cursor.getDate()).slice(-2);
          var b = buckets[ck];
          var lvl = b ? b.sev : 0;
          var cls = 'cal-cell cal-lv' + lvl;
          var tip = ck;
          if (b && b.events.length) {
            tip += '\n' + b.events.join('\n');
          } else {
            tip += '\nNo events';
          }
          cellsHtml += '<rect x="' + cellX + '" y="' + (TOP + dj * STEP) +
            '" width="' + CELL + '" height="' + CELL + '" rx="2" class="' + cls + '">' +
            '<title>' + tip.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</title></rect>';
          cursor.setDate(cursor.getDate() + 1);
        }
      }

      var W = maxX + GAP + 2;
      var H = TOP + days * STEP + BOTTOM_LABEL + 2;

      var html = '<svg class="cal-heatmap-svg" viewBox="0 0 ' + W + ' ' + H +
                 '" width="100%" preserveAspectRatio="xMidYMin meet" role="img" aria-label="Log activity heatmap">';

      /* Day-of-week labels (left side) */
      var dayLabels = ['','Mon','','Wed','','Fri','','Sun'];
      for (var di = 0; di < 7; di++) {
        if (dayLabels[di]) {
          html += '<text x="' + (LEFT - 4) + '" y="' + (TOP + di * STEP + CELL - 1) +
            '" text-anchor="end" class="cal-label">' + dayLabels[di] + '</text>';
        }
      }

      html += cellsHtml;

      /* Month + year labels along bottom */
      var labelY = TOP + days * STEP + BOTTOM_LABEL - 2;
      for (var ml = 0; ml < monthLabelPositions.length; ml++) {
        html += '<text x="' + monthLabelPositions[ml].x + '" y="' + labelY +
          '" class="cal-label cal-month-label">' + monthLabelPositions[ml].label + '</text>';
      }

      html += '</svg>';

      /* Legend + page controls */
      html += '<div class="cal-legend">';
      if (totalMonths < 12) {
        html += '<span class="cal-page-nav">' +
          '<button class="cal-pg-btn" id="cal-pg-prev" title="Older"' + (page >= maxPages - 1 ? ' disabled' : '') + '>&lsaquo;</button>' +
          '<button class="cal-pg-btn" id="cal-pg-next" title="Newer"' + (page <= 0 ? ' disabled' : '') + '>&rsaquo;</button></span>';
      }
      html += '<span class="cal-legend-label">Less</span>' +
        '<span class="cal-cell-preview cal-lv0"></span>' +
        '<span class="cal-cell-preview cal-lv1"></span>' +
        '<span class="cal-cell-preview cal-lv2"></span>' +
        '<span class="cal-cell-preview cal-lv3"></span>' +
        '<span class="cal-legend-label">More severe</span>' +
        '<span class="cal-legend-key"><span class="cal-dot cal-lv1"></span>Run' +
        '<span class="cal-dot cal-lv2"></span>Service' +
        '<span class="cal-dot cal-lv3"></span>Alarm</span></div>';

      $w.html(html);

      /* Bind page buttons */
      if (totalMonths < 12) {
        $('#cal-pg-prev').on('click', function() {
          Pages.logs._calPage++;
          Pages.logs._renderCalPage();
        });
        $('#cal-pg-next').on('click', function() {
          Pages.logs._calPage--;
          Pages.logs._renderCalPage();
        });
      }
    }
  },

  /* ========== MONITOR ========== */
  monitor: {
    cmd: 'monitor_json',
    render: function($c) {
      $c.html('<div class="page-title">'+icon('monitor')+' Monitor</div>' +
        '<div id="mon-data"><div class="text-muted text-center">Loading…</div></div>');
      API.get('monitor_json').done(function(d){ Pages.monitor.update(d); });
    },
    update: function(d) {
      if (!d) return;
      /* d = {Monitor: [{sectionName: [{key:val},...] }, ...]} */
      var sections = d.Monitor || d.monitor || [];
      if (!Array.isArray(sections) || !sections.length) {
        /* fallback to generic renderer if unexpected shape */
        UI.refreshJsonPanel($('#mon-data'), d);
        return;
      }

      /* icon map for section headers */
      var secIcons = {
        'Generator Monitor Stats':
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
        'Communication Stats':
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M22 2L11 13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
        'Platform Stats':
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
        'Weather':
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z"/></svg>',
        'External Data':
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>'
      };

      var h = '';
      sections.forEach(function(secObj) {
        for (var secName in secObj) {
          if (!secObj.hasOwnProperty(secName)) continue;
          var items = secObj[secName];
          var ic = secIcons[secName] || '';
          h += '<div class="card mb-2"><div class="card-header">' + ic + ' ' + esc(secName) + '</div><div class="card-body">';

          if (Array.isArray(items)) {
            items.forEach(function(item) {
              if (item && typeof item === 'object') {
                for (var k in item) {
                  if (!item.hasOwnProperty(k)) continue;
                  var v = item[k];
                  if (v && typeof v === 'object') {
                    /* nested sub-section */
                    h += '<div class="mon-subsec"><div class="mon-subsec-title">' + esc(k) + '</div>';
                    h += Pages.monitor._renderObj(v);
                    h += '</div>';
                  } else {
                    h += Pages.monitor._kvRow(k, v);
                  }
                }
              }
            });
          } else if (items && typeof items === 'object') {
            /* External Data: object with named sub-sections */
            h += '<div class="ext-data-grid">';
            for (var edKey in items) {
              if (!items.hasOwnProperty(edKey)) continue;
              h += '<div class="ext-data-card"><div class="ext-data-card-hdr">' + esc(edKey) + '</div>' +
                '<div class="ext-data-card-body">' + Pages.monitor._renderObj(items[edKey]) + '</div></div>';
            }
            h += '</div>';
          }
          h += '</div></div>';
        }
      });

      $('#mon-data').html(h);
    },
    _renderObj: function(obj) {
      var h = '';
      if (Array.isArray(obj)) {
        obj.forEach(function(item) {
          if (item && typeof item === 'object') {
            for (var k in item) {
              if (!item.hasOwnProperty(k)) continue;
              var v = item[k];
              if (v && typeof v === 'object') {
                h += '<div class="ext-data-nested"><div class="ext-data-nested-hdr">' + esc(k) + '</div>' +
                  Pages.monitor._renderObj(v) + '</div>';
              } else {
                h += Pages.monitor._kvRow(k, v);
              }
            }
          } else {
            h += Pages.monitor._kvRow('#' + obj.indexOf(item), item);
          }
        });
      } else if (obj && typeof obj === 'object') {
        for (var k in obj) {
          if (!obj.hasOwnProperty(k)) continue;
          var v = obj[k];
          if (v && typeof v === 'object') {
            h += '<div class="ext-data-nested"><div class="ext-data-nested-hdr">' + esc(k) + '</div>' +
              Pages.monitor._renderObj(v) + '</div>';
          } else {
            h += Pages.monitor._kvRow(k, v);
          }
        }
      }
      return h;
    },
    _kvRow: function(k, v) {
      var val = (v != null) ? String(v) : '--';
      var cls = '';
      /* highlight certain values */
      var kl = k.toLowerCase();
      if (kl.indexOf('error') >= 0 || kl.indexOf('exception') >= 0 || kl.indexOf('invalid') >= 0) {
        var num = parseFloat(val);
        if (!isNaN(num) && num > 0) cls = ' mon-val-warn';
      }
      if (kl === 'monitor health') {
        cls = val.toLowerCase() === 'ok' ? ' mon-val-ok' : ' mon-val-warn';
      }
      if (kl === 'update available') {
        cls = val.toLowerCase() === 'no' ? '' : ' mon-val-warn';
      }
      if (kl === 'status') {
        var vl = val.toLowerCase();
        cls = (vl === 'ok' || vl === 'sleeping' || vl === 'mppt') ? ' mon-val-ok' : ' mon-val-warn';
      }
      return '<div class="kv-row"><span class="kv-key">' + esc(k) +
        '</span><span class="kv-val' + cls + '">' + esc(val) + '</span></div>';
    }
  },

  /* ========== NOTIFICATIONS ========== */
  notifications: {
    cmd: null, // manual fetch
    render: function($c) {
      $c.html('<div class="page-title">'+icon('notifications')+' Notifications</div>' +
        '<div id="notif-wrap"><div class="text-muted text-center">Loading…</div></div>');
      API.get('notifications').done(function(d){ Pages.notifications._build(d); });
    },
    _build: function(data) {
      if (!data) return;
      var CATS = ['outage','error','warn','info','software_update','fuel'];
      var CAT_LABELS = {outage:'Outage',error:'Error',warn:'Warning',info:'Info',software_update:'Updates',fuel:'Fuel'};
      var sorted = [];
      for (var em in data) {
        if (!data.hasOwnProperty(em)) continue;
        var raw = data[em][1];
        var cats = (raw && raw.length) ? raw.split(',') : CATS.slice();
        sorted.push({ email:em, order:data[em][0], cats:cats });
      }
      sorted.sort(function(a,b){return a.order-b.order;});

      function recipientCard(r) {
        var c = '<div class="notif-card">' +
          '<div class="notif-card-top">' +
          '<input class="form-input n-email" type="email" name="notif_email" autocomplete="email" value="'+esc(r.email)+'" placeholder="email@example.com">' +
          '<button class="btn btn-sm btn-danger n-del" title="Remove">&times;</button></div>' +
          '<div class="notif-cats">';
        CATS.forEach(function(cat) {
          var checked = r.cats.indexOf(cat) >= 0 ? ' checked' : '';
          c += '<label class="notif-cat-label"><input type="checkbox" class="n-cat" data-cat="'+esc(cat)+'"'+checked+'>' +
            '<span class="notif-cat-chip">'+(CAT_LABELS[cat]||cat)+'</span></label>';
        });
        c += '</div></div>';
        return c;
      }

      var h = '<div class="card"><div class="card-header">' + icon('mail') + ' Email Recipients</div><div class="card-body">' +
        '<div id="notif-list" class="notif-list">';
      sorted.forEach(function(r) { h += recipientCard(r); });
      h += '</div>' +
        '<div class="form-actions" style="border:none;margin-top:12px">' +
        '<button class="btn btn-sm btn-outline" id="n-add">'+btnIcon('plus')+' Add Recipient</button>' +
        '<button class="btn btn-sm btn-primary" id="n-save">'+btnIcon('save')+' Save</button></div></div></div>';

      var $w = $('#notif-wrap').html(h);

      /* Add */
      $('#n-add').on('click', function() {
        var card = recipientCard({email:'', cats:[]});
        $('#notif-list').append(card);
      });
      /* Delete */
      $w.on('click', '.n-del', function(){ $(this).closest('.notif-card').remove(); });
      /* Save */
      $('#n-save').on('click', function() {
        var parts = [];
        $w.find('.notif-card').each(function() {
          var em = $(this).find('.n-email').val().trim();
          if (!em) return;
          var cats = [];
          $(this).find('.n-cat:checked').each(function(){ cats.push($(this).data('cat')); });
          parts.push(em+'='+cats.join(','));
        });
        Modal.restart('Notification settings saved. Service is restarting\u2026');
        $.ajax({ url: CFG.baseUrl + 'setnotifications',
          data: { setnotifications: parts.join('&') } });
        delete S.dirty['notifications'];
      });

      /* Dirty tracking for notifications */
      function _notifSnap() {
        var parts = [];
        $w.find('.notif-card').each(function() {
          var em = $(this).find('.n-email').val().trim();
          var cats = [];
          $(this).find('.n-cat:checked').each(function(){ cats.push($(this).data('cat')); });
          parts.push(em+'='+cats.join(','));
        });
        return parts.join('&');
      }
      var _notifInitial = _notifSnap();
      $w.on('change input', '.n-email, .n-cat', function() {
        S.dirty['notifications'] = (_notifSnap() !== _notifInitial);
      });
      $w.on('click', '.n-del', function() {
        setTimeout(function() { S.dirty['notifications'] = (_notifSnap() !== _notifInitial); }, 0);
      });
      $('#n-add').on('click', function() {
        setTimeout(function() { S.dirty['notifications'] = (_notifSnap() !== _notifInitial); }, 0);
      });
    },
    update: function() {}
  },

  /* ========== SERVICE JOURNAL ========== */
  journal: {
    cmd: 'get_maint_log_json',
    _data: [],
    _newestFirst: false,
    render: function($c) {
      var calIcon = '<svg class="cal-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/>' +
        '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';
      var h = '<div class="page-title">'+icon('journal')+' Service Journal</div>';
      h += '<div class="card mb-2"><div class="card-header">' + icon('plus') + ' New Entry</div><div class="card-body">' +
        '<div class="form-row">' +
        '<div class="form-group"><label class="form-label">Date</label>' +
        '<div class="input-icon-wrap">' + calIcon +
        '<input class="form-input input-with-icon" type="datetime-local" id="j-date"></div></div>' +
        '<div class="form-group"><label class="form-label">Type</label>' +
        '<select class="form-select" id="j-type"><option>Maintenance</option><option>Repair</option>' +
        '<option>Check</option><option>Observation</option></select></div>' +
        '<div class="form-group"><label class="form-label">Engine Hours</label>' +
        '<input class="form-input" type="number" id="j-hours" min="0" step="0.1" placeholder="0"></div></div>' +
        '<div class="form-group"><label class="form-label">Comment</label>' +
        '<textarea class="form-textarea" id="j-cmt" rows="2" placeholder="Describe the work performed…"></textarea></div>' +
        '<div class="form-actions" style="border:none;padding:0;margin:0">' +
        '<button class="btn btn-sm btn-primary" id="j-add">'+btnIcon('plus')+' Add Entry</button></div></div></div>';
      h += '<div class="set-toolbar">' +
        '<div class="set-search-wrap">' +
        btnIcon('search', 16) +
        '<input class="set-search-input" id="j-search" type="text" placeholder="Search journal\u2026"></div>' +
        '<button class="btn btn-sm btn-outline" id="j-sort-toggle">' +
        btnIcon('sort', 14) + ' <span id="j-sort-label">Newest First</span></button></div>';
      h += '<div id="j-list" class="journal-list"><div class="text-muted text-center">Loading…</div></div>';
      $c.html(h);

      Pages.journal._newestFirst = Store.get('journalNewestFirst', false);
      function _updateSortBtn() {
        var nf = Pages.journal._newestFirst;
        $('#j-sort-label').text(nf ? 'Newest First' : 'Oldest First');
        $('#j-sort-toggle').toggleClass('btn-primary', nf).toggleClass('btn-outline', !nf);
      }
      _updateSortBtn();

      $('#j-sort-toggle').on('click', function() {
        Pages.journal._newestFirst = !Pages.journal._newestFirst;
        Store.set('journalNewestFirst', Pages.journal._newestFirst);
        Store._flush();
        _updateSortBtn();
        Pages.journal._renderList();
      });

      $('#j-search').on('input', function() { Pages.journal._renderList(); });

      $('#j-date').val(new Date().toISOString().slice(0,16));

      /* Auto-fill engine hours from the global polling data */
      if (S.runHours) {
        $('#j-hours').val(S.runHours);
      }

      $('#j-add').on('click', function() {
        var d = new Date($('#j-date').val());
        var entry = {
          date: String(d.getMonth()+1).padStart(2,'0')+'/'+String(d.getDate()).padStart(2,'0')+'/'+
                d.getFullYear()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'),
          type: $('#j-type').val(), hours: parseFloat($('#j-hours').val()) || 0, comment: $('#j-cmt').val()
        };
        API.set('add_maint_log', JSON.stringify(entry)).done(function() {
          $('#j-cmt').val('');
          delete S.dirty['journal'];
          API.get('get_maint_log_json').done(function(d){ Pages.journal._list(d); });
        }).fail(function(){ Modal.alert('Error','Failed to add entry.'); });
      });

      /* Dirty tracking: mark dirty when the comment has content */
      $('#j-cmt').on('input', function() {
        if ($(this).val().trim()) S.dirty['journal'] = true;
        else delete S.dirty['journal'];
      });

      API.get('get_maint_log_json').done(function(d){ Pages.journal._list(d); })
        .fail(function(){ Pages.journal._list([]); });
    },
    _list: function(data) {
      /* Handle string, object wrapper, or direct array */
      if (typeof data === 'string') { try { data = JSON.parse(data); } catch(e) { data = []; } }
      if (data && !Array.isArray(data) && typeof data === 'object') {
        /* If backend wraps in object, find the array value */
        var keys = Object.keys(data);
        for (var i = 0; i < keys.length; i++) {
          if (Array.isArray(data[keys[i]])) { data = data[keys[i]]; break; }
        }
      }
      Pages.journal._data = data && Array.isArray(data) ? data : [];
      Pages.journal._renderList();
    },
    _renderList: function() {
      var all = Pages.journal._data;
      if (!all.length) {
        $('#j-list').html('<div class="text-muted text-center">No journal entries.</div>');
        return;
      }
      /* Build index array so we keep original indices for edit/delete */
      var indices = [];
      for (var i = 0; i < all.length; i++) indices.push(i);

      /* Search filter */
      var q = ($('#j-search').val() || '').toLowerCase();
      if (q) {
        indices = indices.filter(function(i) {
          var e = all[i];
          var text = ((e.date||'')+' '+(e.type||'')+' '+(e.comment||'')).toLowerCase();
          return text.indexOf(q) >= 0;
        });
      }

      /* Sort by date (parse "MM/DD/YYYY HH:MM" into comparable timestamps) */
      function _parseJDate(s) {
        var p = (s||'').split(' '), dp = (p[0]||'').split('/'), tp = (p[1]||'00:00').split(':');
        if (dp.length === 3) return new Date(dp[2], dp[0]-1, dp[1], tp[0]||0, tp[1]||0).getTime();
        return 0;
      }
      indices.sort(function(a, b) {
        var da = _parseJDate(all[a].date), db = _parseJDate(all[b].date);
        return Pages.journal._newestFirst ? db - da : da - db;
      });

      if (!indices.length) {
        $('#j-list').html('<div class="text-muted text-center">No matching entries.</div>');
        return;
      }

      var h = '';
      indices.forEach(function(i) {
        var e = all[i];
        var cmt = (e.comment||'').replace(/<br>/g, ' ');
        var hrs = e.hours ? ' &middot; ' + esc(String(e.hours)) + ' hrs' : '';
        h += '<div class="journal-entry">' +
          '<div class="journal-date">'+esc(e.date)+'</div>' +
          '<div class="journal-text"><strong>'+esc(e.type)+'</strong>' + hrs + '<br>'+esc(cmt)+'</div>' +
          '<div class="journal-actions">' +
          '<button class="btn btn-sm btn-outline j-edit" data-idx="'+i+'" title="Edit">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>' +
          '<path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>' +
          '<button class="btn btn-sm btn-danger j-del" data-idx="'+i+'" title="Delete">&times;</button></div></div>';
      });
      var $l = $('#j-list').html(h);
      $l.off('click','.j-del').on('click','.j-del', function() {
        var idx = $(this).data('idx');
        Modal.confirm('Delete','Delete this journal entry?', function() {
          API.set('delete_row_maint_log', idx).done(function(){
            API.get('get_maint_log_json').done(function(d){ Pages.journal._list(d); });
          });
        });
      });
      $l.off('click','.j-edit').on('click','.j-edit', function() {
        Pages.journal._editModal($(this).data('idx'));
      });
    },
    _editModal: function(idx) {
      var e = Pages.journal._data[idx];
      if (!e) return;
      /* parse "MM/DD/YYYY HH:MM" to datetime-local value */
      var parts = (e.date||'').split(' ');
      var dp = (parts[0]||'').split('/');
      var tp = (parts[1]||'00:00').split(':');
      var dtVal = '';
      if (dp.length === 3) {
        dtVal = dp[2]+'-'+dp[0].padStart(2,'0')+'-'+dp[1].padStart(2,'0')+'T'+
                (tp[0]||'00').padStart(2,'0')+':'+(tp[1]||'00').padStart(2,'0');
      }
      var calIcon = '<svg class="cal-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/>' +
        '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';
      var cmt = (e.comment||'').replace(/<br>/g, '\n');
      var body = '<div class="form-group"><label class="form-label">Date</label>' +
        '<div class="input-icon-wrap">' + calIcon +
        '<input class="form-input input-with-icon" type="datetime-local" id="je-date" value="'+esc(dtVal)+'"></div></div>' +
        '<div class="form-group"><label class="form-label">Type</label>' +
        '<select class="form-select" id="je-type">' +
        ['Maintenance','Repair','Check','Observation'].map(function(t){
          return '<option'+(t===e.type?' selected':'')+'>'+t+'</option>';
        }).join('') + '</select></div>' +
        '<div class="form-group"><label class="form-label">Engine Hours</label>' +
        '<input class="form-input" type="number" id="je-hours" min="0" step="0.1" value="'+esc(String(e.hours||0))+'"></div>' +
        '<div class="form-group"><label class="form-label">Comment</label>' +
        '<textarea class="form-textarea" id="je-cmt" rows="3">'+esc(cmt)+'</textarea></div>';
      Modal.show('Edit Journal Entry', Modal.html(body), [
        {text:'Cancel', action:'close'},
        {text:'Save', cls:'btn-primary', action:'save'}
      ]).onAction(function(a) {
        if (a !== 'save') return;
        var d = new Date($('#je-date').val());
        if (isNaN(d.getTime())) { Modal.alert('Error','Please enter a valid date.'); return; }
        var entry = {
          date: String(d.getMonth()+1).padStart(2,'0')+'/'+String(d.getDate()).padStart(2,'0')+'/'+
                d.getFullYear()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'),
          type: $('#je-type').val(),
          hours: parseFloat($('#je-hours').val()) || 0,
          comment: $('#je-cmt').val().replace(/\n/g, '<br>')
        };
        var obj = {}; obj[String(idx)] = entry;
        var payload = JSON.stringify(obj);
        Modal.close();
        API.set('edit_row_maint_log', payload).done(function() {
          API.get('get_maint_log_json').done(function(d){ Pages.journal._list(d); });
        }).fail(function(){ Modal.alert('Error','Failed to save entry.'); });
      });
    },
    update: function(d) { Pages.journal._list(d); }
  },

  /* ========== SETTINGS ========== */
  settings: {
    cmd: null,
    _advData: null,
    _notifData: null,
    /* Category mapping: field key → category id */
    _CAT_MAP: {
      sitename:'general', favicon:'general', fueltype:'general', tanksize:'general',
      nominalfrequency:'general', nominalkw:'general', nominalrpm:'general',
      smart_transfer_switch:'general', enhancedexercise:'general',
      http_user:'security', http_pass:'security', http_user_ro:'security', http_pass_ro:'security',
      http_port:'security',
      usehttps:'security', usemfa:'security', mfa_url:'security', mfa_enrolled:'security', email_configured:'security',
      remember_me_days:'security', mfa_trust_days:'security', mfa_trust_extend:'security',
      cert_mode:'security', cert_info:'security', certfile:'security', keyfile:'security',
      port:'comms', use_serial_tcp:'comms', serial_tcp_address:'comms',
      serial_tcp_port:'comms', modbus_tcp:'comms',
      disableweather:'weather', minimumweatherinfo:'weather', metricweather:'system',
      weatherkey:'weather', weatherlocation:'weather',
      incoming_mail_folder:'email', processed_mail_folder:'email',
      readonlyemailcommands:'email',
      autofeedback:'system', update_check:'system', synctime:'system',
      syncdst:'system', disableoutagecheck:'system', optimizeforslowercpu:'system',
      disablepowerlog:'system', displayunknown:'system'
    },
    _CATEGORIES: [
      { id:'general',  label:'General',        icon:'home' },
      { id:'security', label:'Security',       icon:'shield' },
      { id:'comms',    label:'Communication',  icon:'wifi' },
      { id:'email',    label:'Email',          icon:'mail' },
      { id:'weather',  label:'Weather',        icon:'cloud' },
      { id:'system',   label:'System',         icon:'cpu' }
    ],
    render: function($c) {
      $c.html('<div class="page-title">'+icon('settings')+' Settings</div>' +
        '<div id="set-wrap"><div class="text-muted text-center">Loading\u2026</div></div>');
      var self = this;
      API.get('settings', 12000).done(function(d){
        API.get('get_advanced_settings', 12000).done(function(adv){
          self._advData = adv;
          API.get('notifications', 12000).done(function(notif){
            self._notifData = notif;
            self._build(d);
          }).fail(function(){ self._notifData = null; self._build(d); });
        }).fail(function(){ self._advData = null; self._notifData = null; self._build(d); });
      });
    },
    _build: function(data) {
      if (!data) return;
      var self = Pages.settings;
      var CAT = self._CAT_MAP;
      var CATS = self._CATEGORIES;
      var devMode = Store.get('devMode', false);
      var showModbus = Store.get('showModbus', true);

      /* Dependent field rules: parent checkbox → child fields hidden when condition met.
         NOTE: 'disable*' keys are displayed INVERTED (checked = enabled).
         So 'when:true' means 'when the original config value is true (=disabled)',
         which in the inverted UI means 'when checkbox is UNchecked'. We flip the
         when value for inverted keys so the DOM check logic stays simple. */
      var DEPS = {
        disableweather:  { disables:['minimumweatherinfo','weatherkey','weatherlocation'], when:false },
        usehttps:        { disables:['cert_mode','certfile','keyfile','http_user','http_pass','http_user_ro','http_pass_ro','usemfa','mfa_url'], when:false },
        usemfa:          { disables:['mfa_url','mfa_trust_extend','mfa_trust_days'], when:false },
        mfa_trust_extend:{ disables:['mfa_trust_days'], when:false },
        use_serial_tcp:  { disables:['serial_tcp_address','serial_tcp_port','modbus_tcp'], when:false },
        disablesmtp:     { disables:['email_account','email_pw','sender_account','sender_name','smtp_server','smtp_port','ssl_enabled','tls_disable','smtpauth_disable'], when:false },
        disableimap:     { disables:['imap_server','readonlyemailcommands','incoming_mail_folder','processed_mail_folder'], when:false },
        disableoutagecheck: { disables:[], when:false },
        disablepowerlog:    { disables:[], when:false }
      };

      /* Email sub-section definitions */
      var EMAIL_SUBS = [
        { id:'email-smtp', toggle:'disablesmtp', label:'Outbound Email (SMTP)',
          icon:'upload',
          desc:'Configure an SMTP server to send email alerts and notifications.',
          fields:['email_account','email_pw','sender_account','sender_name','smtp_server','smtp_port','ssl_enabled','smtpauth_disable','tls_disable'] },
        { id:'email-imap', toggle:'disableimap', label:'Inbound Email Commands (IMAP)',
          icon:'download',
          desc:'Allow genmon to receive and process commands via email.',
          fields:['imap_server','readonlyemailcommands','incoming_mail_folder','processed_mail_folder'] }
      ];

      /* Security sub-section definitions */
      var SEC_SUBS = [
        { id:'sec-https',  parent:'usehttps', label:'HTTPS / SSL Encryption',
          icon:'lock',
          desc:'Encrypt all traffic between your browser and the server.',
          fields:['cert_mode','certfile','keyfile'] },
        { id:'sec-auth',   parent:'usehttps', label:'Password Authentication',
          icon:'user',
          desc:'Require a username and password to access the web interface. You can create a full-access admin account and an optional limited-rights account.',
          fields:['http_user','http_pass','http_user_ro','http_pass_ro'] },
        { id:'sec-session', parent:'usehttps', label:'Session & Remember Me',
          icon:'clock',
          desc:'Set how many days the browser remembers your login. Set to 0 for a browser-session only \u2014 you\u2019ll be logged out when you close the browser.',
          fields:['remember_me_days'] },
        { id:'sec-mfa',    parent:'usehttps', label:'Multi-Factor Authentication',
          icon:'shield',
          desc:'Add a second layer of security. After entering your password you\u2019ll need a code from an authenticator app (Google Authenticator, Authy, etc.). MFA applies to all accounts; passkeys and backup codes are admin-only.',
          fields:['usemfa','mfa_url','mfa_trust_extend','mfa_trust_days'] },
        { id:'sec-passkey', parent:'usehttps', label:'Passkeys',
          icon:'lock',
          desc:'Manage hardware security keys and biometric passkeys for passwordless login. Passkeys are only available for the admin account \u2014 the limited read-only account does not use MFA.',
          fields:[], custom: 'passkey' },
        { id:'sec-backup',  parent:'usehttps', label:'Backup Codes',
          icon:'archive',
          desc:'Generate single-use recovery codes in case you lose access to your authenticator. Backup codes are only for the admin account.',
          fields:[], custom: 'backup' }
      ];

      /* Bucket fields into categories */
      var buckets = {};
      CATS.forEach(function(c) { buckets[c.id] = []; });
      for (var k in data) {
        if (!data.hasOwnProperty(k)) continue;
        var def = data[k], section = def[7];
        var cat = (section === 'MyMail') ? 'email' : (CAT[k] || 'general');
        if (!buckets[cat]) buckets[cat] = [];
        buckets[cat].push({ key: k, def: def, order: def[2] || 0 });
      }
      for (var b in buckets) buckets[b].sort(function(a,b){ return a.order - b.order; });

      /* --- Top toolbar --- */
      var h = '<div class="set-toolbar">' +
        '<div class="set-search-wrap">' +
        btnIcon('search', 16) +
        '<input class="set-search-input" id="set-search" type="text" placeholder="Search settings\u2026"></div>' +
        '<button class="set-adv-btn'+(devMode?' set-adv-on':'')+' " id="set-adv-toggle">' +
        btnIcon('advanced', 14) + ' Advanced</button></div>';

      /* --- Category tabs (with icons) --- */
      h += '<div class="set-cats" id="set-cats">';
      CATS.forEach(function(c, i) {
        var cnt = buckets[c.id] ? buckets[c.id].length : 0;
        h += '<button class="set-cat'+(i===0?' active':'')+'" data-cat="'+c.id+'">' +
          icon(c.icon) + '<span class="set-cat-label">'+esc(c.label)+'</span>' +
          '<span class="set-cat-count">'+cnt+'</span></button>';
        if (c.id === 'email') {
          h += '<button class="set-cat" data-cat="__notifications__">' +
            icon('notifications') + '<span class="set-cat-label">Notifications</span></button>';
        }
      });
      /* Advanced & System Actions tabs (hidden unless dev mode) */
      h += '<button class="set-cat set-cat-adv'+(devMode?'':' hidden')+'" data-cat="__advanced__">' +
        icon('advanced') + '<span class="set-cat-label">Advanced</span></button>';
      h += '<button class="set-cat set-cat-adv'+(devMode?'':' hidden')+'" data-cat="__sysactions__">' +
        icon('power') + '<span class="set-cat-label">System</span></button>';
      h += '</div>';

      /* --- Setting panels --- */
      h += '<div id="set-panels">';
      CATS.forEach(function(c, i) {
        h += '<div class="set-panel'+(i===0?' active':'')+'" data-cat="'+c.id+'">';
        h += '<div class="set-panel-hdr">' +
          '<div class="set-panel-icon">'+icon(c.icon)+'</div>' +
          '<div><div class="set-panel-title">'+esc(c.label)+'</div>' +
          '<div class="set-panel-sub">'+buckets[c.id].length+' settings</div></div></div>';
        h += '<div class="set-panel-fields">';
        if (c.id === 'security') {
          /* --- Structured security panel --- */
          var secMap = {};
          (buckets[c.id] || []).forEach(function(s) { secMap[s.key] = s; });
          /* Port field */
          if (secMap['http_port']) h += UI.formField('http_port', secMap['http_port'].def, secMap['http_port'].def[3]);
          /* Master toggle: usehttps */
          if (secMap['usehttps']) h += UI.formField('usehttps', secMap['usehttps'].def, secMap['usehttps'].def[3]);
          h += '<div class="set-url-warn" id="sec-url-warn" style="display:none">' +
            '<strong>\u26A0 WARNING:</strong> After saving, your server address will change to:<br>' +
            '<span id="sec-new-url"></span><br>' +
            'The server will attempt to <strong>redirect you automatically</strong>. ' +
            'If the certificate is not yet trusted, you may need to navigate to the new address manually.</div>';
          h += '<div class="set-sec-hint" id="sec-off-hint">' +
            btnIcon('about',14) + ' Enable Webserver Security to configure HTTPS, password protection, and multi-factor authentication.</div>';
          /* Sub-sections */
          SEC_SUBS.forEach(function(sub) {
            h += '<div class="set-sec-group" id="'+sub.id+'">' +
              '<div class="set-sec-group-hdr">' + icon(sub.icon) +
              '<div><div class="set-sec-group-title">'+esc(sub.label)+'</div>' +
              '<div class="set-sec-group-desc">'+sub.desc+'</div></div></div>';
            h += '<div class="set-sec-group-fields">';
            if (sub.id === 'sec-mfa') {
              h += '<div class="set-sec-hint mfa-pending-hint" id="mfa-pending-hint" style="display:none">' +
                btnIcon('about',14) +
                ' Save and restart with HTTPS enabled first. ' +
                'You can configure MFA after the server is running securely.</div>';
              h += '<div class="set-sec-hint" id="mfa-auth-hint" style="display:none">' +
                btnIcon('about',14) +
                ' Set up a username and password first, save, and log in. ' +
                'You can enable MFA after password authentication is active.</div>';
            }
            sub.fields.forEach(function(fk) {
              if (!secMap[fk]) return;
              if (fk === 'cert_mode') {
                /* ─── Certificate mode radio-card selector ─── */
                var curMode = String(secMap[fk].def[3] || 'selfsigned');
                var certInfoRaw = secMap['cert_info'] ? secMap['cert_info'].def[3] : '{}';
                try { _certInfo = JSON.parse(certInfoRaw); } catch(e){ _certInfo = {}; }
                var certInfo = _certInfo;

                var modes = [
                  { val:'selfsigned', icon:'zap',    title:'Quick (Self-Signed)',
                    desc:'Works immediately with no setup.',
                    pro:'Zero config', con:'Browser warning on every visit' },
                  { val:'localca',    icon:'shield', title:'Trusted Local CA',
                    desc:'Generate a local CA you import into your browser once.',
                    pro:'No browser warnings', con:'One-time import per device' },
                  { val:'custom',     icon:'upload', title:'Your Own Certificate',
                    desc:'Use a certificate you obtained elsewhere.',
                    pro:'Full control', con:'Manual renewal required' }
                ];
                h += '<div class="form-group setting-field cert-mode-wrap">' +
                  '<input type="hidden" id="f_cert_mode" name="cert_mode" value="'+esc(curMode)+'">' +
                  '<div class="cert-mode-cards">';
                modes.forEach(function(m) {
                  var sel = m.val === curMode ? ' cert-mode-card-sel' : '';
                  h += '<div class="cert-mode-card'+sel+'" data-mode="'+m.val+'">' +
                    '<div class="cert-mode-card-hdr">' + icon(m.icon) +
                    '<span>'+esc(m.title)+'</span></div>' +
                    '<div class="cert-mode-card-desc">'+esc(m.desc)+'</div>' +
                    '<div class="cert-mode-badges">' +
                    '<span class="cert-badge cert-badge-pro">'+esc(m.pro)+'</span>' +
                    '<span class="cert-badge cert-badge-con">'+esc(m.con)+'</span>' +
                    '</div></div>';
                });
                h += '</div>'; /* .cert-mode-cards */

                /* Cert status info */
                h += '<div class="cert-status" id="cert-status">';
                if (curMode === 'selfsigned') {
                  h += '<div class="cert-status-line">' + icon('about') + ' Ephemeral certificate \u2014 regenerated on each restart. Browsers will show a security warning.</div>';
                } else if (curMode === 'localca') {
                  if (certInfo.ca_created) {
                    h += '<div class="cert-status-line">' + icon('check') + ' CA created: ' + esc(certInfo.ca_created) + '</div>';
                  }
                  if (certInfo.srv_expiry) {
                    h += '<div class="cert-status-line">' + icon('check') + ' Server cert expires: ' + esc(certInfo.srv_expiry) + '</div>';
                  }
                  if (certInfo.san) {
                    h += '<div class="cert-status-line">' + icon('about') + ' SAN: ' + esc(certInfo.san) + '</div>';
                  }
                } else if (curMode === 'custom') {
                  if (certInfo.expiry) {
                    h += '<div class="cert-status-line">' + icon('check') + ' Certificate expires: ' + esc(certInfo.expiry) + '</div>';
                  }
                }
                h += '</div>';

                /* Browser import wizard (localca only, shown when on HTTPS) */
                h += '<div class="cert-import-wizard" id="cert-import-wizard" style="display:none">' +
                  '<div class="cert-import-title">' + icon('download') + ' Import CA Certificate Into Your Browser</div>' +
                  '<div class="cert-step-warn" id="cert-save-first" style="display:none">' +
                    icon('warning') + ' The CA certificate has not been generated yet. ' +
                    '<strong>Save</strong> your settings and <strong>restart</strong> genmon first, ' +
                    'then return here to download and import the certificate.</div>' +
                  '<div class="cert-import-download" id="cert-dl-wrap">' +
                  '<button type="button" class="btn btn-sm" id="cert-dl-crt" onclick="_certDL(\'/download/ca.crt\',\'genmon-ca.crt\')">'+icon('download')+' Download Certificate</button>' +
                  '</div>' +

                  '<div id="cert-dl-status" style="display:none"></div>' +
                  '<div id="cert-pem-fallback" style="display:none">' +
                  '<p style="margin:.5em 0 .3em;font-size:.85rem;color:var(--text-muted)">Download blocked? Copy the PEM text below and save it as a <code>.crt</code> file:</p>' +
                  '<textarea id="cert-pem-text" readonly rows="6" style="width:100%;font-size:.75rem;font-family:monospace;background:var(--input-bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;resize:vertical"></textarea>' +
                  '<button type="button" class="btn btn-sm" style="margin-top:.4em" onclick="var t=document.getElementById(\'cert-pem-text\');t.select();document.execCommand(\'copy\')">'+icon('clipboard')+' Copy</button>' +
                  '</div>' +
                  '<div class="cert-import-tabs">' +
                  '<button type="button" class="cert-tab cert-tab-sel" data-tab="chrome">Windows (Chrome / Edge)</button>' +
                  '<button type="button" class="cert-tab" data-tab="firefox">Firefox</button>' +
                  '<button type="button" class="cert-tab" data-tab="safari">macOS (Safari / Chrome)</button>' +
                  '<button type="button" class="cert-tab" data-tab="ios">iOS</button>' +
                  '<button type="button" class="cert-tab" data-tab="android">Android</button>' +
                  '</div>' +
                  '<div class="cert-tab-content" data-for="chrome">' +
                  '<ol><li>Click <strong>Download Certificate</strong> above — a file named <code>genmon-ca.crt</code> will be saved to your Downloads folder.</li>' +
                  '<li>Open your Downloads folder and <strong>double-click</strong> <code>genmon-ca.crt</code>.</li>' +
                  '<li>Windows opens the <strong>Certificate Import Wizard</strong>. Choose <strong>Current User</strong>, click Next.</li>' +
                  '<li>Select <strong>\u201cPlace all certificates in the following store\u201d</strong>, then click <strong>Browse</strong>.</li>' +
                  '<li class="cert-step-warn">\u26a0\ufe0f <strong>Important:</strong> Do not use <em>Personal</em> or <em>Intermediate Certification Authorities</em> \u2014 neither will work!<br>Select <strong>Trusted Root Certification Authorities</strong> and click OK.</li>' +
                  '<li>Click Next \u2192 Finish \u2192 click <strong>Yes</strong> on the security prompt.</li>' +
                  '<li><strong>Close all Chrome windows</strong> completely (check the system tray too).</li>' +
                  '<li class="cert-step-warn">\u26a0\ufe0f If you visited this page <em>before</em> importing the certificate, Chrome remembers a past warning. ' +
                  'To clear it: click the <strong>Not secure</strong> badge \u2192 <strong>Site settings</strong> \u2192 <strong>Clear data</strong>, then close and reopen Chrome.</li>' +
                  '<li>Reopen Chrome and navigate to this page \u2014 you should see no security warnings.</li></ol>' +
                  '<p style="margin:.5em 0 0;font-size:.82rem;color:var(--text-muted)">To verify: <code>chrome://certificate-manager/</code> \u2192 Manage imported certificates from Windows.</p></div>' +
                  '<div class="cert-tab-content" data-for="firefox" style="display:none">' +
                  '<ol><li>Click this button \u2014 Firefox will open its import dialog directly:' +
                  '<div style="margin:.5em 0"><button type="button" class="btn btn-sm" onclick="window.open(\'/import/ca.crt\',\'_self\')">'+icon('shield')+' Import into Firefox</button></div></li>' +
                  '<li>Check <strong>\u201cTrust this CA to identify websites\u201d</strong> and click OK.</li>' +
                  '<li>Refresh this page \u2014 you should see no security warnings.</li></ol>' +
                  '<p style="margin:.5em 0 0;font-size:.82rem;color:var(--text-muted)">Firefox uses its own certificate store, separate from Windows.</p></div>' +
                  '<div class="cert-tab-content" data-for="safari" style="display:none">' +
                  '<ol><li>Click <strong>Download Certificate</strong> above to save the file.</li>' +
                  '<li>Open Finder, go to your Downloads folder, and double-click <code>genmon-ca.crt</code> \u2014 it opens in <strong>Keychain Access</strong>.</li>' +
                  '<li>In the list, find \u201cGenmon Local CA\u201d and double-click it.</li>' +
                  '<li>Expand the <strong>Trust</strong> section, set <strong>When using this certificate</strong> to <strong>Always Trust</strong>, then close the window and enter your macOS password to confirm.</li>' +
                  '<li>Quit and reopen your browser, then navigate to this page \u2014 you should see no security warnings.</li>' +
                  '<li style="font-size:.85rem;color:var(--text-muted)">Chrome on macOS also uses the Keychain, so this covers both Safari and Chrome.</li></ol></div>' +
                  '<div class="cert-tab-content" data-for="ios" style="display:none">' +
                  '<ol><li>Open this page on your iOS device and tap <strong>Download Certificate</strong> above.</li>' +
                  '<li>A prompt will say \u201cThis website is trying to download a configuration profile.\u201d Tap <strong>Allow</strong>.</li>' +
                  '<li>Go to <strong>Settings \u2192 General \u2192 VPN & Device Management</strong> \u2192 tap the downloaded profile \u2192 <strong>Install</strong>.</li>' +
                  '<li>Then go to <strong>Settings \u2192 General \u2192 About \u2192 Certificate Trust Settings</strong>.</li>' +
                  '<li>Enable the toggle for \u201cGenmon Local CA\u201d to grant full trust.</li>' +
                  '<li>Open Safari and navigate to this page \u2014 you should see no security warnings.</li></ol></div>' +
                  '<div class="cert-tab-content" data-for="android" style="display:none">' +
                  '<ol><li>Open this page on your Android device and tap <strong>Download Certificate</strong> above.</li>' +
                  '<li>If prompted, choose to download the file. Open your <strong>Downloads</strong> or <strong>Files</strong> app and tap <code>genmon-ca.crt</code>.</li>' +
                  '<li>Android opens the <strong>Install Certificate</strong> screen. If the file does not open automatically, go to <strong>Settings \u2192 Security \u2192 Encryption & credentials \u2192 Install a certificate \u2192 CA certificate</strong>.</li>' +
                  '<li>Tap <strong>Install anyway</strong> when warned about CA certificates.</li>' +
                  '<li>You may need to confirm with your PIN, pattern, or fingerprint.</li>' +
                  '<li>Open Chrome and navigate to this page \u2014 you should see no security warnings.</li></ol>' +
                  '<p style="margin:.5em 0 0;font-size:.82rem;color:var(--text-muted)">Path may vary by Android version and manufacturer. Look under Security, Biometrics, or Credentials in Settings.</p></div>' +
                  '</div>'; /* .cert-import-wizard */
                h += '</div>'; /* .cert-mode-wrap */
                return; /* skip default formField */
              }
              if (fk === 'mfa_url') {
                /* Special QR code field — two states: enrolled vs first-time setup */
                var url = secMap[fk].def[3] || '';
                var enrolled = secMap['mfa_enrolled'] && (secMap['mfa_enrolled'].def[3] === true || secMap['mfa_enrolled'].def[3] === 'True');
                var emailOk  = secMap['email_configured'] && (secMap['email_configured'].def[3] === true || secMap['email_configured'].def[3] === 'True');
                var isSecure = location.protocol === 'https:';

                h += '<div class="form-group setting-field" data-label="mfa qrcode" id="mfa-qr-wrap">' +
                  '<div class="mfa-qr-card">';

                if (enrolled && !url) {
                  /* ─── Already enrolled ─── */
                  h += '<div class="mfa-enrolled-status">' +
                    '<div class="mfa-enrolled-header">' +
                    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>' +
                    '<span>MFA is active</span></div>' +
                    '<div class="mfa-enrolled-hint">Your authenticator app is configured. The QR code is hidden for security.</div>';

                  /* Method status badges */
                  h += '<div class="mfa-methods">' +
                    '<div class="mfa-method mfa-method-ok">' +
                    '<span class="mfa-method-icon">\u2713</span>' +
                    '<div><strong>Authenticator App</strong><span class="mfa-method-note">Required \u2014 always active</span></div></div>';

                  h += '<div class="mfa-method ' + (emailOk ? 'mfa-method-ok' : 'mfa-method-off') + '">' +
                    '<span class="mfa-method-icon">' + (emailOk ? '\u2713' : '\u2014') + '</span>' +
                    '<div><strong>Email One-Time Code</strong>' +
                    '<span class="mfa-method-note">' +
                    (emailOk ? 'Available \u2014 send a code to your email at login'
                             : 'Not configured \u2014 set up email in the Communication tab to enable') +
                    '</span></div></div>';

                  if (isSecure) {
                    h += '<div class="mfa-method mfa-method-opt" id="mfa-badge-passkey">' +
                      '<span class="mfa-method-icon">\u2022</span>' +
                      '<div><strong>Passkeys</strong><span class="mfa-method-note">Available for admin account \u2014 manage in the Passkeys section below</span></div></div>' +
                      '<div class="mfa-method mfa-method-opt" id="mfa-badge-backup">' +
                      '<span class="mfa-method-icon">\u2022</span>' +
                      '<div><strong>Backup Codes</strong><span class="mfa-method-note">Available for admin account \u2014 generate in the Backup Codes section below</span></div></div>';
                  }
                  h += '</div>'; /* .mfa-methods */

                  h += '<div class="mfa-enrolled-reset-hint">' + icon('about') +
                    ' To reset your authenticator, disable MFA, save, then re-enable it. A new QR code will be generated automatically.</div>' +
                    '</div>'; /* .mfa-enrolled-status */

                } else if (url) {
                  /* ─── First-time setup / re-enrollment ─── */
                  h += '<div class="mfa-setup-intro">' +
                    '<div class="mfa-setup-intro-title">' + icon('shield') + ' Setting up Multi-Factor Authentication</div>' +
                    '<p>You\u2019ll need an authenticator app to get started. This is the only <strong>required</strong> step.</p>' +
                    '<div class="mfa-methods mfa-methods-preview">' +
                    '<div class="mfa-method mfa-method-req">' +
                    '<span class="mfa-method-icon">\u2022</span>' +
                    '<div><strong>Authenticator App</strong><span class="mfa-method-note">Required \u2014 Google Authenticator, Authy, Microsoft Authenticator, etc.</span></div></div>' +
                    '<div class="mfa-method ' + (emailOk ? 'mfa-method-opt' : 'mfa-method-off') + '">' +
                    '<span class="mfa-method-icon">\u2022</span>' +
                    '<div><strong>Email One-Time Code</strong><span class="mfa-method-note">' +
                    (emailOk ? 'Optional \u2014 email is configured, you can use it as a fallback at login'
                             : 'Unavailable \u2014 configure email in the Communication tab first') +
                    '</span></div></div>' +
                    '<div class="mfa-method ' + (isSecure ? 'mfa-method-opt' : 'mfa-method-off') + '">' +
                    '<span class="mfa-method-icon">\u2022</span>' +
                    '<div><strong>Passkeys</strong><span class="mfa-method-note">' +
                    (isSecure ? 'Optional \u2014 admin account only, configure after setup in the Passkeys section'
                              : 'Requires HTTPS') +
                    '</span></div></div>' +
                    '<div class="mfa-method ' + (isSecure ? 'mfa-method-opt' : 'mfa-method-off') + '">' +
                    '<span class="mfa-method-icon">\u2022</span>' +
                    '<div><strong>Backup Codes</strong><span class="mfa-method-note">' +
                    (isSecure ? 'Optional \u2014 admin account only, generate after setup in the Backup Codes section'
                              : 'Requires HTTPS') +
                    '</span></div></div>' +
                    '</div></div>';

                  h += '<div class="mfa-qr-header">' +
                    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                    '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>' +
                    '<rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>' +
                    '<span>Step 1 \u2014 Scan with your authenticator app</span></div>' +
                    '<div class="mfa-qr-frame"><div id="mfa-qr-target" data-qr="'+esc(url)+'"></div></div>' +
                    '<details class="mfa-qr-details"><summary>Can\u2019t scan? Copy the key</summary>' +
                    '<code class="mfa-qr-uri">'+esc(url)+'</code></details>' +
                    '<div class="mfa-verify-section">' +
                    '<div class="mfa-verify-header">Step 2 \u2014 Enter the code from your app to verify</div>' +
                    '<div class="mfa-verify-row">' +
                    '<input id="mfa-verify-code" type="text" maxlength="6" pattern="[0-9]*" inputmode="numeric" autocomplete="one-time-code" placeholder="000000" class="mfa-verify-input">' +
                    '<button type="button" id="mfa-verify-btn" class="mfa-verify-btn">Verify</button>' +
                    '</div>' +
                    '<div id="mfa-verify-status" class="mfa-verify-status"></div>' +
                    '</div>';

                } else {
                  h += '<div class="mfa-qr-hint">Enable HTTPS, save, and restart before configuring MFA. ' +
                    'The authenticator secret cannot be displayed over an unencrypted connection.</div>';
                }
                h += '</div></div>';
              } else {
                h += UI.formField(fk, secMap[fk].def, secMap[fk].def[3]);
              }
            });
            /* Custom UI for passkey management */
            if (sub.custom === 'passkey') {
              h += '<div id="passkey-manage">' +
                '<div id="passkey-list" class="passkey-list"><em>Loading\u2026</em></div>' +
                '<button type="button" class="btn btn-sm" id="passkey-register-btn">' + icon('plus') + ' Register New Passkey</button>' +
                '</div>';
            }
            /* Custom UI for backup code management */
            if (sub.custom === 'backup') {
              h += '<div id="backup-manage">' +
                '<div id="backup-status" class="backup-status"><em>Loading\u2026</em></div>' +
                '<button type="button" class="btn btn-sm" id="backup-generate-btn">' + icon('refresh') + ' Generate New Codes</button>' +
                '<div id="backup-codes-display" style="display:none">' +
                '<pre id="backup-codes-text" class="backup-codes-text"></pre>' +
                '<button type="button" class="btn btn-sm" id="backup-print-btn">Print</button>' +
                '</div>' +
                '</div>';
            }
            h += '</div></div>';
          });
        } else if (c.id === 'email') {
          /* --- Structured email panel --- */
          var emlMap = {};
          (buckets[c.id] || []).forEach(function(s) { emlMap[s.key] = s; });
          EMAIL_SUBS.forEach(function(sub) {
            /* Toggle field */
            if (emlMap[sub.toggle]) h += UI.formField(sub.toggle, emlMap[sub.toggle].def, emlMap[sub.toggle].def[3]);
            h += '<div class="set-sec-group" id="'+sub.id+'">' +
              '<div class="set-sec-group-hdr">' + icon(sub.icon) +
              '<div><div class="set-sec-group-title">'+esc(sub.label)+'</div>' +
              '<div class="set-sec-group-desc">'+sub.desc+'</div></div></div>';
            h += '<div class="set-sec-group-fields">';
            sub.fields.forEach(function(fk) {
              if (!emlMap[fk]) return;
              h += UI.formField(fk, emlMap[fk].def, emlMap[fk].def[3]);
            });
            h += '</div>';
            /* Test button for SMTP sub-section */
            if (sub.id === 'email-smtp') {
              h += '<button class="btn btn-outline btn-sm" id="test-email-btn" style="margin-top:10px">' +
                btnIcon('mail') + ' Test Sending Email</button>';
            }
            h += '</div>';
          });
        } else {
          (buckets[c.id] || []).forEach(function(s) { h += UI.formField(s.key, s.def, s.def[3]); });
        }
        /* Inject Modbus page toggle into General panel */
        if (c.id === 'general') {
          h += '<div class="form-group setting-field" data-label="show modbus page">' +
            '<div class="setting-toggle-row">' +
            '<label class="toggle"><input type="checkbox" id="set-modbus-toggle"' +
            (showModbus ? ' checked' : '') + '><span class="toggle-slider"></span></label>' +
            '<label class="setting-toggle-label" for="set-modbus-toggle">Show Modbus Page</label></div>' +
            '<div class="form-hint">Show the Modbus registers page in the navigation menu</div></div>';
        }
        /* Save bar at bottom of each category panel */
        h += '<div class="set-save-bar"><button class="btn btn-success set-save-cat">'+btnIcon('save')+' Save Settings</button></div>';
        h += '</div></div>';
      });

      /* --- Advanced settings panel (hidden unless dev mode) --- */
      var advData = self._advData;
      h += '<div class="set-panel set-panel-adv'+(devMode?'':' hidden')+'" data-cat="__advanced__">';
      h += '<div class="set-panel-hdr">' +
        '<div class="set-panel-icon">'+icon('advanced')+'</div>' +
        '<div><div class="set-panel-title">Advanced Settings</div>' +
        '<div class="set-panel-sub">For experienced users only</div></div></div>';
      h += '<div class="badge badge-warning mb-2">'+btnIcon('warning',14)+' Changing these settings may break your system. Proceed with caution.</div>';
      if (advData && typeof advData === 'object') {
        var advSorted = [];
        for (var ak in advData) { if (advData.hasOwnProperty(ak) && Array.isArray(advData[ak])) advSorted.push({key:ak, def:advData[ak], order:advData[ak][2]||0}); }
        advSorted.sort(function(a,b){return a.order-b.order;});
        h += '<div class="set-panel-fields" id="adv-form">';
        advSorted.forEach(function(s){ h += UI.formField(s.key, s.def, s.def[3]); });
        h += '</div>';
        h += '<div class="set-save-bar"><button class="btn btn-success" id="adv-save">'+btnIcon('save')+' Save Settings</button></div>';
      } else {
        h += '<div class="text-muted">No advanced settings available.</div>';
      }
      h += '</div>';

      /* --- System Actions panel (hidden unless dev mode) --- */
      h += '<div class="set-panel set-panel-adv'+(devMode?'':' hidden')+'" data-cat="__sysactions__">';
      h += '<div class="set-panel-hdr">' +
        '<div class="set-panel-icon">'+icon('power')+'</div>' +
        '<div><div class="set-panel-title">System Actions</div>' +
        '<div class="set-panel-sub">Control the running system</div></div></div>';
      h += '<div class="badge badge-warning mb-2">'+btnIcon('warning',14)+' These actions affect the running system.</div>';
      h += '<div class="btn-group flex-wrap" style="gap:8px;margin-top:12px">' +
        '<button class="btn btn-outline btn-sm" data-sys="restart">'+btnIcon('refresh')+' Restart Service</button>' +
        '<button class="btn btn-outline btn-sm" data-sys="stop">'+btnIcon('stop')+' Stop Service</button>' +
        '<button class="btn btn-danger btn-sm" data-sys="reboot">'+btnIcon('power')+' Reboot System</button>' +
        '<button class="btn btn-danger btn-sm" data-sys="shutdown">'+btnIcon('power')+' Shutdown System</button></div>';
      h += '</div>';

      /* --- Notifications panel --- */
      var NOTIF_CATS = ['outage','error','warn','info','software_update','fuel'];
      var NOTIF_CAT_LABELS = {outage:'Outage',error:'Error',warn:'Warning',info:'Info',software_update:'Updates',fuel:'Fuel'};
      var notifData = self._notifData;

      function _notifRecipientCard(r) {
        var c = '<div class="notif-card">' +
          '<div class="notif-card-top">' +
          '<input class="form-input n-email" type="email" name="notif_email" autocomplete="email" value="'+esc(r.email)+'" placeholder="email@example.com">' +
          '<button class="btn btn-sm btn-danger n-del" title="Remove">&times;</button></div>' +
          '<div class="notif-cats">';
        NOTIF_CATS.forEach(function(cat) {
          var checked = r.cats.indexOf(cat) >= 0 ? ' checked' : '';
          c += '<label class="notif-cat-label"><input type="checkbox" class="n-cat" data-cat="'+esc(cat)+'"'+checked+'>' +
            '<span class="notif-cat-chip">'+(NOTIF_CAT_LABELS[cat]||cat)+'</span></label>';
        });
        c += '</div></div>';
        return c;
      }

      h += '<div class="set-panel" data-cat="__notifications__">';
      h += '<div class="set-panel-hdr">' +
        '<div class="set-panel-icon">'+icon('notifications')+'</div>' +
        '<div><div class="set-panel-title">Notifications</div>' +
        '<div class="set-panel-sub">Email recipients &amp; categories</div></div></div>';
      h += '<div class="card"><div class="card-header">' + icon('mail') + ' Email Recipients</div><div class="card-body">';
      h += '<div id="notif-list" class="notif-list">';
      if (notifData) {
        var sorted = [];
        for (var nem in notifData) {
          if (!notifData.hasOwnProperty(nem)) continue;
          var nraw = notifData[nem][1];
          var ncats = (nraw && nraw.length) ? nraw.split(',') : NOTIF_CATS.slice();
          sorted.push({ email:nem, order:notifData[nem][0], cats:ncats });
        }
        sorted.sort(function(a,b){return a.order-b.order;});
        sorted.forEach(function(r) { h += _notifRecipientCard(r); });
      }
      h += '</div>' +
        '<div class="form-actions" style="border:none;margin-top:12px">' +
        '<button class="btn btn-sm btn-outline" id="n-add">'+btnIcon('plus')+' Add Recipient</button></div></div></div>';
      h += '<div class="set-save-bar"><button class="btn btn-success" id="n-save">'+btnIcon('save')+' Save Settings</button></div>';
      h += '</div>';
      h += '</div>'; /* close #set-panels */

      /* (global save bar removed — save button is now inside each tab panel) */

      var $w = $('#set-wrap').html(h);

      /* --- Tab switching (with dirty guard) --- */
      $w.on('click', '.set-cat', function() {
        var $btn = $(this);
        var cat = $btn.data('cat');
        var activeCat = $('.set-cat.active').data('cat');
        if (activeCat === cat) return;
        function doSwitch() {
          $('.set-cat').removeClass('active'); $btn.addClass('active');
          $('#set-search-results').hide();
          $('.set-panel').removeClass('active');
          $('.set-panel[data-cat="'+cat+'"]').addClass('active');
          $('#set-search').val('');
        }
        if (_isTabDirty(activeCat)) {
          Modal.confirm('Unsaved Changes',
            'You have unsaved changes. Leave without saving?',
            doSwitch);
          return;
        }
        doSwitch();
      });

      /* --- Search filter (improved: hides non-matching fields and empty panels) --- */
      $('#set-search').on('input', function() {
        var q = $(this).val().toLowerCase();
        if (!q) {
          /* Restore normal tab view */
          $('#set-panels .set-panel').removeClass('active set-search-mode');
          $('.setting-field').show();
          var active = $('.set-cat.active').data('cat');
          $('.set-panel[data-cat="'+active+'"]').addClass('active');
          $('#set-cats').show();
          return;
        }
        /* Hide category tabs, show all panels in search mode */
        $('#set-cats').hide();
        $('#set-panels .set-panel').each(function() {
          var $panel = $(this);
          /* Skip hidden panels (e.g. Advanced when dev mode is off) */
          if ($panel.hasClass('hidden')) { $panel.removeClass('active set-search-mode'); return; }
          var hasMatch = false;
          $panel.find('.setting-field').each(function() {
            var match = ($(this).data('label') || '').indexOf(q) >= 0;
            $(this).toggle(match);
            if (match) hasMatch = true;
          });
          $panel.toggleClass('active set-search-mode', hasMatch);
          if (!hasMatch) $panel.removeClass('active');
        });
      });

      /* --- Password toggle --- */
      $w.on('click', '.pw-toggle', function() {
        var $inp = $(this).prev('input');
        $inp.attr('type', $inp.attr('type') === 'password' ? 'text' : 'password');
      });

      /* --- Modbus menu toggle (inside General panel) --- */
      $w.on('change', '#set-modbus-toggle', function() {
        var on = $(this).is(':checked');
        Store.set('showModbus', on);
        Store._flush();
        Nav.build(S.startInfo ? S.startInfo.pages : null);
        Nav.setActive('settings');
      });

      /* --- Advanced mode toggle --- */
      $w.on('click', '#set-adv-toggle', function() {
        var $btn = $(this);
        if ($btn.hasClass('set-adv-on')) {
          Store.set('devMode', false);
          Store._flush();
          $btn.removeClass('set-adv-on');
          $('.set-cat-adv, .set-panel-adv').removeClass('active').addClass('hidden');
          var $first = $('.set-cat:not(.set-cat-adv)').first();
          $first.addClass('active');
          $('.set-panel[data-cat="'+$first.data('cat')+'"]').addClass('active');
        } else {
          Modal.confirm('Enable Advanced Settings',
            '<strong>'+btnIcon('warning',16)+' Warning:</strong> Advanced settings are intended for experienced users. ' +
            'Incorrect changes can break your system.<br><br>Enable Advanced Settings?',
            function() {
              Store.set('devMode', true);
              Store._flush();
              $btn.addClass('set-adv-on');
              $('.set-cat-adv, .set-panel-adv').removeClass('hidden');
            },
            function() { /* cancelled */ }
          );
        }
      });

      /* --- Dependent field hide/show logic --- */
      var _depsInitial = true;
      function applyDeps() {
        var dur = _depsInitial ? 0 : 250;
        for (var parent in DEPS) {
          if (!DEPS.hasOwnProperty(parent)) continue;
          var rule = DEPS[parent];
          var $cb = $w.find('#f_'+parent);
          if (!$cb.length) continue;
          var checked = $cb.is(':checked');
          var shouldHide = (rule.when === true && checked) || (rule.when === false && !checked);
          rule.disables.forEach(function(child) {
            var $field = $w.find('#f_'+child).closest('.setting-field');
            if (shouldHide) {
              dur ? $field.slideUp(dur) : $field.hide();
            } else {
              dur ? $field.slideDown(dur) : $field.show();
            }
          });
        }
        _depsInitial = false;
      }
      /* Bind change events on parent checkboxes */
      for (var dep in DEPS) {
        if (DEPS.hasOwnProperty(dep)) {
          $w.on('change', '#f_'+dep, applyDeps);
        }
      }
      applyDeps(); /* initial state */

      /* --- Security sub-section visibility cascade --- */
      /* Remember the saved values so we can detect changes */
      var _origHttps = $w.find('#f_usehttps').is(':checked');
      var _origPort  = $w.find('#f_http_port').val() || '80';
      var _origMfa   = $w.find('#f_usemfa').is(':checked');
      var _origUser  = ($w.find('[name=http_user]').val() || '').trim();
      /* Track whether MFA is already enrolled (QR hidden for security) */
      var _mfaEnrolled = !!$w.find('.mfa-enrolled-status').length;
      /* MFA verification gate: true when we are confident the user has a
         working authenticator (already enabled, or just verified a code). */
      var _mfaVerified = _origMfa || _mfaEnrolled;
      var _secInitial = true;
      var _certInfo = {};
      function applySecVis() {
        var dur = _secInitial ? 0 : 250;
        var httpsOn = $w.find('#f_usehttps').is(':checked');
        /* Port: hide when HTTPS on (backend ignores it) */
        _secSlide($w.find('#f_http_port').closest('.setting-field'), !httpsOn, dur);
        /* Show/hide hint + sub-sections */
        _secSlide($w.find('#sec-off-hint'), !httpsOn, dur);
        $w.find('.set-sec-group').each(function(){ _secSlide($(this), httpsOn, dur); });
        /* Self-signed cert → own cert fields */
        var certMode = $w.find('#f_cert_mode').val() || 'selfsigned';
        $w.find('#f_certfile, #f_keyfile').closest('.setting-field').each(function(){
          _secSlide($(this), httpsOn && certMode === 'custom', dur);
        });
        /* Browser import wizard: visible when localca selected + HTTPS on */
        _secSlide($w.find('#cert-import-wizard'), httpsOn && certMode === 'localca', dur);
        /* If CA cert doesn't exist yet, show 'save first' banner and hide download + tabs.
           If we're already browsing over HTTPS the cert must exist even if cert_info
           isn't populated (e.g. genserv.py hasn't been updated yet). */
        var caReady = !!(_certInfo && _certInfo.ca_created) || location.protocol === 'https:';
        if (httpsOn && certMode === 'localca') {
          $w.find('#cert-save-first')[caReady ? 'hide' : 'show']();
          $w.find('#cert-dl-wrap')[caReady ? 'show' : 'hide']();
          $w.find('.cert-import-tabs, .cert-import-body')[caReady ? 'show' : 'hide']();
          $w.find('#cert-dl-crt').prop('disabled', !caReady);
        }
        /* Cert status: update content + visibility per selected mode */
        var $certStatus = $w.find('#cert-status');
        if (httpsOn) {
          var ci = _certInfo || {};
          var sh = '';
          if (certMode === 'selfsigned') {
            sh = '<div class="cert-status-line">' + icon('about') + ' Ephemeral certificate \u2014 regenerated on each restart. Browsers will show a security warning.</div>';
          } else if (certMode === 'localca') {
            if (ci.mode === 'localca') {
              if (ci.ca_created) sh += '<div class="cert-status-line">' + icon('check') + ' CA created: ' + esc(ci.ca_created) + '</div>';
              if (ci.srv_expiry) sh += '<div class="cert-status-line">' + icon('check') + ' Server cert expires: ' + esc(ci.srv_expiry) + '</div>';
              if (ci.san) sh += '<div class="cert-status-line">' + icon('about') + ' SAN: ' + esc(ci.san) + '</div>';
            }
            if (!sh && location.protocol === 'https:')
              sh = '<div class="cert-status-line">' + icon('check') + ' Local CA is active. Download the certificate below to import it into your browser.</div>';
            if (!sh) sh = '<div class="cert-status-line">' + icon('about') + ' Local CA will be generated when you save and restart.</div>';
          } else if (certMode === 'custom') {
            if (ci.mode === 'custom' && ci.expiry) {
              sh = '<div class="cert-status-line">' + icon('check') + ' Certificate expires: ' + esc(ci.expiry) + '</div>';
            } else {
              sh = '<div class="cert-status-line">' + icon('about') + ' Provide your certificate and key file paths below.</div>';
            }
          }
          $certStatus.html(sh);
        }
        _secSlide($certStatus, httpsOn, dur);
        /* MFA: requires HTTPS running + password auth already active.
           Disable the toggle and show a hint when prerequisites aren't met. */
        var hasQrData = !!$w.find('#mfa-qr-target').attr('data-qr');
        var $mfaCb   = $w.find('#f_usemfa');
        var authActive = !!_origUser; /* password auth was active when page loaded */
        var mfaReady = httpsOn && (hasQrData || _mfaEnrolled) && authActive;
        /* Pending hint: HTTPS enabled in form but server not yet running HTTPS */
        _secSlide($w.find('#mfa-pending-hint'), httpsOn && !hasQrData && !_mfaEnrolled, dur);
        /* Auth hint: HTTPS is live but no password auth configured/active yet */
        _secSlide($w.find('#mfa-auth-hint'), httpsOn && (hasQrData || _mfaEnrolled) && !authActive, dur);
        if (!mfaReady) {
          $mfaCb.prop('disabled', true).prop('checked', false);
          $mfaCb.closest('.setting-field').css('opacity', '.45');
        } else {
          $mfaCb.prop('disabled', false);
          $mfaCb.closest('.setting-field').css('opacity', '');
        }
        /* MFA QR + verify visible only when MFA on AND server is actually HTTPS */
        var mfaOn = $mfaCb.is(':checked');
        _secSlide($w.find('#mfa-qr-wrap'), mfaReady && mfaOn, dur);
        /* Passkeys & backup codes: only available on a live HTTPS connection with MFA on */
        var isSecure = location.protocol === 'https:';
        _secSlide($w.find('#sec-passkey'), isSecure && httpsOn && mfaOn, dur);
        _secSlide($w.find('#sec-backup'), isSecure && httpsOn && mfaOn, dur);
        _secSlide($w.find('#sec-session'), httpsOn, dur);
        /* Reset verification when MFA is freshly toggled on */
        if (mfaOn && !_origMfa && !_mfaEnrolled) {
          _mfaVerified = false;
          $w.find('#mfa-verify-status').empty();
        } else if (!mfaOn) {
          _mfaVerified = true; /* disabling MFA — no gate needed */
        }
        /* URL change warning */
        var curPort = httpsOn ? '443' : ($w.find('#f_http_port').val() || '80');
        var changed = (httpsOn !== _origHttps) || (!httpsOn && curPort !== _origPort);
        if (changed) {
          var proto = httpsOn ? 'https' : 'http';
          var host = location.hostname;
          var port = (!httpsOn && curPort !== '80') ? ':' + curPort : '';
          $w.find('#sec-new-url').text(proto + '://' + host + port + location.pathname);
        }
        _secSlide($w.find('#sec-url-warn'), changed, dur);
        _secInitial = false;
      }
      function _secSlide($el, show, dur) {
        if (show) { dur ? $el.slideDown(dur) : $el.show(); }
        else      { dur ? $el.slideUp(dur)   : $el.hide(); }
      }
      $w.on('change', '#f_usehttps, #f_cert_mode, #f_usemfa, #f_http_port', applySecVis);
      $w.on('input', '#f_http_port', applySecVis);

      /* --- Auth field coupling --- */
      /* Clearing the username clears password + disables MFA */
      $w.on('input', '[name=http_user]', function() {
        var u = $(this).val().trim();
        if (!u) {
          $w.find('[name=http_pass]').val('');
          var $mfa = $w.find('#f_usemfa');
          if ($mfa.is(':checked')) { $mfa.prop('checked', false).trigger('change'); }
        }
      });
      /* Same for read-only user */
      $w.on('input', '[name=http_user_ro]', function() {
        if (!$(this).val().trim()) {
          $w.find('[name=http_pass_ro]').val('');
        }
      });
      /* Cert mode card selection */
      $w.on('click', '.cert-mode-card', function() {
        var mode = $(this).data('mode');
        $w.find('.cert-mode-card').removeClass('cert-mode-card-sel');
        $(this).addClass('cert-mode-card-sel');
        $w.find('#f_cert_mode').val(mode).trigger('change');
      });
      /* Cert import wizard tabs */
      $w.on('click', '.cert-tab', function() {
        var tab = $(this).data('tab');
        $(this).closest('.cert-import-wizard').find('.cert-tab').removeClass('cert-tab-sel');
        $(this).addClass('cert-tab-sel');
        $(this).closest('.cert-import-wizard').find('.cert-tab-content').hide()
          .filter('[data-for="'+tab+'"]').show();
      });
      applySecVis();

      /* --- Dot-style QR code renderer --- */
      function _dotQR($el, text, sz) {
        if (!$.fn.qrcode) return;
        /* Render with plugin on a hidden 1024px canvas to extract module grid */
        var $t = $('<div>').css({position:'fixed',left:'-9999px'}).appendTo('body');
        $t.qrcode({width:1024, height:1024, text:text});
        var src = $t.find('canvas')[0];
        if (!src) { $t.remove(); return; }
        var pix = src.getContext('2d').getImageData(0,0,1024,1024).data;
        /* Detect module size from row 0: first 7 modules are dark (finder pattern) */
        var fp = 0;
        for (var i=0; i<1024; i++) { if (pix[i*4]>128) { fp=i; break; } }
        if (!fp) {
          /* Quiet-zone or unexpected layout — fall back to plain plugin QR */
          var fallback = $t.find('canvas')[0];
          if (fallback) {
            fallback.style.width = sz + 'px';
            fallback.style.height = sz + 'px';
            fallback.style.borderRadius = '12px';
            $el.empty().append(fallback);
          }
          $t.remove(); return;
        }
        var ms = fp/7, mc = Math.round(1024/ms);
        /* Build boolean grid */
        var g = [];
        for (var r=0; r<mc; r++) { g[r]=[]; for (var c=0; c<mc; c++) {
          var px=Math.floor((c+.5)*ms), py=Math.floor((r+.5)*ms);
          g[r][c] = pix[(py*1024+px)*4] < 128;
        }}
        $t.remove();

        /* Create HiDPI canvas */
        var dpr = Math.min(window.devicePixelRatio||1, 3);
        var pad = 12;
        var full = sz + pad*2;
        var cv = document.createElement('canvas');
        cv.width = full*dpr; cv.height = full*dpr;
        cv.style.width = full+'px'; cv.style.height = full+'px';
        var ctx = cv.getContext('2d'); ctx.scale(dpr,dpr);

        /* Theme palette — always dark-on-light for scanner compatibility */
        var dk = document.documentElement.getAttribute('data-theme')==='dark';
        var bg  = dk ? '#d6dded' : '#f0f4fa';
        var dot = dk ? '#16203a' : '#1a2640';
        var acc = dk ? '#4f8ffa' : '#3b82f6';

        /* Rounded rect helper with fallback */
        function rr(x,y,w,h,rd) {
          ctx.beginPath();
          if (ctx.roundRect) { ctx.roundRect(x,y,w,h,rd); }
          else { ctx.moveTo(x+rd,y); ctx.lineTo(x+w-rd,y); ctx.arcTo(x+w,y,x+w,y+rd,rd);
            ctx.lineTo(x+w,y+h-rd); ctx.arcTo(x+w,y+h,x+w-rd,y+h,rd);
            ctx.lineTo(x+rd,y+h); ctx.arcTo(x,y+h,x,y+h-rd,rd);
            ctx.lineTo(x,y+rd); ctx.arcTo(x,y,x+rd,y,rd); ctx.closePath(); }
        }

        /* Background */
        ctx.fillStyle = bg; rr(0,0,full,full,12); ctx.fill();

        var cs = sz/mc; /* cell size */
        function isFP(r,c) { return (r<7&&c<7) || (r<7&&c>=mc-7) || (r>=mc-7&&c<7); }

        /* Data modules as dots */
        var dr = cs * 0.34;
        for (var r=0; r<mc; r++) for (var c=0; c<mc; c++) {
          if (!g[r][c] || isFP(r,c)) continue;
          ctx.fillStyle = dot;
          ctx.beginPath();
          ctx.arc(pad+(c+.5)*cs, pad+(r+.5)*cs, dr, 0, Math.PI*2);
          ctx.fill();
        }

        /* Finder patterns — rounded concentric squares in accent colour */
        function drawFP(fr,fc) {
          var x=pad+fc*cs, y=pad+fr*cs, rd=cs*.9;
          ctx.fillStyle = acc; rr(x,y,cs*7,cs*7,rd);           ctx.fill();
          ctx.fillStyle = bg;  rr(x+cs,y+cs,cs*5,cs*5,rd*.55); ctx.fill();
          ctx.fillStyle = acc; rr(x+cs*2,y+cs*2,cs*3,cs*3,rd*.45); ctx.fill();
        }
        drawFP(0,0); drawFP(0,mc-7); drawFP(mc-7,0);

        $el.empty().append(cv);
      }

      var _qrRendered = false;
      function renderMfaQr() {
        if (_qrRendered) return;
        var $wrap = $w.find('#mfa-qr-wrap');
        if (!$wrap.length) return;
        var $target = $wrap.find('#mfa-qr-target');
        if (!$target.length) return;
        var url = $target.attr('data-qr');
        if (!url || !$.fn.qrcode) return;
        _dotQR($target, url, 196);
        _qrRendered = true;
      }
      renderMfaQr();
      /* Re-attempt QR render each time the MFA section becomes visible */
      $w.on('change', '#f_usemfa, #f_usehttps', function() {
        setTimeout(renderMfaQr, 50);
      });

      /* --- Client-side TOTP verifier (Web Crypto API) --- */
      function _b32decode(s) {
        var alpha = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
        s = s.replace(/[\s=-]+/g, '').toUpperCase();
        var bits = '', bytes = [];
        for (var i = 0; i < s.length; i++) {
          var v = alpha.indexOf(s[i]); if (v < 0) continue;
          bits += ('00000' + v.toString(2)).slice(-5);
        }
        for (var i = 0; i + 8 <= bits.length; i += 8)
          bytes.push(parseInt(bits.substr(i, 8), 2));
        return new Uint8Array(bytes);
      }
      function _verifyTOTP(secret, code) {
        /* Returns a Promise<boolean>. Checks current ±1 time steps. */
        var keyBytes = _b32decode(secret);
        return crypto.subtle.importKey('raw', keyBytes, {name:'HMAC',hash:'SHA-1'}, false, ['sign'])
          .then(function(key) {
            var now = Math.floor(Date.now() / 1000);
            var checks = [-1, 0, 1].map(function(offset) {
              var counter = Math.floor(now / 30) + offset;
              var buf = new ArrayBuffer(8);
              var dv = new DataView(buf);
              dv.setUint32(0, Math.floor(counter / 0x100000000), false);
              dv.setUint32(4, counter >>> 0, false);
              return crypto.subtle.sign('HMAC', key, buf).then(function(sig) {
                var h = new Uint8Array(sig);
                var o = h[h.length - 1] & 0x0f;
                var otp = ((h[o]&0x7f)<<24 | h[o+1]<<16 | h[o+2]<<8 | h[o+3]) % 1000000;
                return ('000000' + otp).slice(-6);
              });
            });
            return Promise.all(checks).then(function(codes) {
              return codes.indexOf(code) !== -1;
            });
          });
      }
      /* Verify button handler — calls server to verify AND set enrolled flag */
      $w.on('click', '#mfa-verify-btn', function() {
        var code = ($w.find('#mfa-verify-code').val() || '').replace(/\s/g, '');
        var $status = $w.find('#mfa-verify-status');
        if (code.length !== 6 || !/^\d{6}$/.test(code)) {
          $status.html('<span class="mfa-verify-fail">\u2717 Enter a 6-digit code</span>');
          return;
        }
        var $btn = $w.find('#mfa-verify-btn').prop('disabled', true);
        $.ajax({ url:'/mfa/verify_setup', method:'POST',
          contentType:'application/json', data:JSON.stringify({code:code})
        }).done(function(r) {
          if (r.status === 'ok') {
            _mfaVerified = true;
            _mfaEnrolled = true;
            $status.html('<span class="mfa-verify-ok">\u2713 Authenticator verified \u2014 you can now save.</span>');
          } else {
            $status.html('<span class="mfa-verify-fail">\u2717 ' + esc(r.msg || 'Verification failed') + '</span>');
          }
        }).fail(function() {
          $status.html('<span class="mfa-verify-fail">\u2717 Server error during verification.</span>');
        }).always(function() { $btn.prop('disabled', false); });
      });
      /* Also verify on Enter key in the input */
      $w.on('keydown', '#mfa-verify-code', function(e) {
        if (e.which === 13) { e.preventDefault(); $w.find('#mfa-verify-btn').click(); }
      });

      /* --- Email sub-section visibility cascade --- */
      var _emlInitial = true;
      function applyEmailVis() {
        var dur = _emlInitial ? 0 : 250;
        EMAIL_SUBS.forEach(function(sub) {
          /* Inverted toggles: checked = enabled */
          var enabled = $w.find('#f_'+sub.toggle).is(':checked');
          var $grp = $w.find('#'+sub.id);
          if (enabled) { dur ? $grp.slideDown(dur) : $grp.show(); }
          else         { dur ? $grp.slideUp(dur)   : $grp.hide(); }
          if (sub.id === 'email-smtp') {
            var $btn = $w.find('#test-email-btn');
            if (enabled) { dur ? $btn.slideDown(dur) : $btn.show(); }
            else         { dur ? $btn.slideUp(dur)   : $btn.hide(); }
          }
        });
        _emlInitial = false;
      }
      $w.on('change', '#f_disablesmtp, #f_disableimap', applyEmailVis);
      applyEmailVis();

      /* --- Passkey management --- */
      function loadPasskeys() {
        var $list = $w.find('#passkey-list');
        if (!$list.length) return;
        $.getJSON('/passkey/list').done(function(d) {
          if (!d.passkeys || !d.passkeys.length) {
            $list.html('<em>No passkeys registered.</em>');
            return;
          }
          var $badge = $w.find('#mfa-badge-passkey');
          if ($badge.length) { $badge.removeClass('mfa-method-opt').addClass('mfa-method-ok').find('.mfa-method-icon').text('\u2713'); }
          var html = '';
          d.passkeys.forEach(function(pk) {
            html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:.35rem 0">' +
              '<span>' + esc(pk.name) + '</span>' +
              '<button type="button" class="btn btn-sm btn-danger passkey-del" style="margin-left:1rem" data-id="' + esc(pk.credential_id) + '">Delete</button></div>';
          });
          $list.html(html);
        }).fail(function() { $list.html('<em>Could not load passkeys.</em>'); });
      }
      if (_origMfa || _mfaEnrolled) { loadPasskeys(); }
      $w.on('click', '#passkey-register-btn', function() {
        var btn = this; btn.disabled = true;
        var h = location.hostname;
        if (/^\d{1,3}(\.\d{1,3}){3}$/.test(h) || h.indexOf(':') !== -1) {
          alert('Passkeys require a hostname (e.g. https://generac), not an IP address (' + h + '). Add a DNS or hosts entry for your generator.');
          btn.disabled = false; return;
        }
        $.post('/passkey/register/begin').done(function(opts) {
          if (opts.error) { alert(opts.error); btn.disabled = false; return; }
          opts.challenge = _pk_b64toAB(opts.challenge);
          opts.user.id = _pk_b64toAB(opts.user.id);
          if (opts.excludeCredentials) opts.excludeCredentials.forEach(function(c){ c.id = _pk_b64toAB(c.id); });
          navigator.credentials.create({publicKey: opts}).then(function(cred) {
            var body = JSON.stringify({
              id: cred.id,
              rawId: _pk_ABtob64(cred.rawId),
              response: {
                attestationObject: _pk_ABtob64(cred.response.attestationObject),
                clientDataJSON: _pk_ABtob64(cred.response.clientDataJSON)
              },
              type: cred.type,
              name: 'Passkey ' + (new Date()).toLocaleDateString()
            });
            return $.ajax({url:'/passkey/register/complete', method:'POST', contentType:'application/json', data:body});
          }).then(function(d) {
            if (d.status === 'ok') { loadPasskeys(); }
            else alert(d.error || 'Registration failed');
            btn.disabled = false;
          })['catch'](function(e) { console.error(e); btn.disabled = false; });
        }).fail(function() { alert('Failed to start registration'); btn.disabled = false; });
      });
      $w.on('click', '.passkey-del', function() {
        var credId = $(this).data('id');
        Modal.confirm('Delete Passkey', 'Remove this passkey?', function() {
          $.ajax({url:'/passkey/delete', method:'POST', contentType:'application/json',
            data: JSON.stringify({credential_id: credId})
          }).done(function() { loadPasskeys(); });
        });
      });
      function _pk_b64toAB(b64){var s=atob(b64.replace(/-/g,'+').replace(/_/g,'/'));var a=new Uint8Array(s.length);for(var i=0;i<s.length;i++)a[i]=s.charCodeAt(i);return a.buffer;}
      function _pk_ABtob64(buf){var s='';var a=new Uint8Array(buf);for(var i=0;i<a.length;i++)s+=String.fromCharCode(a[i]);return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}

      /* --- Backup code management --- */
      function loadBackupStatus() {
        var $s = $w.find('#backup-status');
        if (!$s.length) return;
        $.getJSON('/backup_codes/count').done(function(d) {
          if (d.count > 0) {
            $s.html('You have <strong>' + d.count + '</strong> backup codes remaining.');
            var $badge = $w.find('#mfa-badge-backup');
            if ($badge.length) { $badge.removeClass('mfa-method-opt').addClass('mfa-method-ok').find('.mfa-method-icon').text('\u2713'); }
          } else $s.html('<em>No backup codes generated yet.</em>');
        }).fail(function() { $s.html('<em>Could not load backup code status.</em>'); });
      }
      if (_origMfa || _mfaEnrolled) { loadBackupStatus(); }
      $w.on('click', '#backup-generate-btn', function() {
        Modal.confirm('Generate Backup Codes', 'This will replace any existing codes. Continue?', function() {
          $.post('/backup_codes/generate').done(function(d) {
            if (d.status === 'ok') {
              var txt = 'Genmon Backup Codes\n' + '='.repeat(30) + '\n\n';
              d.codes.forEach(function(c, i) { txt += (i+1) + '. ' + c + '\n'; });
              txt += '\nStore these codes in a safe place.\nEach code can only be used once.';
              $w.find('#backup-codes-text').text(txt);
              $w.find('#backup-codes-display').slideDown(200);
              loadBackupStatus();
            }
          });
        });
      });
      $w.on('click', '#backup-print-btn', function() {
        var txt = $w.find('#backup-codes-text').text();
        var win = window.open('', '_blank');
        win.document.write('<html><head><title>Genmon Backup Codes</title></head><body><pre>' + esc(txt) + '</pre></body></html>');
        win.document.close();
        win.print();
      });

      /* --- Serial/TCP port field hide --- */
      var _commsInitial = true;
      function applyCommsVis() {
        var dur = _commsInitial ? 0 : 250;
        var tcpOn = $w.find('#f_use_serial_tcp').is(':checked');
        var $port = $w.find('#f_port').closest('.setting-field');
        if (tcpOn) { dur ? $port.slideUp(dur) : $port.hide(); }
        else       { dur ? $port.slideDown(dur) : $port.show(); }
        _commsInitial = false;
      }
      $w.on('change', '#f_use_serial_tcp', applyCommsVis);
      applyCommsVis();

      /* --- Test Email button --- */
      $w.on('click', '#test-email-btn', function(e) {
        e.preventDefault();
        var acct = $w.find('#f_email_account').val() || '';
        Modal.prompt('Test Sending Email', 'Enter recipient email address:', acct, function(to) {
          if (!to) return;
          var payload = JSON.stringify({
            smtp_server:     $w.find('#f_smtp_server').val(),
            smtp_port:       parseInt($w.find('#f_smtp_port').val(), 10) || 587,
            email_account:   $w.find('#f_email_account').val(),
            sender_account:  $w.find('#f_sender_account').val(),
            sender_name:     $w.find('#f_sender_name').val(),
            recipient:       to,
            password:        $w.find('#f_email_pw').val(),
            use_ssl:        ($w.find('#f_ssl_enabled').is(':checked')),
            tls_disable:    ($w.find('#f_tls_disable').is(':checked')),
            smtpauth_disable:($w.find('#f_smtpauth_disable').is(':checked'))
          });
          API.get('test_email?test_email=' + encodeURIComponent(payload), 15000)
            .done(function(r) {
              if (r && r.error) Modal.alert('Test Email', r.error);
              else Modal.alert('Test Email', (r && r.message) || 'Test email sent successfully.');
            })
            .fail(function()  { Modal.alert('Test Email', 'Failed to send test email.'); });
        });
      });

      /* --- System action buttons --- */
      $w.on('click', '[data-sys]', function() {
        var cmd = $(this).data('sys');
        Modal.confirm('System', 'Execute: ' + cmd + '?', function() {
          API.get(cmd, 30000).done(function() {
            if (cmd === 'restart') {
              Modal.restart('Service is restarting…');
            } else {
              Modal.alert('OK', cmd + ' initiated.');
            }
          });
        });
      });

      /* --- Live bounds validation on settings inputs --- */
      UI.bindBoundsValidation($w);

      /* --- Save settings (button inside each tab) --- */
      $w.on('click', '.set-save-cat', function() {
        /* --- Auth field validation --- */
        var user = ($w.find('[name=http_user]').val() || '').trim();
        var pass = ($w.find('[name=http_pass]').val() || '').trim();
        var userRo = ($w.find('[name=http_user_ro]').val() || '').trim();
        var passRo = ($w.find('[name=http_pass_ro]').val() || '').trim();
        var mfaOn = $w.find('#f_usemfa').is(':checked');

        if (user && !pass) {
          Modal.alert('Password Required',
            'You have a username set but no password. Please enter a password or clear the username.');
          return;
        }
        if (userRo && !passRo) {
          Modal.alert('Password Required',
            'The read-only account has a username but no password. Please enter a password or clear the username.');
          return;
        }
        if (mfaOn && (!user || !pass)) {
          Modal.alert('Password Required for MFA',
            'Multi-factor authentication requires a username and password. ' +
            'Please set up password authentication before enabling MFA.');
          $w.find('#f_usemfa').prop('checked', false).trigger('change');
          return;
        }

        /* Block save if MFA is being newly enabled but not yet verified */
        if (mfaOn && !_mfaVerified) {
          Modal.alert('MFA Not Verified',
            'Please scan the QR code with your authenticator app and verify a code ' +
            'before saving. This prevents being locked out of your server.');
          return;
        }
        var val = UI.collectForm('#set-panels .set-panel:not([data-cat^="__"])');
        /* Detect if the server URL will change (HTTPS toggle or port) */
        var httpsOn = $('#f_usehttps').is(':checked');
        var httpPort = $('#f_http_port').val() || '80';
        var curHttps = location.protocol === 'https:';
        var curPort = location.port || (curHttps ? '443' : '80');
        /* HTTPS always runs on 443; the http_port field is only for plain HTTP */
        var newPort = httpsOn ? '443' : httpPort;
        var urlChanged = (httpsOn !== curHttps) || (newPort !== curPort);
        var newUrl = null;
        if (urlChanged) {
          var proto = httpsOn ? 'https' : 'http';
          var host = location.hostname;
          var portSuffix = (httpsOn || newPort === '80') ? '' : ':' + newPort;
          newUrl = proto + '://' + host + portSuffix + '/';
        }
        Modal.restart('Settings saved. Service is restarting\u2026', newUrl);
        $.ajax({ url: CFG.baseUrl + 'setsettings',
          data: { setsettings: val },
          dataType:'text', timeout:12000, cache:false
        });
        CATS.forEach(function(c) { _tabSnaps[c.id] = _snapForTab(c.id); });
        _checkDirty();
      });

      /* --- Save advanced --- */
      $w.on('click', '#adv-save', function() {
        var val = UI.collectForm('#adv-form');
        Modal.restart('Advanced settings saved. Service is restarting\u2026');
        $.ajax({ url: CFG.baseUrl + 'set_advanced_settings',
          data: { set_advanced_settings: val },
          dataType:'text', timeout:12000, cache:false
        });
        _tabSnaps['__advanced__'] = _snapForTab('__advanced__');
        _checkDirty();
      });

      /* --- Per-tab dirty tracking --- */
      function _notifSnap() {
        var parts = [];
        $w.find('.notif-card').each(function() {
          var em = $(this).find('.n-email').val().trim();
          var cats = [];
          $(this).find('.n-cat:checked').each(function(){ cats.push($(this).data('cat')); });
          parts.push(em+'='+cats.join(','));
        });
        return parts.join('&');
      }
      function _snapForTab(cat) {
        if (cat === '__notifications__') return _notifSnap();
        if (cat === '__advanced__') return advData ? UI.collectForm('#adv-form') : '';
        if (cat === '__sysactions__') return '';
        return UI.collectForm('.set-panel[data-cat="'+cat+'"]');
      }
      var _tabSnaps = {};
      CATS.forEach(function(c) { _tabSnaps[c.id] = _snapForTab(c.id); });
      _tabSnaps['__advanced__'] = _snapForTab('__advanced__');
      _tabSnaps['__sysactions__'] = '';
      _tabSnaps['__notifications__'] = _snapForTab('__notifications__');
      function _isTabDirty(cat) { return _snapForTab(cat) !== _tabSnaps[cat]; }
      function _checkDirty() {
        var dirty = false;
        for (var k in _tabSnaps) { if (_isTabDirty(k)) { dirty = true; break; } }
        S.dirty['settings'] = dirty;
      }
      $w.on('change input', '[name]', _checkDirty);
      $w.on('change input', '.n-email, .n-cat', _checkDirty);

      /* --- Notifications: Add / Delete / Save --- */
      $('#n-add').on('click', function() {
        $('#notif-list').append(_notifRecipientCard({email:'', cats:[]}));
        setTimeout(_checkDirty, 0);
      });
      $w.on('click', '.n-del', function(){ $(this).closest('.notif-card').remove();
        setTimeout(_checkDirty, 0);
      });
      $('#n-save').on('click', function() {
        var parts = [];
        $w.find('.notif-card').each(function() {
          var em = $(this).find('.n-email').val().trim();
          if (!em) return;
          var cats = [];
          $(this).find('.n-cat:checked').each(function(){ cats.push($(this).data('cat')); });
          parts.push(em+'='+cats.join(','));
        });
        Modal.restart('Notification settings saved. Service is restarting\u2026');
        $.ajax({ url: CFG.baseUrl + 'setnotifications',
          data: { setnotifications: parts.join('&') } });
        _tabSnaps['__notifications__'] = _snapForTab('__notifications__');
        _checkDirty();
      });
    },
    update: function() {}
  },

  /* ========== ADD-ONS ========== */
  addons: {
    cmd: null,
    _data: null,
    _pending: null,
    /* ── Addon Icon System ──────────────────────────────────────
     * Icons are resolved via a 3-step fallback chain:
     *
     *  1. Embedded SVG symbol  — <symbol id="adn-{key}"> injected
     *     by addon-icons.js at startup. Fastest; no extra request.
     *
     *  2. External SVG file    — static/svg/{key}.svg
     *     Drop any SVG into that folder and it is picked up automatically.
     *
     *  3. External PNG file    — static/images/{key}.png
     *     Same idea but for raster icons.
     *
     *  4. Fallback             — The "genmon" gear symbol (always present).
     *
     * The icon key comes from the backend (genserv.py AddOnCfg "icon"
     * field), lowercased with non-alphanumeric chars stripped.
     *
     * TO ADD A NEW ADDON ICON:
     *   - Preferred: add a <symbol id="adn-yourkey"> to addon-icons.js
     *   - Quick:     drop yourkey.svg into static/svg/
     *   - Legacy:    drop yourkey.png into static/images/
     * ──────────────────────────────────────────────────────────── */
    _addonIcon: function(name) {
      /* 1. Embedded symbol (from addon-icons.js) */
      if (document.getElementById('adn-' + name)) {
        return '<svg class="adn-icon"><use href="#adn-' + name + '"></use></svg>';
      }
      /* 2. External SVG file  (drop {key}.svg into static/svg/) */
      /* 3. External PNG file  (drop {key}.png into static/images/) */
      /* On error, cascade: SVG → PNG → embedded genmon gear fallback */
      return '<img class="adn-icon" src="svg/' + encodeURIComponent(name) + '.svg" onerror="'
        + "this.onerror=function(){this.replaceWith(document.createRange().createContextualFragment("
        + "'<svg class=adn-icon><use href=#adn-genmon></use></svg>'))};" 
        + 'this.src="images/' + encodeURIComponent(name) + '.png"' + '">';
    },
    render: function($c) {
      var h = '<div class="page-title">'+icon('addons')+' Add-Ons</div>';
      h += '<div class="adn-filters">' +
        '<button class="adn-filter active" data-filter="all">All</button>' +
        '<button class="adn-filter" data-filter="active">Installed</button>' +
        '<button class="adn-filter" data-filter="available">Available</button>' +
        '<div class="adn-search-wrap">' +
        '<svg class="adn-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
        '<input class="adn-search" placeholder="Search add-ons\u2026" id="adn-q"></div></div>';
      /* Two sections: installed + available */
      h += '<div id="addon-sec-installed" class="adn-section">' +
        '<div class="adn-section-hdr">'+icon('check')+' Installed</div>' +
        '<div id="addon-grid-installed" class="adn-grid">' + Pages.addons._skeletons(3) + '</div></div>';
      h += '<div id="addon-sec-available" class="adn-section">' +
        '<div class="adn-section-hdr">'+icon('download')+' Available</div>' +
        '<div id="addon-grid-available" class="adn-grid">' + Pages.addons._skeletons(4) + '</div></div>';
      $c.html(h);

      $c.on('click', '.adn-filter', function() {
        $('.adn-filter').removeClass('active');
        $(this).addClass('active');
        Pages.addons._applyFilter();
      });
      $('#adn-q').on('input', function() { Pages.addons._applyFilter(); });

      API.get('get_add_on_settings', 12000).done(function(d){ Pages.addons._build(d); })
        .fail(function() {
          $('.adn-skel').remove();
          $('#addon-grid-installed').html('<div class="text-muted text-center" style="grid-column:1/-1">Failed to load add-ons.</div>');
          $('#addon-grid-available').empty();
        });
    },
    _skeletons: function(n) {
      var s = '';
      for (var i = 0; i < n; i++) {
        s += '<div class="adn-tile adn-skel">' +
          '<div class="adn-skel-icon"></div>' +
          '<div class="adn-skel-line adn-skel-title"></div>' +
          '<div class="adn-skel-line adn-skel-desc"></div>' +
          '<div class="adn-skel-line adn-skel-desc2"></div></div>';
      }
      return s;
    },
    _applyFilter: function() {
      var f = $('.adn-filter.active').data('filter') || 'all';
      var q = ($('#adn-q').val() || '').toLowerCase();
      $('#addon-sec-installed').toggle(f === 'all' || f === 'active');
      $('#addon-sec-available').toggle(f === 'all' || f === 'available');
      if (q) {
        $('.adn-tile').each(function() {
          var $t = $(this);
          var name = ($t.data('title') || '').toLowerCase() + ' ' + ($t.data('mod') || '').toLowerCase();
          $t.toggle(name.indexOf(q) >= 0);
        });
      } else {
        $('.adn-tile').show();
      }
    },
    _paramInput: function(mod, key, par) {
      var v = esc(par.value != null ? par.value : '');
      var id = 'addon-p-'+esc(mod)+'-'+esc(key);
      if (par.type === 'boolean' || par.type === 'bool') {
        var ck = (par.value === true || par.value === 'true') ? ' checked' : '';
        return '<label class="toggle"><input type="checkbox" id="'+id+'" data-mod="'+esc(mod)+'" data-pk="'+esc(key)+'"'+ck+'>' +
          '<span class="toggle-slider"></span></label>';
      }
      if (par.type === 'list' && par.bounds) {
        var opts = par.bounds.split(',');
        var s = '<select class="form-select" id="'+id+'" data-mod="'+esc(mod)+'" data-pk="'+esc(key)+'">';
        opts.forEach(function(o) {
          o = o.trim();
          s += '<option value="'+esc(o)+'"'+(o === String(par.value)?' selected':'')+'>'+esc(o)+'</option>';
        });
        return s + '</select>';
      }
      if (par.type === 'password') {
        var pwb = par.bounds ? ' data-bounds="'+esc(par.bounds)+'"' : '';
        return '<input class="form-input" id="'+id+'" type="password" data-mod="'+esc(mod)+'" data-pk="'+esc(key)+'" value="'+v+'"'+pwb+'>';
      }
      if (par.type === 'readonly') {
        return '<div style="display:flex;align-items:center;gap:6px">' +
          '<input class="form-input" id="'+id+'" type="text" value="'+v+'" readonly ' +
          'style="background:#e9ecef;border-color:#ced4da;opacity:.85;cursor:default;user-select:all;color:#495057;flex:1">' +
          '<button type="button" class="btn btn-sm" style="white-space:nowrap;padding:2px 8px;font-size:12px" ' +
          'onclick="var i=this.previousElementSibling;i.select();document.execCommand(\'copy\');this.textContent=\'Copied!\';var b=this;setTimeout(function(){b.textContent=\'Copy\';},1500)" ' +
          'title="Copy to clipboard">Copy</button></div>';
      }
      var tp = (par.type === 'int' || par.type === 'number') ? 'number' : 'text';
      var ab = par.bounds ? ' data-bounds="'+esc(par.bounds)+'"' : '';
      return '<input class="form-input" id="'+id+'" type="'+tp+'" data-mod="'+esc(mod)+'" data-pk="'+esc(key)+'" value="'+v+'"'+ab+'>';
    },
    _buildTile: function(mod, cfg) {
      var enabled = cfg.enable === true || cfg.enable === 'true';
      var title = cfg.title || mod;
      var iconKey = (cfg.icon || 'genmon').toLowerCase().replace(/[^a-z0-9]/g, '');
      var h = '<div class="adn-tile'+(enabled?' adn-active':'')+'" data-mod="'+esc(mod)+'" data-enabled="'+enabled+'" data-title="'+esc(title)+'">';
      h += '<div class="adn-tile-icon">' + Pages.addons._addonIcon(iconKey) + '</div>';
      h += '<div class="adn-tile-name">'+esc(title)+'</div>';
      if (cfg.description) h += '<div class="adn-tile-desc">'+safeHtml(cfg.description)+'</div>';
      if (cfg.url) h += '<a class="adn-tile-doc" href="'+esc(cfg.url)+'" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">' +
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>' +
        ' Documentation</a>';
      if (enabled) h += '<div class="adn-tile-badge">Active</div>';
      h += '</div>';
      return h;
    },
    _build: function(data) {
      if (!data || typeof data !== 'object' || Object.keys(data).length === 0) {
        $('#addon-grid-installed').html('<div class="text-muted text-center" style="grid-column:1/-1">No add-ons found.</div>');
        return;
      }
      Pages.addons._data = data;
      var self = Pages.addons;
      var installed = [], available = [];
      Object.keys(data).sort(function(a, b) {
        return (data[a].title || a).localeCompare(data[b].title || b);
      }).forEach(function(mod) {
        var cfg = data[mod];
        var en = cfg.enable === true || cfg.enable === 'true';
        (en ? installed : available).push(mod);
      });
      var hi = '', ha = '';
      installed.forEach(function(m){ hi += self._buildTile(m, data[m]); });
      available.forEach(function(m){ ha += self._buildTile(m, data[m]); });
      var $gi = $('#addon-grid-installed').html(hi || '<div class="text-muted text-center" style="grid-column:1/-1">No installed add-ons.</div>');
      var $ga = $('#addon-grid-available').html(ha || '<div class="text-muted text-center" style="grid-column:1/-1">All add-ons are installed!</div>');
      /* installed tile → open settings directly */
      $gi.on('click', '.adn-tile', function() {
        var mod = $(this).data('mod');
        $('.adn-tile').removeClass('adn-selected');
        $(this).addClass('adn-selected');
        self._openDetail(mod, false);
      });
      /* available tile → install wizard */
      $ga.on('click', '.adn-tile', function() {
        self._installAddon($(this).data('mod'), $(this));
      });
    },
    /* ---- Install wizard for available apps ---- */
    _installAddon: function(mod, $tile) {
      var cfg = Pages.addons._data[mod];
      if (!cfg) return;
      var self = Pages.addons;
      var title = cfg.title || mod;
      Modal.confirm('Install ' + esc(title),
        Modal.html('Do you want to install <strong>' + esc(title) + '</strong>?' +
        (cfg.description ? '<br><span style="color:var(--text-2);font-size:.88rem">' + safeHtml(cfg.description) + '</span>' : '')),
        function() {
          /* animate tile out of available */
          $tile.css({transition:'transform .3s,opacity .3s',transform:'scale(.85)',opacity:0});
          setTimeout(function() {
            $tile.detach().removeAttr('style');
            /* promote to installed section */
            $('#addon-grid-installed .text-muted').remove();
            $tile.addClass('adn-active adn-tile-pop').data('enabled',true);
            $tile.find('.adn-tile-badge').remove();
            $tile.append('<div class="adn-tile-badge">New</div>');
            $('#addon-grid-installed').append($tile);
            /* rebind click for installed behaviour */
            $tile.off('click').on('click', function() {
              var m = $(this).data('mod');
              $('.adn-tile').removeClass('adn-selected');
              $(this).addClass('adn-selected');
              self._openDetail(m, false);
            });
            setTimeout(function(){ $tile.removeClass('adn-tile-pop'); }, 500);
            /* update available placeholder */
            if (!$('#addon-grid-available .adn-tile').length)
              $('#addon-grid-available').html('<div class="text-muted text-center" style="grid-column:1/-1">All add-ons are installed!</div>');
            /* open config panel as new-install wizard */
            $('.adn-tile').removeClass('adn-selected');
            $tile.addClass('adn-selected');
            self._pending = mod;
            self._openDetail(mod, true);
          }, 320);
        }
      );
    },
    /* ---- Cancel a pending (unsaved) install ---- */
    _cancelPending: function(mod) {
      var self = Pages.addons;
      self._pending = null;
      var $tile = $('.adn-tile[data-mod="'+mod+'"]');
      if (!$tile.length) return;
      $tile.removeClass('adn-active adn-selected');
      $tile.find('.adn-tile-badge').remove();
      $tile.data('enabled', false);
      $tile.css({transition:'transform .3s,opacity .3s',transform:'scale(.85)',opacity:0});
      setTimeout(function() {
        $tile.detach().removeAttr('style');
        $('#addon-grid-available .text-muted').remove();
        $tile.addClass('adn-tile-pop');
        $('#addon-grid-available').append($tile);
        $tile.off('click').on('click', function() {
          self._installAddon($(this).data('mod'), $(this));
        });
        setTimeout(function(){ $tile.removeClass('adn-tile-pop'); }, 500);
        if (!$('#addon-grid-installed .adn-tile').length)
          $('#addon-grid-installed').html('<div class="text-muted text-center" style="grid-column:1/-1">No installed add-ons.</div>');
      }, 320);
    },
    /* ---- Detail / settings modal ---- */
    _openDetail: function(mod, isNew) {
      var cfg = Pages.addons._data[mod];
      if (!cfg) return;
      var self = Pages.addons;
      var enabled = isNew ? true : (cfg.enable === true || cfg.enable === 'true');
      var title = cfg.title || mod;
      var desc = cfg.description || '';
      var url = cfg.url || '';
      var iconKey = (cfg.icon || 'genmon').toLowerCase().replace(/[^a-z0-9]/g, '');
      var params = cfg.parameters;
      var hasParams = params && typeof params === 'object' && Object.keys(params).length > 0;

      /* Build modal body */
      var h = '<div class="adn-modal-body">';

      /* Hero header inside modal body */
      h += '<div class="adn-detail-header">' +
        '<div class="adn-detail-icon">' + self._addonIcon(iconKey) + '</div>' +
        '<div class="adn-detail-info">' +
          '<div class="adn-detail-title">'+esc(title)+'</div>' +
          '<div class="adn-detail-mod">'+esc(mod)+'</div>' +
        '</div>';
      if (!isNew)
        h += '<label class="toggle adn-detail-toggle"><input type="checkbox" class="addon-tog" data-mod="'+esc(mod)+'"'+(enabled?' checked':'')+'>' +
          '<span class="toggle-slider"></span></label>';
      h += '</div>';

      if (isNew)
        h += '<div class="adn-wizard-hint">'+icon('zap')+' Configure the settings below, then click <strong>Save &amp; Start</strong> to activate.</div>';
      if (desc) h += '<p class="adn-detail-desc">'+safeHtml(desc)+'</p>';
      if (url) h += '<a class="addon-link" href="'+esc(url)+'" target="_blank" rel="noopener">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>' +
        ' Documentation</a>';

      if (hasParams) {
        h += '<div class="adn-detail-section-title">Settings</div>';
        h += '<div class="addon-params">';
        Object.keys(params).forEach(function(pk) {
          var p = params[pk];
          var label = p.display_name || pk;
          var hint = p.description || '';
          h += '<div class="adn-param-row">' +
            '<label class="form-label" for="addon-p-'+esc(mod)+'-'+esc(pk)+'">'+esc(label)+'</label>' +
            self._paramInput(mod, pk, p) +
            (hint ? '<div class="form-hint">'+esc(hint)+'</div>' : '') +
            '</div>';
        });
        h += '</div>';
      }

      h += '</div>'; /* end .adn-modal-body */

      var saveLabel = isNew ? (btnIcon('play')+' Save &amp; Start') : (btnIcon('save')+' Save &amp; Apply');

      /* Use Modal.show with custom wider class */
      Modal.show(title, Modal.html(h), [
        {text:'Cancel', action:'cancel'},
        {text: isNew ? 'Save & Start' : 'Save & Apply', cls:'btn-primary', action:'save'}
      ]);

      /* Widen the modal + replace the save button icon */
      var $m = $('#modal-overlay .modal').addClass('adn-settings-modal');
      $m.find('.modal-footer [data-action="save"]').html(saveLabel);

      /* Live bounds validation on addon parameter inputs */
      UI.bindBoundsValidation($m);

      /* Close/cancel cleanup helper */
      var closeCleanup = function() {
        $('.adn-tile').removeClass('adn-selected');
        if (self._pending === mod) self._cancelPending(mod);
        Modal.close();
      };
      /* Override default X-close button to run cleanup */
      $m.find('.modal-close').off('click').on('click', closeCleanup);

      /* toggle (existing installs only) */
      $m.find('.addon-tog').on('change', function() {
        var $tile = $('.adn-tile[data-mod="'+mod+'"]');
        if (this.checked) {
          $tile.addClass('adn-active').data('enabled', true);
          $tile.find('.adn-tile-badge').remove();
          $tile.append('<div class="adn-tile-badge">Active</div>');
        } else {
          $tile.removeClass('adn-active').data('enabled', false);
          $tile.find('.adn-tile-badge').remove();
        }
      });

      /* Handle save / cancel via Modal callback */
      Modal.onAction(function(a) {
        if (a === 'save') {
          var payload = {};
          payload[mod] = {};
          payload[mod].enable = isNew ? 'true' : ($m.find('.addon-tog').is(':checked') ? 'true' : 'false');
          var paramVals = {};
          $m.find('.addon-params input, .addon-params select').each(function() {
            var $el = $(this);
            var pk = $el.data('pk');
            if (!pk) return;
            paramVals[pk] = $el.attr('type') === 'checkbox' ? ($el.is(':checked') ? 'true' : 'false') : $el.val();
          });
          if (Object.keys(paramVals).length) payload[mod].parameters = paramVals;
          self._pending = null;
          $('.adn-tile').removeClass('adn-selected');
          Modal.close();
          Pages.addons._data[mod].enable = payload[mod].enable;
          var $tile = $('.adn-tile[data-mod="'+mod+'"]');
          $tile.find('.adn-tile-badge').remove();
          if (payload[mod].enable === 'true') {
            $tile.addClass('adn-active').data('enabled', true);
            $tile.append('<div class="adn-tile-badge">Active</div>');
          }
          Modal.restart(esc(title) + ' settings saved. Service is restarting\u2026');
          API.set('set_add_on_settings', JSON.stringify(payload), 15000);
        } else {
          /* cancel */
          closeCleanup();
        }
      });
    },
    update: function() {}
  },

  /* ========== ABOUT ========== */
  about: {
    cmd: null,
    render: function($c) {
      var info = S.startInfo || {};
      var h = '<div class="page-title">'+icon('about')+' About</div>';

      /* --- Update available banner --- */
      if (S.updateAvailable) {
        h += '<div class="about-update-banner">' +
          '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
          '<span>A software update is available!</span>' +
          '<button class="btn btn-sm about-update-btn" id="a-update-banner">Update Now</button>' +
        '</div>';
      }

      /* --- Logo hero + credits --- */
      h += '<div class="about-hero">' +
        '<div class="about-logo-placeholder"></div>' +
        '<div class="about-tagline">Generator Monitoring &amp; Management</div>' +
        '<div class="about-version">Version ' + esc(info.version || CFG.version) + '</div>' +
        '<div class="about-credits">' +
          '<span>Developed by <a href="https://github.com/jgyates" target="_blank" rel="noopener">@jgyates</a></span>' +
          '<span class="about-sep">&middot;</span>' +
          '<span>UI by <a href="https://github.com/MichaelB2018" target="_blank" rel="noopener">@MichaelB2018</a></span>' +
          '<span class="about-sep">&middot;</span>' +
          '<span>Published under the <a href="https://www.gnu.org/licenses/old-licenses/gpl-2.0.html" target="_blank" rel="noopener">GNU GPL v2.0</a></span>' +
          '<span class="about-sep">&middot;</span>' +
          '<span>Source on <a href="https://github.com/jgyates/genmon" target="_blank" rel="noopener">GitHub</a></span>' +
        '</div>' +
        '<div class="about-built">Built with Python &amp; JavaScript</div>' +
      '</div>';

      /* --- Software & Info card --- */
      h += '<div class="card mb-2"><div class="card-header">' + icon('cpu') + ' Software</div><div class="card-body">';
      [['Genmon Version', info.version], ['UI Version', CFG.version],
       ['Python', info.python], ['Platform', info.platform],
       ['OS Architecture', (info.os_bits||'')], ['Install Date', info.install]
      ].forEach(function(f){
        if (f[1]) h += '<div class="kv-row"><span class="kv-key">'+esc(f[0])+'</span><span class="kv-val">'+esc(f[1])+'</span></div>';
      });
      h += '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">' +
        '<button class="btn btn-outline btn-sm" id="a-changelog">'+btnIcon('logs')+' View Changelog</button>';
      if (S.writeAccess || !info.LoginActive)
        h += '<button class="btn btn-primary btn-sm" id="a-update">'+btnIcon('refresh')+' Update Software</button>';
      h += '</div></div></div>';

      /* --- Generator card --- */
      h += '<div class="card mb-2"><div class="card-header">' + icon('zap') + ' Generator</div><div class="card-body">';
      [['Model', info.model||info.Controller], ['Controller', info.Controller],
       ['Firmware', info.Firmware], ['Hardware', info.Hardware],
       ['Fuel Type', info.fueltype], ['Nominal kW', info.nominalKW],
       ['Nominal RPM', info.nominalRPM], ['Frequency', info.nominalfrequency],
       ['Phase', info.phase]
      ].forEach(function(f){
        h += '<div class="kv-row"><span class="kv-key">'+esc(f[0])+'</span><span class="kv-val">'+esc(f[1]||'--')+'</span></div>';
      });
      h += '</div></div>';

      /* --- Request Help card --- */
      h += '<div class="card mb-2"><div class="card-header">' + icon('mail') + ' Request Help</div><div class="card-body">' +
        '<p style="margin:0 0 10px;font-size:.85rem;color:var(--text-2)">' +
        'If you are experiencing issues, you can submit your generator registers or log files to the developer for analysis. ' +
        'Outbound email must be configured and working in genmon for these buttons to function.</p>' +
        '<p style="margin:0 0 10px;font-size:.85rem;color:var(--text-2)">' +
        'To raise a support ticket, please open an issue on ' +
        '<a href="https://github.com/jgyates/genmon/issues/" target="_blank" rel="noopener noreferrer" ' +
        'style="color:var(--accent)">GitHub Issues</a>. ' +
        'See <a href="https://github.com/jgyates/genmon/issues/16" target="_blank" rel="noopener noreferrer" ' +
        'style="color:var(--accent)">issue #16</a> for guidelines on how to submit a helpful report.</p>' +
        '<p style="margin:0 0 10px;font-size:.85rem;color:var(--text-2)">' +
        'For questions, installation help, or general discussion, visit the ' +
        '<a href="https://github.com/jgyates/genmon/discussions" target="_blank" rel="noopener noreferrer" ' +
        'style="color:var(--accent)">GitHub Discussions</a> forum.</p>' +
        '<div class="btn-group">' +
        '<button class="btn btn-outline btn-sm" id="a-submit-regs">'+btnIcon('upload')+' Submit Registers</button>' +
        '<button class="btn btn-outline btn-sm" id="a-submit-logs">'+btnIcon('upload')+' Submit Logs</button></div></div></div>';

      /* --- Actions card --- */
      if (S.writeAccess || !info.LoginActive) {
        h += '<div class="card mb-2"><div class="card-header">' + icon('settings') + ' Actions</div><div class="card-body">' +
          '<div class="btn-group flex-wrap">' +
          '<button class="btn btn-outline btn-sm" id="a-backup">'+btnIcon('archive')+' Export Configuration</button>' +
          '<button class="btn btn-outline btn-sm" id="a-restore">'+btnIcon('upload')+' Import Configuration</button>' +
          '<input type="file" id="a-restore-file" accept=".tar.gz,.gz" style="display:none">' +
          '<button class="btn btn-outline btn-sm" id="a-logs">'+btnIcon('download')+' Download Logs</button>' +
          '<button class="btn btn-danger btn-sm" id="a-restart">'+btnIcon('power')+' Restart Genmon</button></div></div></div>';
      }

      $c.html(h);

      /* Clone sidebar logo into the about page */
      var srcSvg = document.querySelector('.sidebar-logo');
      if (srcSvg) {
        var clone = srcSvg.cloneNode(true);
        clone.setAttribute('class', 'about-logo');
        clone.removeAttribute('role');
        clone.removeAttribute('aria-label');
        $c.find('.about-logo-placeholder').replaceWith(clone);
      }

      /* --- Event handlers --- */
      $('#a-update-banner').on('click', function() { $('#a-update').trigger('click'); });
      $('#a-changelog').on('click', function(){
        Pages.about._showChangelog();
      });
      $('#a-submit-regs').on('click', function(){
        Modal.confirm('Submit Registers', 'Send your generator register data to the developer via email?', function(){
          API.set('sendregisters', '', 15000)
            .done(function(){ Modal.alert('Sent', 'Register data submitted successfully.'); })
            .fail(function(){ Modal.alert('Error', 'Failed to submit register data. Check email configuration.'); });
        });
      });
      $('#a-submit-logs').on('click', function(){
        Modal.confirm('Submit Logs', 'Send your log files to the developer via email? This may take a moment.', function(){
          API.set('sendlogfiles', '', 30000)
            .done(function(){ Modal.alert('Sent', 'Log files submitted successfully.'); })
            .fail(function(){ Modal.alert('Error', 'Failed to submit log files. Check email configuration.'); });
        });
      });
      $('#a-backup').on('click', function(){ Pages.about._download('backup', 'Export Configuration'); });
      $('#a-restore').on('click', function(){ $('#a-restore-file').val('').click(); });
      $('#a-restore-file').on('change', function() {
        var file = this.files && this.files[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.tar.gz')) {
          Modal.alert('Invalid File', 'Please select a .tar.gz backup archive (e.g. genmon_backup.tar.gz).'); return;
        }
        if (file.size > 10 * 1024 * 1024) {
          Modal.alert('File Too Large', 'Maximum upload size is 10 MB.'); return;
        }
        Modal.confirm('Import Configuration',
          Modal.html('This will <strong>overwrite</strong> your current genmon configuration files with the contents of <em>' + esc(file.name) + '</em>.<br><br>' +
          'You will need to <strong>restart genmon</strong> for the restored settings to take effect.<br><br>' +
          'Are you sure you want to continue?'),
          function() {
            Modal.show('Importing', Modal.html(
              '<div class="restart-modal">' +
                '<div class="restart-spinner"></div>' +
                '<p class="restart-msg">Uploading &amp; restoring configuration\u2026</p>' +
              '</div>'), []);
            var fd = new FormData();
            fd.append('file', file);
            fetch('/upload', { method: 'POST', body: fd }).then(function(resp) {
              return resp.json();
            }).then(function(data) {
              if (data.status === 'ok') {
                Modal.restart(data.message || 'Configuration restored. Service is restarting…');
              } else {
                Modal.close();
                Modal.alert('Error', data.message || 'Restore failed.');
              }
            }).catch(function() {
              Modal.close();
              Modal.alert('Error', 'Upload failed. Please try again.');
            });
          });
      });
      $('#a-logs').on('click', function(){ Pages.about._download('get_logs', 'Download Logs'); });
      $('#a-update').on('click', function(){
        Modal.confirm('Update Software',
          'Download and install the latest version of Genmon? The service will restart automatically when done.',
          function(){
            /* Phase 1: show downloading progress */
            Modal.show('Updating', Modal.html(
              '<div class="restart-modal">' +
                '<div class="restart-spinner"></div>' +
                '<p class="restart-msg">Downloading &amp; installing update\u2026</p>' +
                '<p class="restart-countdown" style="font-size:.82rem;color:var(--text-2)">This may take a minute. Do not close the browser.</p>' +
                '<div class="restart-bar-track"><div class="restart-bar-fill" id="upd-bar" style="width:0%"></div></div>' +
              '</div>'), []);
            /* Indeterminate progress animation */
            var updPct = 0, updDir = 1, updTimer = setInterval(function(){
              updPct += updDir * 1.5;
              if (updPct >= 90) updDir = 0.2;
              $('#upd-bar').css('width', Math.min(updPct, 95) + '%');
            }, 300);
            /* Fire update request (timeout: 0 — server restarts before replying) */
            $.ajax({ url: CFG.baseUrl + 'updatesoftware', dataType: 'json', timeout: 0, cache: false })
              .done(function(){
                /* Unexpected — server shouldn't reply before restarting */
                clearInterval(updTimer);
                Modal.close();
                Modal.alert('Note', 'Genmon may not have updated. Please verify manually or try again.');
              })
              .fail(function(){
                /* Expected — server restarted; switch to restart modal */
                clearInterval(updTimer);
                Modal.close();
                Modal.restart('Update installed. Service is restarting\u2026');
              });
          });
      });
      $('#a-restart').on('click', function(){
        Modal.confirm('Restart','Restart the genmon service?', function(){
          $.ajax({ url: CFG.baseUrl + 'restart', dataType: 'json', timeout: 0, cache: false });
          Modal.restart('Service is restarting\u2026');
        });
      });
    },
    _download: function(cmd, title) {
      Modal.show(title, Modal.html(
        '<div class="restart-modal">' +
          '<div class="restart-spinner"></div>' +
          '<p class="restart-msg">Preparing download\u2026</p>' +
        '</div>'), []);
      fetch(CFG.baseUrl + cmd).then(function(resp) {
        var cd = resp.headers.get('content-disposition') || '';
        var m = cd.match(/filename[^;=\n]*=["']?([^"';\n]+)/);
        var fname = m ? m[1] : cmd.replace(/\//g, '_') + '.bin';
        return resp.blob().then(function(blob) { return { blob: blob, name: fname }; });
      }).then(function(r) {
        var url = URL.createObjectURL(r.blob);
        var a = document.createElement('a');
        a.href = url; a.download = r.name;
        document.body.appendChild(a); a.click();
        document.body.removeChild(a);
        setTimeout(function() { URL.revokeObjectURL(url); }, 5000);
        Modal.close();
      }).catch(function() {
        Modal.alert('Error', 'Download failed. Please try again.');
      });
    },
    _showChangelog: function(){
      var url = 'https://raw.githubusercontent.com/jgyates/genmon/master/changelog.md';
      Modal.show('Changelog', Modal.html(
        '<div class="changelog-body" style="padding:8px;font-size:.85rem;color:var(--text-1)">' +
        '<div class="text-muted text-center">Loading changelog…</div></div>'), []);
      $.get(url).done(function(md){
        var html = md
          .replace(/^# (.+)$/gm, '<h3 style="margin:16px 0 8px;color:var(--accent)">$1</h3>')
          .replace(/^## (.+)$/gm, '<h4 style="margin:14px 0 6px;color:var(--text-1);border-bottom:1px solid var(--glass-border);padding-bottom:4px">$1</h4>')
          .replace(/^### (.+)$/gm, '<h5 style="margin:10px 0 4px;color:var(--text-2)">$1</h5>')
          .replace(/^- (.+)$/gm, '<div style="padding:2px 0 2px 16px;position:relative"><span style="position:absolute;left:4px;color:var(--accent)">•</span>$1</div>')
          .replace(/\n{2,}/g, '<br>');
        $('.changelog-body').html(html);
      }).fail(function(){
        $('.changelog-body').html('<div style="color:var(--danger)">Failed to load changelog.</div>');
      });
    },
    update: function() {}
  },

  /* ========== REGISTERS ========== */
  registers: {
    cmd: null,
    _hist: null, /* { _10m:{bank:{addr:[vals]}}, _60m:..., _24h:... } */
    _tick: 0,    /* poll counter for down-sampling */
    _chartInst: null,

    render: function($c) {
      $c.html('<div class="page-title">'+icon('modbus')+' Modbus Registers</div>' +
        '<div class="reg-toolbar">' +
        '<span class="text-muted" style="font-size:.82rem">Polling every 1 s &mdash; ' +
        '<span style="color:var(--danger)">&#9632;</span> just changed &nbsp;' +
        '<span style="color:var(--warning)">&#9632;</span> changed recently &nbsp;' +
        '<span style="color:rgba(96,165,250,.8)">&#9632;</span> changed since load</span>' +
        '<span id="reg-stats" class="reg-stats"></span></div>' +
        '<div id="reg-grid" class="reg-grid"><div class="text-muted text-center">Loading\u2026</div></div>');
      if (!S.regLabels)
        API.get('getreglabels').done(function(d){ S.regLabels = d||{}; });
      /* Preserve history across page navigations */
      if (!S.regTimestamps) S.regTimestamps = {};
      if (!S.changedRegs) S.changedRegs = {};
      if (!this._hist) this._hist = { _10m:{}, _60m:{}, _24h:{} };
      if (!this._tick) this._tick = 0;

      /* Click handler for register cells — show history chart */
      var self = this;
      $c.off('click.regchart').on('click.regchart', '.reg-cell[data-fk]', function() {
        self._showChart($(this).data('fk'));
      });
    },

    /* Flatten array-of-single-key-objects into a plain object */
    _flatten: function(raw) {
      if (!raw) return null;
      if (Array.isArray(raw)) {
        var obj = {};
        for (var i = 0; i < raw.length; i++) {
          var item = raw[i];
          if (item && typeof item === 'object')
            for (var k in item) { if (item.hasOwnProperty(k)) obj[k] = item[k]; }
        }
        return obj;
      }
      return raw;
    },

    /* Accumulate history at 3 resolutions */
    _record: function(flat) {
      var H = this._hist; if (!H) return;
      this._tick++;
      var do60 = (this._tick % 5 === 0);    /* every 5s  → 720 samples = 1 hr */
      var do24 = (this._tick % 60 === 0);    /* every 60s → 1440 samples = 24 hr */
      ['Holding','Inputs','Coils'].forEach(function(bank) {
        var regs = flat[bank]; if (!regs) return;
        if (!H._10m[bank]) { H._10m[bank]={}; H._60m[bank]={}; H._24h[bank]={}; }
        for (var addr in regs) {
          if (!regs.hasOwnProperty(addr)) continue;
          var val = regs[addr];
          if (!H._10m[bank][addr]) { H._10m[bank][addr]=[]; H._60m[bank][addr]=[]; H._24h[bank][addr]=[]; }
          H._10m[bank][addr].unshift(val);
          if (H._10m[bank][addr].length > 600) H._10m[bank][addr].pop();
          if (do60) { H._60m[bank][addr].unshift(val); if (H._60m[bank][addr].length>720) H._60m[bank][addr].pop(); }
          if (do24) { H._24h[bank][addr].unshift(val); if (H._24h[bank][addr].length>1440) H._24h[bank][addr].pop(); }
        }
      });
    },

    /* Show Chart.js line chart in a modal for a given register */
    _showChart: function(fk) {
      var parts = fk.split(':'), bank = parts[0], addr = parts[1];
      var H = this._hist;
      if (!H || !H._10m[bank] || !H._10m[bank][addr]) return;
      var lbl = (S.regLabels && S.regLabels[bank] && S.regLabels[bank][addr])
        ? S.regLabels[bank][addr] : (S.regLabels && S.regLabels[addr] ? S.regLabels[addr] : '');
      var title = (lbl ? lbl + ' ' : '') + '(' + bank + ':' + addr + ')';
      var body = '<div class="reg-chart-tabs">' +
        '<button class="reg-tab active" data-range="10m">10 min</button>' +
        '<button class="reg-tab" data-range="60m">1 hr</button>' +
        '<button class="reg-tab" data-range="24h">24 hr</button></div>' +
        '<div style="position:relative;height:220px"><canvas id="reg-chart-cv"></canvas></div>';
      Modal.show(title, Modal.html(body), [{text:'Close',cls:'btn-outline',action:'close'}]);

      var self = this;
      function buildData(key) {
        /* Sampling intervals: _10m = 1s, _60m = 5s, _24h = 60s
           If the requested buffer has too few points, fall back to finer
           buffers and downsample them to cover the requested timespan. */
        var secPerSample = {
          '10m': 1,    /* 1 sample/sec,  600 samples = 10 min */
          '60m': 5,    /* 1 sample/5s,   720 samples = 60 min */
          '24h': 60    /* 1 sample/60s, 1440 samples = 24 hr  */
        };
        var arr = (H['_'+key]||{})[bank] ? H['_'+key][bank][addr] : [];
        if (!arr) arr = [];

        /* Fall back to finer buffer and downsample when coarser buffer
           doesn't have enough data yet (< 3 points).  This ensures all
           three views are consistent rather than showing sparse snapshots. */
        if (arr.length < 3 && key !== '10m') {
          var finerKey = (key === '24h') ? '60m' : '10m';
          var finerArr = (H['_'+finerKey]||{})[bank] ? H['_'+finerKey][bank][addr] : [];
          if (!finerArr || finerArr.length < 3) {
            finerKey = '10m';
            finerArr = (H['_10m']||{})[bank] ? H['_10m'][bank][addr] : [];
          }
          if (finerArr && finerArr.length >= 3) {
            arr = finerArr;
            secPerSample[key] = secPerSample[finerKey];
          }
        }

        var sps = secPerSample[key];
        var labels = [], vals = [];
        for (var i = arr.length - 1; i >= 0; i--) {
          var dec = parseInt(arr[i], 16);
          if (isNaN(dec)) dec = 0;
          vals.push(dec);
          var minsAgo = -(i * sps / 60);
          labels.push(minsAgo.toFixed(sps < 60 ? 1 : 0));
        }
        return { labels: labels, vals: vals };
      }

      function renderChart(range) {
        var d = buildData(range);
        var cs = getComputedStyle(document.documentElement);
        var gridC = cs.getPropertyValue('--chart-grid').trim() || 'rgba(148,163,184,.1)';
        var tickC = cs.getPropertyValue('--chart-tick').trim() || '#94a3b8';
        var ctx = document.getElementById('reg-chart-cv');
        if (!ctx) return;
        if (self._chartInst) { self._chartInst.destroy(); self._chartInst = null; }
        self._chartInst = new Chart(ctx, {
          type: 'line',
          data: { labels: d.labels, datasets: [{
            label: 'DEC', data: d.vals, borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,.1)', tension: .3, fill: true,
            pointRadius: d.vals.length > 100 ? 0 : 2, borderWidth: 1.5
          }]},
          options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
              x: { display: true, grid: {color: gridC},
                title: { display: true, text: 'Minutes ago', color: tickC, font:{size:10} },
                ticks: { color: tickC, maxTicksLimit: 8, maxRotation: 0, autoSkip: true, font:{size:9} }},
              y: { display: true, grid: {color: gridC}, ticks: { color: tickC, font:{size:9} } }
            },
            plugins: { legend: { display: false } }, animation: { duration: 300 }
          }
        });
      }

      renderChart('10m');
      /* Tab switching */
      $('.reg-chart-tabs').off('click').on('click', '.reg-tab', function() {
        $('.reg-tab').removeClass('active');
        $(this).addClass('active');
        renderChart($(this).data('range'));
      });
    },

    update: function(data) {
      if (!data) return;
      var root = data.Registers || data;
      var now = Date.now(), h = '';

      /* Stats summary */
      if (root['Num Regs'] != null) {
        $('#reg-stats').html(
          '<span><b>Regs:</b> '+esc(String(root['Num Regs']))+'</span>' +
          '<span><b>Changed:</b> '+esc(String(root['Changed']||0))+'</span>' +
          '<span><b>Total:</b> '+esc(String(root['Total Changed']||0))+'</span>');
      }

      var flat = {};
      var self = this;
      ['Holding','Inputs','Coils'].forEach(function(bank) {
        var regs = self._flatten(root[bank]);
        if (!regs) return;
        flat[bank] = regs;
        h += '<div class="reg-bank-hdr">'+esc(bank)+' Registers</div>';
        for (var addr in regs) {
          if (!regs.hasOwnProperty(addr)) continue;
          var val = regs[addr], fk = bank+':'+addr, cls = 'stale';
          if (S.prevRegData && S.prevRegData[bank] && S.prevRegData[bank][addr] !== val) {
            S.regTimestamps[fk] = now; cls = 'fresh';
            S.changedRegs[fk] = true;
          } else if (S.regTimestamps[fk]) {
            var age = now - S.regTimestamps[fk];
            cls = age < 2000 ? 'fresh' : age < 10000 ? 'recent' : 'stale';
          }
          if (S.changedRegs[fk]) cls += ' changed';
          /* Label from regLabels — check bank-keyed or flat */
          var lbl = '';
          if (S.regLabels) {
            if (S.regLabels[bank] && S.regLabels[bank][addr]) lbl = S.regLabels[bank][addr];
            else if (S.regLabels[addr]) lbl = S.regLabels[addr];
          }
          /* Compute DEC and HI:LO */
          var dec = parseInt(val, 16);
          var decStr = isNaN(dec) ? val : String(dec);
          var hi = isNaN(dec) ? '?' : String((dec >> 8) & 0xff);
          var lo = isNaN(dec) ? '?' : String(dec & 0xff);

          h += '<div class="reg-cell '+cls+'" data-fk="'+esc(fk)+'">' +
            (lbl ? '<div class="reg-label" title="'+esc(lbl)+'">'+esc(lbl)+'</div>' : '<div class="reg-label reg-label-empty">Register</div>') +
            '<div class="reg-sub">('+esc(bank)+':'+esc(addr)+')</div>' +
            '<div class="reg-hex">HEX: '+esc(val)+'</div>' +
            '<div class="reg-dec">DEC: '+esc(decStr)+' | HI:LO: '+esc(hi)+':'+esc(lo)+'</div>' +
            '</div>';
        }
      });
      S.prevRegData = flat;
      this._record(flat);
      $('#reg-grid').html(h || '<div class="text-muted text-center">No register data.</div>');
    }
  },

  /* ========== ADVANCED SETTINGS (merged into Settings) ========== */
  advanced: {
    cmd: null,
    render: function() { Router.go('settings'); },
    _build: function() {},
    update: function() {}
  }
};

/* ============================================================
   INIT
   ============================================================ */
function init() {
  Modal.init();
  Store._pull();
  Theme.init();

  /* Flush any pending Store writes when the tab/window closes */
  window.addEventListener('beforeunload', function() { Store._flush(); });

  $('#menu-toggle').on('click', function(){ Nav.toggleMobile(); });
  $('#sidebar-overlay').on('click', function(){ Nav.closeMobile(); });
  $('#theme-toggle').on('click', function(){ Theme.toggle(); });

  API.get('start_info_json', 10000)
    .done(function(data) {
      if (!data) { Modal.alert('Error','Failed to load generator info.'); return; }
      S.startInfo   = data;
      S.writeAccess = data.write_access !== false;

      if (data.sitename) {
        $('#site-name').text(data.sitename);
        document.title = data.sitename + ' \u2014 Genmon';
      }
      if (data.version) $('#footer-version').text('Genmon ' + data.version);

      /* Show logout button when authentication is active */
      if (data.LoginActive) {
        $('#logout-btn').show().on('click', function() {
          window.location.href = window.location.protocol + '//' + window.location.host + '/logout';
        });
      }

      /* Fetch metric setting for 24-hour clock display */
      API.get('settings', 8000).done(function(sd){
        if (sd && sd.metricweather) S.useMetric = (sd.metricweather[3] === true || sd.metricweather[3] === 'true');
      });

      Nav.build(data.pages);
      $('#loader').removeClass('active');
      $('#app').removeClass('hidden');
      Poll.start();
      Router.init();
      UI.connBadge();

      /* Welcome tour for first-time users */
      if (!Store.get('tourSeen')) {
        setTimeout(function() { Tour.start(); }, 800);
      }
    })
    .fail(function() {
      $('.loader-text').text('Connection failed. Retrying\u2026');
      setTimeout(init, 5000);
    });
}

/* ============================================================
   PUBLIC API
   ============================================================ */
window.Genmon = {
  init:  init,
  api:   API,
  modal: Modal,
  store: Store,
  theme: Theme,
  state: S,
  pages: Pages
};

})(jQuery, window);

/* Boot */
$(function() { Genmon.init(); });
