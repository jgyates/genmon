/* =================================================================
   GenmonGauge — Italian Sports-Car Instrument Cluster
   Metallic bezels, glowing needles, premium SVG gauges.
   Zero PNG dependencies.  Fully self-contained.
   ================================================================= */

(function(window) {
  'use strict';

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var _uid = 0;
  var ANIM_T = 'transform 600ms cubic-bezier(.4,0,.2,1)';
  var ANIM_D = '600ms ease';

  /* ---- shared helpers ---- */
  function uid()  { return 'gg' + (++_uid); }
  function svgEl(tag, a) {
    var el = document.createElementNS(SVG_NS, tag);
    if (a) for (var k in a) el.setAttribute(k, a[k]);
    return el;
  }
  function pol(cx, cy, r, deg) {
    var rad = (deg - 90) * Math.PI / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }
  function arc(cx, cy, r, a1, a2) {
    if (a2 - a1 <= 0) { var p = pol(cx,cy,r,a1); return 'M '+p.x+' '+p.y; }
    var s = pol(cx,cy,r,a1), e = pol(cx,cy,r,a2);
    return 'M '+s.x+' '+s.y+' A '+r+' '+r+' 0 '+(a2-a1>180?1:0)+' 1 '+e.x+' '+e.y;
  }

  /* Create <defs> with chrome-bezel gradients + needle shadow filter */
  function makeDefs(svg, id) {
    var d = svgEl('defs');
    /* Bezel — radial metallic gradient (lit from top-left) */
    var bzl = svgEl('radialGradient', {id:'bzl-'+id, cx:'38%', cy:'32%', r:'60%',
      fx:'38%', fy:'32%'});
    var stops = [
      ['0%',   'var(--gauge-bezel-hi)'],
      ['25%',  'var(--gauge-bezel-hi2)'],
      ['50%',  'var(--gauge-bezel-1)'],
      ['75%',  'var(--gauge-bezel-2)'],
      ['92%',  'var(--gauge-bezel-lo)'],
      ['100%', 'var(--gauge-bezel-lo2)']
    ];
    for (var si = 0; si < stops.length; si++) {
      var st = svgEl('stop', {offset:stops[si][0]}); st.style.stopColor = stops[si][1];
      bzl.appendChild(st);
    }
    d.appendChild(bzl);
    /* Specular highlight — tight bloom from top-left */
    var bzr = svgEl('radialGradient', {id:'bzr-'+id, cx:'32%', cy:'25%', r:'40%'});
    var r1 = svgEl('stop', {offset:'0%'});   r1.style.stopColor = 'var(--gauge-bezel-spec)';
    var r2 = svgEl('stop', {offset:'50%'});  r2.style.stopColor = 'var(--gauge-bezel-spec2)';
    var r3 = svgEl('stop', {offset:'100%'}); r3.style.stopColor = 'rgba(255,255,255,0)';
    bzr.appendChild(r1); bzr.appendChild(r2); bzr.appendChild(r3);
    d.appendChild(bzr);
    /* Face — subtle centered radial */
    var fg = svgEl('radialGradient', {id:'fc-'+id, cx:'50%', cy:'38%', r:'65%'});
    var fs1 = svgEl('stop', {offset:'0%'});  fs1.style.stopColor = 'var(--gauge-face-1)';
    var fs2 = svgEl('stop', {offset:'100%'}); fs2.style.stopColor = 'var(--gauge-face-2)';
    fg.appendChild(fs1); fg.appendChild(fs2);
    d.appendChild(fg);
    /* Subtle needle shadow */
    var nf = svgEl('filter', {id:'ns-'+id, x:'-50%', y:'-50%', width:'200%', height:'200%'});
    nf.appendChild(svgEl('feGaussianBlur', {'in':'SourceGraphic', stdDeviation:'0.8', result:'b'}));
    var m = svgEl('feMerge');
    m.appendChild(svgEl('feMergeNode', {'in':'b'}));
    m.appendChild(svgEl('feMergeNode', {'in':'SourceGraphic'}));
    nf.appendChild(m);  d.appendChild(nf);
    svg.appendChild(d);
  }

  /* Chrome center cap with needle-coloured dot */
  function drawHub(svg, cx, cy, r) {
    svg.appendChild(svgEl('circle', {cx:cx, cy:cy, r:r,
      fill:'var(--gauge-hub-1)', stroke:'var(--gauge-hub-ring)', 'stroke-width':'.8'}));
    svg.appendChild(svgEl('circle', {cx:cx, cy:cy, r:r*.45, fill:'var(--gauge-hub-2)'}));
    svg.appendChild(svgEl('circle', {cx:cx, cy:cy, r:r*.18, fill:'var(--gauge-needle)'}));
  }

  /* ================================================================
     GenmonGauge — Radial instrument dial
     ================================================================ */
  var CX = 100, CY = 100, GR = 72;
  var SW_S = -135, SW_E = 135, SW = 270;

  function GenmonGauge(container, opts) {
    this.container = container;
    this.opts = $.extend({min:0, max:100, value:0, labels:[], zones:[],
      divisions:10, subdivisions:2, title:'', units:''}, opts);
    this.currentValue = this.opts.min;
    this._build();
    if (this.opts.value > this.opts.min) this.set(this.opts.value);
  }

  GenmonGauge.prototype._v2a = function(v) {
    var f = Math.max(0, Math.min(1, (v - this.opts.min) / (this.opts.max - this.opts.min)));
    return SW_S + f * SW;
  };

  GenmonGauge.prototype._build = function() {
    var o = this.opts, id = uid();
    var svg = svgEl('svg', {viewBox:'0 0 200 200', class:'gauge-svg', width:'100%', height:'100%'});
    makeDefs(svg, id);

    /* ---- Chrome bezel ---- */
    svg.appendChild(svgEl('circle', {cx:CX, cy:CY, r:97,
      fill:'var(--gauge-bezel-edge)'}));
    svg.appendChild(svgEl('circle', {cx:CX, cy:CY, r:96,
      fill:'url(#bzl-'+id+')'}));
    svg.appendChild(svgEl('circle', {cx:CX, cy:CY, r:96,
      fill:'url(#bzr-'+id+')'}));
    /* Inner bezel shadow ring */
    svg.appendChild(svgEl('circle', {cx:CX, cy:CY, r:84,
      fill:'none', stroke:'var(--gauge-bezel-inner)', 'stroke-width':'1'}));

    /* ---- Face ---- */
    svg.appendChild(svgEl('circle', {cx:CX, cy:CY, r:83,
      fill:'url(#fc-'+id+')'}));

    /* ---- Color zone arcs (outer edge of face) ---- */
    if (o.zones && o.zones.length) {
      for (var i = 0; i < o.zones.length; i++) {
        var z = o.zones[i];
        var a1 = this._v2a(Math.max(z.from, o.min));
        var a2 = this._v2a(Math.min(z.to, o.max));
        if (a2 <= a1) continue;
        svg.appendChild(svgEl('path', {d:arc(CX,CY,76,a1,a2),
          fill:'none', stroke:z.color, 'stroke-width':'5',
          'stroke-linecap':'butt', opacity:'var(--gauge-zone-op)'}));
      }
    }

    /* ---- Tick marks ---- */
    if (o.divisions > 0) {
      var tot = o.divisions * o.subdivisions;
      for (var t = 0; t <= tot; t++) {
        var frac = t / tot, ang = SW_S + frac * SW;
        var major = (t % o.subdivisions === 0);
        var r1 = major ? 56 : 66, r2 = 73;
        var p1 = pol(CX,CY,r1,ang), p2 = pol(CX,CY,r2,ang);
        svg.appendChild(svgEl('line', {x1:p1.x, y1:p1.y, x2:p2.x, y2:p2.y,
          stroke: major ? 'var(--gauge-tick-major)' : 'var(--gauge-tick-minor)',
          'stroke-width': major ? '2' : '.7', 'stroke-linecap':'butt'}));
      }
    }

    /* ---- Labels ---- */
    if (o.labels && o.labels.length) {
      for (var l = 0; l < o.labels.length; l++) {
        var lv = o.labels[l], la = this._v2a(lv), lp = pol(CX,CY,46,la);
        var lb = svgEl('text', {x:lp.x, y:lp.y+1,
          'text-anchor':'middle', 'dominant-baseline':'middle',
          fill:'var(--gauge-label-fill)', 'font-size':'10', 'font-weight':'600',
          'font-family':'system-ui, sans-serif'});
        lb.textContent = lv;
        svg.appendChild(lb);
      }
    }

    /* ---- Title on face ---- */
    if (o.title) {
      var tt = svgEl('text', {x:CX, y:CY-22, 'text-anchor':'middle',
        fill:'var(--gauge-title-fill)', 'font-size':'9', 'font-weight':'400',
        'font-family':'system-ui, sans-serif'});
      tt.textContent = o.title;
      svg.appendChild(tt);
    }

    /* ---- Needle (thin, with subtle shadow) ---- */
    var ng = svgEl('g', {filter:'url(#ns-'+id+')'});
    ng.style.transition = ANIM_T;
    ng.style.transformOrigin = CX+'px '+CY+'px';
    ng.style.willChange = 'transform';
    ng.appendChild(svgEl('polygon', {
      points:(CX-1.5)+','+CY+' '+CX+','+(CY-68)+' '+(CX+1.5)+','+CY,
      fill:'var(--gauge-needle)'}));
    ng.appendChild(svgEl('polygon', {
      points:(CX-3)+','+CY+' '+CX+','+(CY+10)+' '+(CX+3)+','+CY,
      fill:'var(--gauge-needle)', opacity:'.35'}));
    svg.appendChild(ng);
    this._needleG = ng;
    this._setAngle(this._v2a(o.min));

    /* ---- Center hub ---- */
    drawHub(svg, CX, CY, 7);

    /* ---- LCD display box ---- */
    svg.appendChild(svgEl('rect', {x:CX-22, y:CY+26, width:44, height:18, rx:3,
      fill:'var(--gauge-lcd-bg)', stroke:'var(--gauge-lcd-border)', 'stroke-width':'.5'}));
    var vt = svgEl('text', {x:CX, y:CY+35, 'text-anchor':'middle',
      'dominant-baseline':'central',
      fill:'var(--gauge-lcd-text)', 'font-size':'12', 'font-weight':'700',
      'font-family':'system-ui, sans-serif', 'letter-spacing':'.5',
      class:'gauge-val-text'});
    vt.textContent = '--';
    svg.appendChild(vt);
    this._valText = vt;

    /* Units below LCD */
    if (o.units) {
      var ut = svgEl('text', {x:CX, y:CY+52, 'text-anchor':'middle',
        fill:'var(--gauge-unit-fill)', 'font-size':'7', 'font-weight':'400',
        'font-family':'system-ui, sans-serif', 'letter-spacing':'1'});
      ut.textContent = o.units;
      svg.appendChild(ut);
    }

    this.container.innerHTML = '';
    this.container.appendChild(svg);
    this.svg = svg;
  };

  GenmonGauge.prototype._setAngle = function(d) {
    this._needleG.style.transform = 'rotate('+d+'deg)';
  };
  GenmonGauge.prototype.set = function(val) {
    val = parseFloat(val); if (isNaN(val)) return;
    val = Math.max(this.opts.min, Math.min(this.opts.max, val));
    this.currentValue = val;
    this._setAngle(this._v2a(val));
  };
  GenmonGauge.prototype.setLabel = function(t) { this._valText.textContent = t || '--'; };
  GenmonGauge.prototype.destroy = function() { this.container.innerHTML = ''; };


  /* ================================================================
     GenmonFuelGauge — Classic arc fuel gauge
     Inspired by Italian supercar instrument clusters.
     E on left, F on right, gas-pump icon, red danger zone.
     ================================================================ */
  var FCX = 100, FCY = 100, FR = 75;
  var FS = -120, FE = 120, FSW = 240;

  function GenmonFuelGauge(container, opts) {
    this.container = container;
    this.opts = $.extend({min:0, max:100, value:0, title:'', units:'%'}, opts);
    this.currentValue = this.opts.min;
    this._build();
  }

  GenmonFuelGauge.prototype._v2a = function(v) {
    var f = Math.max(0, Math.min(1, (v - this.opts.min) / (this.opts.max - this.opts.min)));
    return FS + f * FSW;
  };

  GenmonFuelGauge.prototype._build = function() {
    var o = this.opts, id = uid();
    var svg = svgEl('svg', {viewBox:'0 0 200 165', class:'gauge-svg fuel-gauge-svg',
      width:'100%', height:'100%'});
    makeDefs(svg, id);

    /* Bezel arc band (thick dark metallic) */
    svg.appendChild(svgEl('path', {d:arc(FCX,FCY,FR,FS,FE),
      fill:'none', stroke:'url(#bzl-'+id+')', 'stroke-width':'28', 'stroke-linecap':'round'}));
    svg.appendChild(svgEl('path', {d:arc(FCX,FCY,FR,FS,FE),
      fill:'none', stroke:'var(--gauge-face-ring)', 'stroke-width':'24', 'stroke-linecap':'round'}));

    /* Face arc */
    svg.appendChild(svgEl('path', {d:arc(FCX,FCY,FR,FS,FE),
      fill:'none', stroke:'url(#fc-'+id+')', 'stroke-width':'20', 'stroke-linecap':'round'}));

    /* Red danger zone near E (first 20 %) */
    svg.appendChild(svgEl('path', {d:arc(FCX,FCY,FR,FS,FS+FSW*.2),
      fill:'none', stroke:'#ef4444', 'stroke-width':'8', 'stroke-linecap':'butt', opacity:'var(--gauge-zone-op)'}));

    /* Tick marks — 10 divisions */
    for (var t = 0; t <= 10; t++) {
      var f = t / 10, ang = FS + f * FSW, maj = (t % 2 === 0);
      var r1 = maj ? FR-14 : FR-8, r2 = FR-1;
      var p1 = pol(FCX,FCY,r1,ang), p2 = pol(FCX,FCY,r2,ang);
      svg.appendChild(svgEl('line', {x1:p1.x, y1:p1.y, x2:p2.x, y2:p2.y,
        stroke: maj ? 'var(--gauge-tick-major)' : 'var(--gauge-tick-minor)',
        'stroke-width': maj ? '1.2' : '.5', 'stroke-linecap':'round'}));
    }

    /* "E" label (dark red) */
    var ep = pol(FCX, FCY, FR+20, FS);
    var eT = svgEl('text', {x:ep.x, y:ep.y+2,
      'text-anchor':'middle', 'dominant-baseline':'middle',
      fill:'#b91c1c', 'font-size':'16', 'font-weight':'700',
      'font-family':'system-ui, sans-serif'});
    eT.textContent = 'E';
    svg.appendChild(eT);

    /* "F" label */
    var fp = pol(FCX, FCY, FR+20, FE);
    var fT = svgEl('text', {x:fp.x, y:fp.y+2,
      'text-anchor':'middle', 'dominant-baseline':'middle',
      fill:'var(--gauge-fuel-f)', 'font-size':'16', 'font-weight':'700',
      'font-family':'system-ui, sans-serif'});
    fT.textContent = 'F';
    svg.appendChild(fT);

    /* Gas-pump icon (centred watermark) */
    var pg = svgEl('g', {transform:'translate('+(FCX-12)+','+(FCY-46)+') scale(1.6)', opacity:'var(--gauge-fuel-icon-op)', fill:'var(--gauge-fuel-icon)'});
    /* Pump body */
    pg.appendChild(svgEl('path', {d:'M3,4 C3,2.9 3.9,2 5,2 L13,2 C14.1,2 15,2.9 15,4 L15,24 L3,24 Z'}));
    /* Nozzle window */
    pg.appendChild(svgEl('rect', {x:'5.5', y:'5', width:'7', height:'5', rx:'1',
      fill:'none', stroke:'var(--gauge-fuel-icon)', 'stroke-width':'.7', opacity:'.45'}));
    /* Base plate */
    pg.appendChild(svgEl('rect', {x:'1', y:'24', width:'16', height:'2.5', rx:'1.2'}));
    /* Hose arm */
    pg.appendChild(svgEl('path', {d:'M15,8 L18,5 L18,1', fill:'none', stroke:'var(--gauge-fuel-icon)',
      'stroke-width':'1.6', 'stroke-linecap':'round', 'stroke-linejoin':'round'}));
    /* Hose drop down & nozzle */
    pg.appendChild(svgEl('path', {d:'M18,5 L18,18 Q18,21 15.5,21', fill:'none', stroke:'var(--gauge-fuel-icon)',
      'stroke-width':'1.1', 'stroke-linecap':'round', opacity:'.55'}));
    /* Nozzle tip */
    pg.appendChild(svgEl('path', {d:'M15.5,21 L13,21 L12,23', fill:'none', stroke:'var(--gauge-fuel-icon)',
      'stroke-width':'1.1', 'stroke-linecap':'round', opacity:'.55'}));
    /* Small circle at hose pivot */
    pg.appendChild(svgEl('circle', {cx:'18', cy:'1', r:'1.5', fill:'var(--gauge-fuel-icon)', opacity:'.4'}));
    svg.appendChild(pg);

    /* Needle + tail (thin, matching radial style) */
    var ng = svgEl('g', {filter:'url(#ns-'+id+')'});
    ng.style.transition = ANIM_T;
    ng.style.transformOrigin = FCX+'px '+FCY+'px';
    ng.style.willChange = 'transform';
    ng.appendChild(svgEl('polygon', {
      points:(FCX-1.5)+','+FCY+' '+FCX+','+(FCY-FR+14)+' '+(FCX+1.5)+','+FCY,
      fill:'var(--gauge-needle)'}));
    ng.appendChild(svgEl('polygon', {
      points:(FCX-3)+','+FCY+' '+FCX+','+(FCY+10)+' '+(FCX+3)+','+FCY,
      fill:'var(--gauge-needle)', opacity:'.35'}));
    svg.appendChild(ng);
    this._needleG = ng;
    this._setAngle(this._v2a(o.min));

    /* Center hub */
    drawHub(svg, FCX, FCY, 7);

    /* LCD value display */
    svg.appendChild(svgEl('rect', {x:FCX-20, y:FCY+18, width:40, height:16, rx:3,
      fill:'var(--gauge-lcd-bg)', stroke:'var(--gauge-lcd-border)', 'stroke-width':'.5'}));
    var vt = svgEl('text', {x:FCX, y:FCY+29, 'text-anchor':'middle',
      fill:'var(--gauge-lcd-text)', 'font-size':'11', 'font-weight':'700',
      'font-family':'system-ui, sans-serif'});
    vt.textContent = '--';
    svg.appendChild(vt);
    this._valText = vt;

    this.container.innerHTML = '';
    this.container.appendChild(svg);
  };

  GenmonFuelGauge.prototype._setAngle = function(d) {
    this._needleG.style.transform = 'rotate('+d+'deg)';
  };
  GenmonFuelGauge.prototype.set = function(val) {
    val = parseFloat(val); if (isNaN(val)) return;
    val = Math.max(this.opts.min, Math.min(this.opts.max, val));
    this.currentValue = val;
    this._setAngle(this._v2a(val));
  };
  GenmonFuelGauge.prototype.setLabel = function(t) { this._valText.textContent = t || '--'; };
  GenmonFuelGauge.prototype.destroy = function() { this.container.innerHTML = ''; };


  /* ================================================================
     GenmonHBar — Horizontal sport-bar gauge (SVG)
     ================================================================ */
  function GenmonHBar(container, opts) {
    this.container = container;
    this.opts = $.extend({min:0, max:100, value:0, title:'', units:'',
      zones:[], labels:[]}, opts);
    this.currentValue = this.opts.min;
    this._build();
  }

  GenmonHBar.prototype._build = function() {
    var o = this.opts;
    var svg = svgEl('svg', {viewBox:'0 0 180 42', class:'hbar-gauge-svg',
      width:'100%', preserveAspectRatio:'xMidYMid meet'});

    /* Track background */
    svg.appendChild(svgEl('rect', {x:'0', y:'6', width:'180', height:'18', rx:'9',
      fill:'var(--gauge-track-bg)', stroke:'var(--gauge-track-ring)', 'stroke-width':'.5'}));
    svg.appendChild(svgEl('rect', {x:'1', y:'7', width:'178', height:'8', rx:'4',
      fill:'var(--gauge-track-hl)'}));

    /* Zone hints */
    if (o.zones && o.zones.length) {
      var range = o.max - o.min;
      for (var zi = 0; zi < o.zones.length; zi++) {
        var z = o.zones[zi];
        var x1 = ((z.from - o.min) / range) * 174 + 3;
        var x2 = ((z.to   - o.min) / range) * 174 + 3;
        svg.appendChild(svgEl('rect', {x:x1, y:'8', width:Math.max(0, x2-x1), height:'14',
          fill:z.color, opacity:'.12'}));
      }
    }

    /* Fill bar */
    var fill = svgEl('rect', {x:'3', y:'8', width:'0', height:'14', rx:'7',
      fill:'var(--accent)'});
    fill.style.transition = 'width '+ANIM_D+', fill 400ms ease';
    svg.appendChild(fill);
    this._fill = fill;
    this._maxW = 174;

    /* Segment marks */
    for (var s = 1; s < 10; s++) {
      svg.appendChild(svgEl('line', {x1:s*18, y1:'8', x2:s*18, y2:'22',
        stroke:'var(--gauge-segment)', 'stroke-width':'.5'}));
    }

    /* Min / max labels */
    var ml = svgEl('text', {x:'3', y:'37', 'text-anchor':'start',
      fill:'var(--gauge-label-fill)', 'font-size':'9.5',
      'font-family':'system-ui, sans-serif', 'font-weight':'400'});
    ml.textContent = o.min;
    svg.appendChild(ml);

    var xl = svgEl('text', {x:'177', y:'37', 'text-anchor':'end',
      fill:'var(--gauge-label-fill)', 'font-size':'9.5',
      'font-family':'system-ui, sans-serif', 'font-weight':'400'});
    xl.textContent = o.max + (o.units ? ' ' + o.units : '');
    svg.appendChild(xl);

    this._zones = o.zones;
    this.container.innerHTML = '';
    this.container.appendChild(svg);
  };

  GenmonHBar.prototype._zc = function(val) {
    for (var i = 0; i < this._zones.length; i++) {
      var z = this._zones[i];
      if (val >= z.from && val <= z.to) return z.color;
    }
    return 'var(--accent)';
  };
  GenmonHBar.prototype.set = function(val) {
    val = parseFloat(val); if (isNaN(val)) return;
    var o = this.opts;
    val = Math.max(o.min, Math.min(o.max, val));
    this.currentValue = val;
    this._fill.setAttribute('width', Math.max(2, ((val-o.min)/(o.max-o.min))*this._maxW));
    this._fill.setAttribute('fill', this._zc(val));
  };
  GenmonHBar.prototype.setLabel = function() {};
  GenmonHBar.prototype.destroy = function() { this.container.innerHTML = ''; };


  /* ================================================================
     GenmonArc — Speedometer-style top arc gauge (9 o'clock → 3 o'clock)
     ================================================================ */
  var ACX = 100, ACY = 105, AR = 78;
  var ARC_START = -180, ARC_END = 0; /* top semicircle: 9 o'clock to 3 o'clock */

  function GenmonArc(container, opts) {
    this.container = container;
    this.opts = $.extend({min:0, max:100, value:0, title:'', units:'',
      zones:[]}, opts);
    this.currentValue = this.opts.min;
    this._build();
  }

  GenmonArc.prototype._build = function() {
    var o = this.opts, id = uid();
    var svg = svgEl('svg', {viewBox:'0 0 200 120', class:'arc-gauge-svg',
      width:'100%', height:'100%'});

    /* Defs: glow filter, clip path, gradient */
    var defs = svgEl('defs');
    /* Glow-only filter (blur only, no source merge).  Uses a generous
       userSpaceOnUse region so the blur is never truncated by the
       filter's bounding rectangle. */
    var gf = svgEl('filter', {id:'ag-'+id, filterUnits:'userSpaceOnUse',
      x:'-50', y:'-50', width:'300', height:'300'});
    gf.appendChild(svgEl('feGaussianBlur', {'in':'SourceGraphic', stdDeviation:'3'}));
    defs.appendChild(gf);
    /* Clip: prevents the glow layer from bleeding far below the hub.
       Height extends half a stroke-width past ACY so the glow fades
       naturally rather than producing a hard visible edge. */
    var acp = svgEl('clipPath', {id:'vaclip-'+id});
    acp.appendChild(svgEl('rect', {x:'0', y:'0', width:'200', height:String(ACY+7)}));
    defs.appendChild(acp);
    /* Gradient for the value arc */
    var lg = svgEl('linearGradient', {id:'arcg-'+id, x1:'0', y1:'0', x2:'1', y2:'0'});
    lg.appendChild(svgEl('stop', {offset:'0%',   'stop-color':'#22d3ee'}));
    lg.appendChild(svgEl('stop', {offset:'50%',  'stop-color':'#3b82f6'}));
    lg.appendChild(svgEl('stop', {offset:'100%', 'stop-color':'#a855f7'}));
    defs.appendChild(lg);
    svg.appendChild(defs);
    this._gradId = 'arcg-'+id;

    /* Outer bezel track */
    svg.appendChild(svgEl('path', {d:_dArc(ACX,ACY,AR,ARC_START,ARC_END),
      fill:'none', stroke:'var(--gauge-track-bg)', 'stroke-width':'20', 'stroke-linecap':'round'}));

    /* Zone background arcs */
    if (o.zones && o.zones.length) {
      for (var zi = 0; zi < o.zones.length; zi++) {
        var z = o.zones[zi];
        var sa = ARC_START + ((z.from - o.min) / (o.max - o.min)) * (ARC_END - ARC_START);
        var ea = ARC_START + ((z.to   - o.min) / (o.max - o.min)) * (ARC_END - ARC_START);
        svg.appendChild(svgEl('path', {d:_dArc(ACX,ACY,AR,sa,ea),
          fill:'none', stroke:z.color, 'stroke-width':'16',
          'stroke-linecap':'butt', opacity:'.3'}));
      }
    } else {
      svg.appendChild(svgEl('path', {d:_dArc(ACX,ACY,AR,ARC_START,ARC_END),
        fill:'none', stroke:'var(--gauge-face-ring)', 'stroke-width':'16', 'stroke-linecap':'round'}));
    }

    /* Tick marks — 10 divisions with numbers */
    for (var t = 0; t <= 10; t++) {
      var frac = t / 10;
      var angDeg = ARC_START + frac * (ARC_END - ARC_START);
      var rad = angDeg * Math.PI / 180;
      var maj = (t % 2 === 0);
      var innerR = AR + 1;
      var outerR = maj ? AR + 10 : AR + 6;
      var cs = Math.cos(rad), sn = Math.sin(rad);
      svg.appendChild(svgEl('line', {
        x1:ACX+innerR*cs, y1:ACY+innerR*sn, x2:ACX+outerR*cs, y2:ACY+outerR*sn,
        stroke: maj ? 'var(--gauge-tick-major)' : 'var(--gauge-tick-minor)',
        'stroke-width': maj ? '1.5' : '.6', 'stroke-linecap':'round'}));
      /* Numeric labels at major ticks */
      if (maj) {
        var lv = o.min + frac * (o.max - o.min);
        var lr = AR + 20;
        var lt = svgEl('text', {x:ACX+lr*cs, y:ACY+lr*sn+1,
          'text-anchor':'middle', 'dominant-baseline':'middle',
          fill:'var(--gauge-label-fill)', 'font-size':'10',
          'font-family':'system-ui, sans-serif', 'font-weight':'500'});
        lt.textContent = Math.round(lv * 10) / 10;
        svg.appendChild(lt);
      }
    }

    /* Value arc — two layers so the glow can be clipped at the hub
       without truncating the crisp stroke itself.
       Layer 1: blur-only glow, clipped just below the hub line.
       Layer 2: clean stroke on top, never clipped. */
    var glowG = svgEl('g', {'clip-path':'url(#vaclip-'+id+')'});
    var ga = svgEl('path', {d:_dArc(ACX,ACY,AR,ARC_START,ARC_START),
      fill:'none', stroke:'url(#arcg-'+id+')', 'stroke-width':'12', 'stroke-linecap':'butt',
      filter:'url(#ag-'+id+')'});
    ga.style.transition = 'all ' + ANIM_D;
    glowG.appendChild(ga);
    svg.appendChild(glowG);
    this._glowArc = ga;

    var va = svgEl('path', {d:_dArc(ACX,ACY,AR,ARC_START,ARC_START),
      fill:'none', stroke:'url(#arcg-'+id+')', 'stroke-width':'12', 'stroke-linecap':'butt'});
    va.style.transition = 'all ' + ANIM_D;
    svg.appendChild(va);
    this._valArc = va;

    /* Needle — tapered polygon with counter-weight and glow */
    var nf = svgEl('filter', {id:'anf-'+id, x:'-50%', y:'-50%', width:'200%', height:'200%'});
    nf.appendChild(svgEl('feGaussianBlur', {'in':'SourceGraphic', stdDeviation:'1.5', result:'nb'}));
    var nm = svgEl('feMerge');
    nm.appendChild(svgEl('feMergeNode', {'in':'nb'}));
    nm.appendChild(svgEl('feMergeNode', {'in':'SourceGraphic'}));
    nf.appendChild(nm);
    defs.appendChild(nf);

    var ng = svgEl('g', {filter:'url(#anf-'+id+')'});
    ng.style.transition = 'transform ' + ANIM_D;
    ng.style.transformOrigin = ACX+'px '+ACY+'px';
    ng.style.willChange = 'transform';
    /* Main needle — tapered triangle pointing left (9 o'clock), rotated by set() */
    ng.appendChild(svgEl('polygon', {
      points:(ACX-AR+16)+','+ACY+' '+ACX+','+(ACY-2)+' '+ACX+','+(ACY+2),
      fill:'var(--gauge-needle)'}));
    /* Counter-weight tail */
    ng.appendChild(svgEl('polygon', {
      points:(ACX+10)+','+ACY+' '+ACX+','+(ACY-3)+' '+ACX+','+(ACY+3),
      fill:'var(--gauge-needle)', opacity:'.3'}));
    svg.appendChild(ng);
    this._needle = ng;

    /* Center hub — layered metallic look */
    svg.appendChild(svgEl('circle', {cx:ACX, cy:ACY, r:'6',
      fill:'var(--gauge-hub-1)', opacity:'.8'}));
    svg.appendChild(svgEl('circle', {cx:ACX, cy:ACY, r:'4',
      fill:'var(--gauge-needle)'}));
    svg.appendChild(svgEl('circle', {cx:ACX, cy:ACY, r:'2',
      fill:'var(--gauge-hub-dot)'}));

    /* Digital value — inside the arc */
    var vt = svgEl('text', {x:ACX, y:ACY-24, 'text-anchor':'middle',
      fill:'var(--gauge-val-fill)', 'font-size':'26', 'font-weight':'700',
      'font-family':'system-ui, sans-serif', 'letter-spacing':'.5'});
    vt.textContent = '--';
    svg.appendChild(vt);
    this._valText = vt;

    /* Units label */
    if (o.units) {
      var ut = svgEl('text', {x:ACX, y:ACY-10, 'text-anchor':'middle',
        fill:'var(--gauge-unit-fill)', 'font-size':'11', 'font-weight':'500',
        'font-family':'system-ui, sans-serif', 'letter-spacing':'1.5'});
      ut.textContent = o.units;
      svg.appendChild(ut);
    }

    this.container.innerHTML = '';
    this.container.appendChild(svg);
  };

  /* Arc helper — converts degree angles to SVG arc path */
  function _dArc(cx, cy, r, sa, ea) {
    var s = sa*Math.PI/180, e = ea*Math.PI/180;
    var x1=cx+r*Math.cos(s), y1=cy+r*Math.sin(s);
    var x2=cx+r*Math.cos(e), y2=cy+r*Math.sin(e);
    if (ea-sa <= 0) return 'M '+x1+' '+y1;
    return 'M '+x1+' '+y1+' A '+r+' '+r+' 0 '+(ea-sa>180?1:0)+' 1 '+x2+' '+y2;
  }

  GenmonArc.prototype._zc = function(val) {
    for (var i = 0; i < this.opts.zones.length; i++) {
      var z = this.opts.zones[i];
      if (val >= z.from && val <= z.to) return z.color;
    }
    return 'var(--accent)';
  };
  GenmonArc.prototype.set = function(val) {
    val = parseFloat(val); if (isNaN(val)) return;
    var o = this.opts;
    val = Math.max(o.min, Math.min(o.max, val));
    this.currentValue = val;
    var frac = (val - o.min) / (o.max - o.min);
    var endDeg = ARC_START + frac * (ARC_END - ARC_START);
    var d = _dArc(ACX,ACY,AR,ARC_START,endDeg);
    this._valArc.setAttribute('d', d);
    this._glowArc.setAttribute('d', d);
    var zc = this._zc(val);
    var stroke = zc === 'var(--accent)' ? 'url(#'+this._gradId+')' : zc;
    this._valArc.setAttribute('stroke', stroke);
    this._glowArc.setAttribute('stroke', stroke);
    /* Rotate needle — polygon drawn pointing left (= ARC_START direction) */
    this._needle.style.transform = 'rotate('+(endDeg - ARC_START)+'deg)';
  };
  GenmonArc.prototype.setLabel = function(t) { this._valText.textContent = t || '--'; };
  GenmonArc.prototype.destroy = function() { this.container.innerHTML = ''; };


  /* ---- Parsing helpers (unchanged API) ---- */
  GenmonGauge.parseZones = function(zones) {
    if (!zones) return [];
    if (Array.isArray(zones)) {
      return zones.map(function(z) {
        return {from:parseFloat(z.from||z.min||0), to:parseFloat(z.to||z.max||0),
                color:z.color||z.strokeStyle||'#ccc'};
      });
    }
    if (typeof zones === 'string') {
      var p = zones.trim().split(/\s+/), r = [];
      for (var i = 0; i+2 < p.length; i += 3)
        r.push({from:parseFloat(p[i]), to:parseFloat(p[i+1]), color:p[i+2]});
      return r;
    }
    return [];
  };

  GenmonGauge.parseLabels = function(labels) {
    if (!labels) return [];
    if (Array.isArray(labels)) return labels.map(Number);
    if (typeof labels === 'string') return labels.trim().split(/\s+/).map(Number);
    return [];
  };

  /* Exports */
  window.GenmonGauge      = GenmonGauge;
  window.GenmonFuelGauge  = GenmonFuelGauge;
  window.GenmonHBar       = GenmonHBar;
  window.GenmonArc        = GenmonArc;

})(window);
