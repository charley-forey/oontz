/* The page script: every command, the terminal, the clock wiring.
 *
 * This lived inline in index.html - 127KB of it - which meant the browser could
 * not paint the terminal shell until the whole thing had downloaded and run. The
 * markup above it is a complete, styled prompt; there was simply no way to reach
 * it. Out here it is one more `defer` script, so the shell paints first and every
 * script still runs in document order, which is the order this file needs.
 *
 * Loaded AFTER copy/legal/oontz/theory/ear/compose/viz/track and BEFORE
 * account/touch/mixer/midi, exactly as when it was inline. defer preserves that.
 */
"use strict";
var API = "https://api.oontz.sh";
/* If the custom domain's edge is having a day, fall back to the address that
   always works. Four seconds, once, at boot - then every call rides the winner. */
var API_FALLBACK = 'https://api-production-68c09.up.railway.app';
(function(){ var c = new AbortController(); setTimeout(function(){ c.abort(); }, 4000);
  fetch(API + '/health', {signal: c.signal}).catch(function(){ API = API_FALLBACK; }); })();

var CP = window.OONTZ_COPY || {}, CO = window.OONTZ_COMPOSE, OZ = window.oontz;
var OUT = document.getElementById('out'), IN = document.getElementById('in'),
    HUD = document.getElementById('hud'), RACK = document.getElementById('rack'),
    TAIL = document.getElementById('tail');
/* Quotes too: every data-cmd/data-t site below puts this INSIDE a double-quoted
   attribute, and a track name out of a stranger's published song is the value. */
var esc = function(s){ return String(s).replace(/[&<>"']/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
/* Autoscroll only when the reader is already at the bottom. Scrolling up is how
   you read what just went by; the log must not fight you for it. */
function atBottom(){ return OUT.scrollHeight - OUT.scrollTop - OUT.clientHeight < 24; }
function tail(){ OUT.scrollTop = OUT.scrollHeight; TAIL.classList.remove('on'); }
/* The scrollback had no ceiling. Every command, every jam turn and every render
   left a div behind for the session's lifetime, and #wrap paints all of them with
   a three-layer text-shadow halo - so an hour in, scrolling and typing were
   repainting thousands of glyphs that nobody was ever going to read again. */
var SCROLLBACK = 500;
function w(html, cls){ var stick = atBottom();
  var d=document.createElement('div'); if(cls)d.className=cls;
  d.innerHTML=html; OUT.appendChild(d);
  while(OUT.childElementCount > SCROLLBACK + 1)   /* +1: #slack, the top spacer, stays */
    OUT.removeChild(OUT.firstElementChild.id === 'slack' ? OUT.children[1] : OUT.firstElementChild);
  if(stick) tail(); else TAIL.classList.add('on');
  return d; }
function line(s, cls){ return w(esc(s===undefined?'':s), cls); }
var sleep = function(ms){ return new Promise(function(r){ setTimeout(r,ms); }); };
async function type(s, cls, sp){ var d=w('',cls);
  for(var i=0;i<s.length;i++){ d.innerHTML+=esc(s[i]); OUT.scrollTop=OUT.scrollHeight;
    if(s[i]!==' ') await sleep(sp||9); } return d; }
function block(rows){ line();
  (rows||[]).forEach(function(r){
    if(!r || (!r.t && !r.s && !r.c)) return line();
    if(r.t) return w('<span class="'+(r.cls||'b')+'">'+esc(r.t)+'</span>');
    if(r.c) return w('  <span class="a">'+esc(r.c)+'</span>'+
      '   <span class="dim">'+esc(r.d||'')+'</span>');
    w('<span class="'+(r.cls||'')+'">'+esc(r.s)+'</span>');
  }); line(); }

/* ------------------------------------------------------------- the engine */
var E = new OZ.Engine();
if(window.OONTZ_VIZ) OONTZ_VIZ.start(E);
var song = null, token = localStorage.getItem('oontz_token') || '';
var NOWID = '', PLAYAT = 0;      /* which track is loaded, and when it started — for listen-through */

/* Nothing about sharing was observable before this: gtag carried a page view and
   not one custom event, so whether a link was ever minted, opened or played was
   unknowable. share_mint -> share_open -> share_play -> remix_from_share is the
   whole funnel, readable straight off a GA report. */
function ev(n, p){ try{ if(window.gtag) gtag('event', n, p || {});
                        if(window.OONTZ_TRACK) OONTZ_TRACK(n, p); }catch(e){} }

/* Tracks this browser shared before it had an account. The API hands back a claim
   token once, to the browser that made the song; signing in trades them for
   ownership. Kept small - this is a convenience, not a system of record. */
function keepClaim(tok){
  try{
    var a = JSON.parse(localStorage.getItem('oontz_claims') || '[]');
    a.push(tok); localStorage.setItem('oontz_claims', JSON.stringify(a.slice(-50)));
  }catch(e){}
}
async function claimAll(){
  var a = [];
  try{ a = JSON.parse(localStorage.getItem('oontz_claims') || '[]'); }catch(e){}
  if(!a.length || !token) return;
  try{
    var r = await fetch(API+'/songs/claim',{method:'POST',
      headers:{'content-type':'application/json','authorization':'Bearer '+token},
      body:JSON.stringify({claims:a})});
    var j = await r.json();
    localStorage.removeItem('oontz_claims');
    ev('claim', {n: j.claimed || 0, offered: a.length});
    if(j.claimed) line('▸ '+j.claimed+' track'+(j.claimed>1?'s':'')+' you shared before signing in '+
                       (j.claimed>1?'are':'is')+' now yours','ok');
  }catch(e){}
}

/* One link, handed over properly. The clipboard write is attempted and REPORTED,
   never assumed - the await that minted the link may already have spent the
   gesture some browsers demand for it. The send chip carries its own tap. */
function offerShare(url, title, note){
  var el = w('<span class="ok">▸ shared.</span> <a href="'+esc(url)+'" target="_blank" rel="noopener">'+
             esc(url)+'</a> <span class="dim cpy"></span>');
  var say = function(t){ var n = el.querySelector('.cpy'); if(n) n.textContent = t; };
  if(navigator.clipboard) navigator.clipboard.writeText(url)
    .then(function(){ say('· copied'); ev('share_copy'); })
    .catch(function(){ say('· select to copy'); });
  else say('· select to copy');
  if(navigator.share){
    var b = document.createElement('button');
    b.className = 'chip'; b.textContent = 'send it';
    b.onclick = function(){
      navigator.share({title: title || 'oontz', text: 'made this in oontz', url: url})
        .then(function(){ ev('share_native'); }).catch(function(){});
    };
    el.appendChild(b);
  }
  if(note) w('<span class="dim">  '+note+'</span>');
  return el;
}

/* Hand a file to the browser. Five places grew their own copy of this, and the one
   that did NOT - `source save` - printed a link and waited for a click, which on a
   phone quietly does nothing. Clicking it ourselves is what every other export
   already does; the revoke keeps a big WAV from pinning memory for the session. */
function saveBlob(blob, name){
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(function(){ URL.revokeObjectURL(a.href); }, 30000);
  return name;
}

/* The first mime this browser will actually record, most shareable first. mp4 leads
   deliberately: webm is what Chrome prefers, and Instagram and TikTok reject webm
   uploads, so a webm clip is a file you cannot post. */
function pickMime(list){
  if(!window.MediaRecorder) return null;
  for(var i = 0; i < list.length; i++)
    if(MediaRecorder.isTypeSupported(list[i])) return list[i];
  return null;
}
var CLIP_MIMES = ['video/mp4;codecs=avc1,mp4a', 'video/mp4',
                  'video/webm;codecs=vp9,opus', 'video/webm'];

/* Centre-crop a landscape canvas to the square a feed wants. Pure, because getting
   this subtly wrong ships a clip that is off-centre and nobody notices in review. */
function clipRect(vw, vh){
  var side = Math.min(vw, vh);
  return {sx: Math.round((vw - side) / 2), sy: Math.round((vh - side) / 2), s: side};
}

/* The standing resume. A browser can suspend the context at any moment - autoplay
   policy, a tab switch, an iOS call - and until now the only thing that ever resumed
   it was armPlay, which removed itself after one tap. So a page had exactly one
   chance to make sound in its whole life. This one never removes itself. */
OZ.armAudio(function(){ return [E && E.ctx]; });

/* A gesture happened and the context still is not running: this browser is never
   going to make a sound for this person. Said once, so the count is people. */
addEventListener('pointerdown', function ab(){
  removeEventListener('pointerdown', ab, true);
  setTimeout(function(){ if(E && E.ctx && E.ctx.state !== 'running') ev('audio_blocked', {state: E.ctx.state}); }, 1500);
}, true);

/* Arriving from somebody else's link. A browser will not let a page make noise
   without a gesture, so do not pretend: say what it is, then ask for the one tap.
   The alternative - what the share page used to do - is a timer that "plays" into
   a suspended context, and a visitor who concludes it is broken. */
/* The track a first-time visitor arrives holding. Hardcoded, not composed: this
   runs on the boot path we just spent a refactor clearing, and CO.compose is real
   CPU. It is also the exact song the README opens with, which is the point - ten
   lines of text that are a whole track, on screen, before anything is explained. */
function starterSong(){
  return {name: 'warehouse', bpm: 132, swing: 6, key: 'a', scale: 'minor',
    order: ['loop'],
    sections: {loop: {bars: 16, role: 'drop', energy: 0.8,
      order: ['kick', 'hat', 'oh', 'clap', 'bass'],
      tracks: {
        kick: {voice: 'kick', pat: 'X...x...X...x..x', gain: 1},
        hat:  {voice: 'hat',  pat: '..x...x...x.x.x.', gain: 0.8},
        oh:   {voice: 'oh',   pat: '......x.......x.', gain: 0.7},
        clap: {voice: 'clap', pat: '....x.......x...', gain: 0.9},
        bass: {voice: 'bass', pat: 'X.x.x.x.X.x.x.x.', gain: 1,
               notes: ['a1!', '.', 'a1~', '.', 'c2', '.', 'a1', '.',
                       'g1!', '.', 'a1~', '.', 'c2', '.', 'd2', '.']}
      }}}};
}

/* Wires the next gesture; prints NOTHING. It used to print a `▸ title meta` header
   and "tap anywhere to hear it" - but all three callers run it immediately after
   loadSong, which already announces the track and already prints that same line, so
   a first arrival was announced twice and told to tap twice. loadSong's line is the
   truthful one on every path, not just these three: OZ.armAudio() registers a
   capture-phase unlock that resumes the context on any gesture and never removes
   itself. What is left here is the part that was never visible - NOWID, the play
   count, the share_play event, and `then`. */
function armPlay(id, then){
  NOWID = id || '';
  var fired = false;
  var go = function(){
    if(fired) return; fired = true;
    document.removeEventListener('pointerdown', go, true);
    document.removeEventListener('keydown', go, true);
    E.start(); run('play'); ev('share_play', {id: id || ''});
    if(id) fetch(API+'/songs/'+encodeURIComponent(id)+'/play',{method:'POST'}).catch(function(){});
    if(then) then();                             /* the tap is step one; `then` asks for step two */
  };
  /* Already running - the tap has effectively happened, so `then` still owes its
     step two. loadSong prints no prompt in this case either; the two agree. */
  if(E.ctx && E.ctx.state === 'running') return go();
  document.addEventListener('pointerdown', go, true);
  document.addEventListener('keydown', go, true);
}


function mmss(s){ s = Math.max(0, Math.floor(s||0));
  return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
function songSeconds(sg){ if(!sg) return 0;
  return OZ.totalBars(sg) * 240 / (sg.bpm||138); }

function deckLine(d, name){
  if(!d.r) return '<span class="dim">'+name+'  empty · dload '+name+' this</span>';
  var ph = d.beatPhase(), beat = d.beat(), bar = Math.floor(beat/4)+1, m = d.r.marks, sec = '';
  for(var k = 0; k < m.length; k++) if(m[k][0] <= d.pos()+0.01) sec = m[k][1];
  var meter = ''; for(var q = 0; q < 8; q++) meter += (q < ph*8 ? '█' : '·');
  return '<span class="'+(DECKFOC===name?'a2':'dim')+'">'+name.toUpperCase()+'</span> '+
    '<span class="b">'+esc(String(d.r.name).slice(0,16).padEnd(16))+'</span><span class="dim"> '+
    d.bpm().toFixed(1)+' BPM  bar '+String(bar).padStart(3)+' '+esc(sec.padEnd(8))+' </span>'+
    '<span class="a">'+meter+'</span><span class="dim"> '+(d.playing?'▸':'■')+(d.loop?' loop':'')+
    ' kill '+['low','mid','high'].filter(function(b){ return d.kill[b]; }).join(' ')+'</span>';
}
/* draw() rebuilds the whole rack with innerHTML, and the clock called it on every
   16th note - ~9 full reparse+layout passes a second at 140bpm, landing on the same
   thread as your keystrokes and your scroll. drawSoon() coalesces the flood into one
   per frame. draw() itself stays synchronous: the thirty command handlers that call
   it once and then read the DOM back are not the problem and must not become one. */
var DRAWQ = 0;
function drawSoon(){ if(DRAWQ) return;
  DRAWQ = requestAnimationFrame(function(){ DRAWQ = 0; draw(); }); }
function draw(){
  var i = E.stepNow || 0, foc = E.focus || (E.order||[])[0];
  if(MODE === 'deck'){
    var D = E.decks(), g = OZ.xfGains(D.xf), xfbar = '';
    for(var q = 0; q < 21; q++) xfbar += (Math.round((D.xf+1)*10) === q ? '┃' : '─');
    HUD.innerHTML = deckLine(D.a,'a') + '<br>' + deckLine(D.b,'b') + '<br><span class="dim">A </span><span class="a2">'+
      xfbar+'</span><span class="dim"> B   ' + Math.round(g[0]*100) + '% / ' + Math.round(g[1]*100) + '%</span>';
    RACK.classList.remove('on');                 // the studio grid is not the deck
    return;
  }
  /* HUD: where we are in the whole song */
  if(song){
    var at = OZ.sectionAt(song, E.songbar), total = OZ.totalBars(song);
    var cells = '', acc = 0, barAt = 0, w0 = Math.max(20, Math.min(90, Math.floor(innerWidth/14)));
    song.order.forEach(function(n){
      var s = song.sections[n]; if(!s) return;
      var span = Math.max(1, Math.round(s.bars/total*w0));
      var col = {intro:'--dim', build:'--warn', drop:'--hot', break:'--accent',
                 verse:'--ok', outro:'--dim'}[s.role] || '--fg';
      var gl = s.energy>0.8?'█':(s.energy>0.5?'▓':'▒');
      for(var k=0;k<span;k++){ acc++;
        var here = at && n===at.name && Math.abs(acc - Math.round((E.songbar+1)/total*w0))<1;
        /* every cell knows which bar it is, so the map is a transport */
        cells += '<span class="sq" data-bar="'+Math.round(barAt + s.bars*k/span)+'" title="'+esc(n)+'" style="color:var('+col+')'+
          (here?';background:var('+col+');color:#000':'')+'">'+gl+'</span>'; }
      barAt += s.bars;
    });
    /* name the next section while it is still close enough to play towards */
    var soon = '';
    if(at){
      var lf = at.sec.bars - at.within;
      if(lf <= 4){
        var np = OZ.sectionAt(song, E.songbar + lf);
        if(np && np.name !== at.name)
          soon = ' <span class="w">→ '+esc(np.name)+' in '+lf+'</span>';
      }
    }
    HUD.innerHTML = '<span class="a2">'+esc(song.name)+'</span> <span class="dim">'+
      Math.round(song.bpm)+' BPM · '+esc(song.key+' '+song.scale)+' · bar '+
      (E.songbar+1)+'/'+total+' · '+mmss(songSeconds(song))+' · </span>'+
      (ROOM.code ? '<span class="a">room '+esc(ROOM.code)+' · '+(ROOM.others+1)+'</span> <span class="dim">· </span>' : '')+
      '<span class="b">'+esc(at?at.name:'')+'</span>'+soon+'<div class="map">'+cells+'</div>';
  }
  /* WHAT IS COMING. state_at() is pure, so the next section can be asked for its
     patterns before it arrives - the one thing no other instrument can draw, because
     no other one knows its own future. Only inside the last few bars though: shown
     always it is wallpaper, shown at the boundary it is a warning you can play to. */
  var LOOKAHEAD = 4, nx = null, nxIn = 0;
  if(song && at){
    var left = at.sec.bars - at.within;                  /* bars until the next section */
    if(left <= LOOKAHEAD){
      var ns = OZ.stateAt(song, E.songbar + left);       /* ONE call, shared by every lane */
      if(ns && ns.section !== at.name){ nx = ns; nxIn = left; }
    }
  }
  /* Is this track being moved right now, and which way? The rack's axis is steps
     inside a bar; automation's axis is bars inside a section. A curve drawn across
     the steps would be a lie, so the lane says only what is true on its own axis:
     that this track is moving, and where to. */
  function autoNow(sec, name, within){
    var a = sec.automation || [];
    for(var k = 0; k < a.length; k++){
      var x = a[k], t = String(x[0]);
      if(t.indexOf(name + '.') !== 0) continue;
      var start = Math.max(0, Math.min(x[3]|0, sec.bars - 1));
      var len = Math.max(1, Math.min(x[4] ? (x[4]|0) : (sec.bars - start), sec.bars - start));
      if(within >= start && within < start + len) return (+x[2] >= +x[1]) ? '▲' : '▼';
    }
    return '';
  }
  var COL = {kick:'--hot', hat:'--accent', oh:'--accent', clap:'--accent2',
             snare:'--warn', perc:'--ok', bass:'--warn', rumble:'--dim',
             pad:'--accent', riser:'--a2'};
  function lane(n, tr, ghost){
    var col = COL[n] || '--fg';
    var nt = nx && nx.tracks ? nx.tracks[n] : null;
    var cells = '';
    for(var q=0;q<16;q++){
      var ch = ghost ? '.' : (tr.pat[OZ.patIndex(tr.pat, E.songbar, q)] || '.');
      var on = ch !== '.' && ch !== '-';
      var maybeStep = ch === '?';
      var cur = !ghost && q === i && E.playing;
      /* the incoming pattern, read at the bar it actually starts on */
      var nOn = false;
      if(nt && nt.pat){
        var nch = nt.pat[OZ.patIndex(nt.pat, E.songbar + nxIn, q)] || '.';
        nOn = nch !== '.' && nch !== '-';
      }
      /* a track's own pattern restarting mid-bar: polymeter, finally visible */
      var wrap = !ghost && q > 0 && OZ.patIndex(tr.pat, E.songbar, q) === 0;
      cells += '<span class="'+(ghost?'gst':'st')+(on?' on':'')+(wrap?' wrap':'')+
        (nx && nOn && !on ? ' arr' : '')+(nx && nt && on && !nOn ? ' lea' : '')+'"'+
        (ghost?'':' data-t="'+esc(n)+'" data-i="'+q+'"')+
        ' style="color:var('+(on?col:'--dim')+')'+(maybeStep?';opacity:.55':'')+
        (cur?';background:var('+(on?col:'--line')+');color:#000':'')+'">'+
        (maybeStep?'▒':(on?'█':'·'))+'</span>';
    }
    var mark = ghost ? '' : autoNow(at ? at.sec : {}, n, at ? at.within : 0);
    return '<div'+(ghost?' class="ghost"':'')+' style="--tc:var('+col+')">'+
      '<span class="trk '+(ghost?'dim':(n===foc?'a2':'dim'))+'"'+(ghost?'':' data-t="'+esc(n)+'"')+'>'+
      (ghost?'+ ':(n===foc?'▸ ':'  '))+esc(n)+(mark?' '+mark:'')+'</span>'+cells+'</div>';
  }
  var h = '', shown = {};
  (E.order||[]).forEach(function(n){
    var tr = E.tracks[n]; if(!tr || !tr.pat) return;
    if(!tr.pat.replace(/[.\-]/g,'')) return;
    shown[n] = 1;
    h += lane(n, tr, false);
  });
  /* A voice the next section brings that is not playing yet gets its own ghost lane -
     this is the drop's bassline appearing before the drop does. */
  if(nx) (nx.order||[]).forEach(function(n){
    if(shown[n]) return;
    var nt = nx.tracks[n];
    if(!nt || !nt.pat || !nt.pat.replace(/[.\-]/g,'')) return;
    h += lane(n, nt, true);
  });
  RACK.innerHTML = h;
  RACK.classList.toggle('on', !!h);        // no rack until there is something in it
}

/* ------------------------------------------------------- psychedelic bg */
var cv=document.getElementById('bg'), cx=cv.getContext('2d'), W=0,H=0,tt=0;
/* Same rule as viz.js: measure the element, not the window. inset:0 keeps this
   canvas viewport-sized through every keyboard and fullscreen transition on its own;
   reading innerHeight once and pinning it in px is what left a black strip under the
   picture in watch mode. */
/* ponytail: DPR clamped to 1 for the background only. It is six blurred rings -
   nothing in it is a crisp edge - and at dpr 3 the full-viewport fill every frame
   costs 9x the pixels for a picture nobody can tell apart. Raise it if the bg ever
   grows text or a hairline. */
function size(){ var w=cv.clientWidth||innerWidth, h=cv.clientHeight||innerHeight;
  W=cv.width=Math.floor(w); H=cv.height=Math.floor(h); }
size(); addEventListener('resize', function(){ size(); draw(); });
try{ if(window.ResizeObserver) new ResizeObserver(function(){ size(); draw(); }).observe(cv); }catch(e){}
var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
var flash = 0, pulse = 0;                       // a drop lights the room; a kick pushes it
var ROLE_HUE = {drop: 330, break: 175, build: 40, intro: 210, outro: 210, verse: 130};
/* The same hidden gate viz.js uses. The idle drift stays - that ambience is the
   point - it is just not painted for a tab nobody is looking at. */
/* The second full-screen canvas on the page. Same bill as viz.js: six stroked
   rings and a full-viewport fill, sixty times a second, whether or not anything is
   playing. The ambient drift is the point and it stays - at a sixth of the frames
   when the room is quiet, which no eye can tell apart on a slow drift. */
var bgLast = 0;
/* Idle ambience does not need sixty frames a second. Nothing here moves to a beat
   when there is no beat, so a drift at ~13fps is the same picture for a sixth of
   the work - and idle is the state a first-time visitor judges the app in. */
function frame(ts){ requestAnimationFrame(frame); if(reduce || document.hidden) return;
  if(!E.playing){ if((ts || 0) - bgLast < 75) return; bgLast = ts || 0; }
  var spec = E.spectrum();
  var at = song && E.playing ? OZ.sectionAt(song, E.songbar) : null;
  var en = at ? (at.sec.energy || 0.5) : 0.3, role = at ? at.sec.role : '';
  var build = role === 'build' ? at.within / Math.max(1, at.sec.bars) : 0;
  tt += E.playing ? .01 + en * .03 * (1 + build) : .006;
  flash *= .9; pulse *= .85;
  cx.fillStyle='rgba(7,9,11,.17)'; cx.fillRect(0,0,W,H);
  if(flash > .01){ cx.fillStyle='rgba(255,79,163,'+(flash*.45)+')'; cx.fillRect(0,0,W,H); }
  var cxx=W/2, cyy=H/2, R=Math.hypot(W,H)*.42;   /* was min(W,H)*.44: a centred blob */
  var bass=0, air=0;
  if(spec){ for(var b=1;b<12;b++) bass+=spec[b]; bass/=11*255;
            for(var a2=300;a2<520;a2++) air+=spec[a2]; air/=220*255; }
  var hue0 = role in ROLE_HUE ? ROLE_HUE[role] : tt*45;
  for(var r=0;r<6;r++){
    var p=(tt*.45+r/6)%1, rad=R*p*(1+bass*.35+pulse*.15);
    cx.beginPath();
    for(var a=0;a<=72;a++){
      var th=a/72*Math.PI*2;
      var wob=1+Math.sin(th*(3+r)+tt*2.2)*(.10+air*.5+en*.08);
      var x=cxx+Math.cos(th)*rad*wob, y=cyy+Math.sin(th)*rad*wob*.66;
      a?cx.lineTo(x,y):cx.moveTo(x,y);
    }
    cx.closePath();
    cx.strokeStyle='hsla('+((hue0+tt*20+r*38)%360)+',85%,'+(55+bass*20)+'%,'+
      ((1-p)*(.12+en*.1+bass*.35))+')';
    cx.lineWidth=(1+en*1.5+bass*4); cx.stroke();
  }
}
frame();
E.onbar = function(bar, st){ if(st && st.role === 'drop' && st.within === 0) flash = 1; drawSoon(); };
E.onstep = function(i, tracks){ var k = tracks && tracks.kick;
  if(k && k.pat && !k.mute){ var ch = k.pat[OZ.patIndex(k.pat, E.songbar, i)]; if(ch && ch !== '.' && ch !== '-') pulse = 1; }
  drawSoon(); };

/* ------------------------------------------------------------- commands */
var LOGO = ["  ▄▄▄   ▄▄▄  ▄▄▄▄▄ ▄▄▄▄▄ ▄▄▄▄▄▄     ▄▄▄▄ █    ",
            " █   █ █   █ █   █   █       ▄▀      █    █    ",
            " █   █ █   █ █   █   █     ▄▀        ▀▀▀▄ █▄▄▄ ",
            " █   █ █   █ █   █   █   ▄▀        ▄    █ █   █",
            "  ▀▀▀   ▀▀▀  ▀   ▀   ▀   ▀▀▀▀▀▀   ▀ ▀▀▀▀ ▀   ▀"];

/* `nograde` exists for exactly one caller: the first-run arrival. The grader marks
   ARRANGEMENTS - sections, energy curve, where the drop lands - and the starter is
   deliberately a sixteen-bar loop, which it scores 12/100. Telling a stranger the
   track they have not yet heard is 12/100 is a bad five seconds and, worse, it is
   not even the question being asked. `grade` still answers honestly on demand. */
function loadSong(sg, why, nograde){
  REMIX_OF = null;                               /* a fresh song owes nobody, until `remix` says so */
  SHARED_ID = '';                                /* nor is it the song the last link points at */
  /* play() reports the context state now. Printing the banner regardless of it is
     what made `go` look like it had worked while nothing reached the speakers. */
  song = sg; E.loadSong(sg); var live = E.play() === 'running';
  if(window.OONTZ_VIZ) OONTZ_VIZ.song(sg);
  var crit = CO.critique(sg), sc = CO.score(crit);
  line();
  w('<span class="a2">▸ '+esc(sg.name)+'</span> <span class="dim">'+
    OZ.totalBars(sg)+' bars · '+mmss(songSeconds(sg))+' · '+Math.round(sg.bpm)+
    ' BPM · '+esc(sg.key+' '+sg.scale)+' · '+sg.order.length+' sections</span>');
  w('<span class="dim">  '+esc(sg.order.join(' → '))+'</span>');
  if(!nograde)
    w('<span class="'+(sc>75?'ok':(sc>45?'w':'hot'))+'">  theory says '+sc+'/100</span>'+
      '<span class="dim">   type <span class="a">grade</span> for the full verdict</span>');
  if(why) w('<span class="dim">  '+esc(why)+'</span>');
  if(!live) w('<span class="a">  ▶ ' + esc(CP.first_tap || 'tap anywhere to hear it') + '</span>');
  line();
  draw();
}

var CMDS = {
  help: function(){ line();
    (CP.help||[]).forEach(function(kv){
      w('  <span class="k">'+esc(kv[0])+'</span><span class="dim">'+esc(kv[1])+'</span>'); });
    line(); },
  what: function(){ block(CP.what); },
  theory: function(){ block(CP.theory); },
  rules: function(a){ var T = window.OONTZ_THEORY, sets = {arrangement:T.arrangement, mixing:T.mixing, dj:T.dj};
    var which = (a[0]||'').toLowerCase(), keys = sets[which] ? [which] : Object.keys(sets); line();
    keys.forEach(function(k){ w('<span class="b">'+k+'</span>');
      sets[k].forEach(function(r){ w('  <span class="a">'+esc(r.rule)+'</span>'); w('    <span class="dim">'+esc(r.why)+'</span>'); }); line(); }); },
  bands: function(){ var T = window.OONTZ_THEORY; line();
    Object.keys(T.freq_roles).forEach(function(k){ var v = T.freq_roles[k];
      w('  <span class="k">'+esc(k+'  '+v.hz[0]+'-'+v.hz[1]+' Hz')+'</span><span class="dim">'+esc(v.note)+'</span>'); }); line(); },
  /* `decks` used to print an essay whose first line was "Press M" - which is the
     one instruction a phone cannot follow. It is a verb now, like `share`; the
     essay is one word away at `decks why`. */
  decks: function(a){ if(a && a[0] === 'why') return block(CP.decks);
    return CMDS.mode([MODE === 'deck' ? 'studio' : 'deck']); },
  keys: function(){ block(CP.keys); },
  ai: function(){ block(CP.ai); },
  /* `share` used to print an essay about sharing. It is a verb now; the essay is
     still one word away at `share why`. */
  share: async function(a){
    if(a[0] === 'why') return block(CP.share);
    if(a[0] === 'link') return CMDS.link([]);
    if(!song) return line(CP.err_nosong,'w');
    var d = w('<span class="dim">  minting a link…</span>');
    try{
      var hdr = {'content-type':'application/json'};
      if(token) hdr.authorization = 'Bearer ' + token;
      var r = await fetch(API+'/songs',{method:'POST', headers:hdr,
        body:JSON.stringify({title:song.name, data:Object.assign({format:'oontz-song-1'}, song),
                             public:true, remix_of:REMIX_OF||undefined,
                             id:SHARED_ID||undefined})});
      var j = await r.json(); d.remove();
      if(!j.id) return line('▸ '+((j.detail && j.detail[0] && j.detail[0].msg) || j.error ||
                                  j.detail || 'could not share'),'w');
      if(j.claim) keepClaim(j.claim);
      SHARED_URL = String(j.url||'').replace(/^https?:\/\//,'');
      SHARED_ID = j.id || '';            /* share again and it edits this one, not a namesake */
      ev('share_mint', {kind:'server', anon: token ? 0 : 1});
      offerShare(j.url, song.name,
        'anyone who opens it hears it and can flip it. <span class="a">clip</span> makes a video of it.' +
        (token ? '' : ' <span class="a">login</span> puts your name on it.'));
      var shot = 'https://oontz.music/t/'+j.id+'?watch=1';
      w('<span class="dim">  or as a light show: </span><a href="'+esc(shot)+
        '" target="_blank" rel="noopener">'+esc(shot)+'</a>');
    }catch(e){ d.remove(); line('could not reach the server','w'); }
  },
  /* The same song with nobody in the middle: the whole track rides in the URL's
     fragment, so no server ever sees it and there is nothing to store or lose. */
  link: async function(){
    if(!song) return line(CP.err_nosong,'w');
    try{
      var p = await OZ.packSong(Object.assign({format:'oontz-song-1'}, song));
      var url = 'https://oontz.sh/#s=' + p;
      if(url.length > 8000)
        return line('that arrangement is too big for a URL — `share` puts it on the server','w');
      ev('share_mint', {kind:'url', chars: url.length});
      offerShare(url, song.name, 'that link IS the song — no account, no server, works forever.');
      if(url.length > 1500)
        line('  (a long one. `share` gives a short link that also previews.)','dim');
    }catch(e){ line('could not pack that song','w'); }
  },
  free: function(){ block(CP.free); },
  terms: function(){ block(OONTZ_LEGAL.terms); },
  privacy: function(){ block(OONTZ_LEGAL.privacy); },
  /* track.js reads the flag once at load, so this cannot stop a tracker that is
     already running - say so instead of pretending. */
  /* Typing anything already lands in prompt_submit, so this is not a new pipe -
     it is a findable name for the one that exists, and an acknowledgement, which
     is the half that makes someone bother saying anything at all. Honours notrack
     and DNT like everything else, because ev() does. */
  feedback: function(a){
    var t = a.join(' ').trim().slice(0, 500);
    if(!t) return line('feedback <what you think> · good, bad, what broke. no account needed.','w');
    ev('feedback', {text: t, chars: t.length});
    line('▸ got it. thank you — these get read.','ok');
  },
  notrack: function(){
    var off;
    try{
      off = !localStorage.getItem('oontz_notrack');
      if(off){ localStorage.setItem('oontz_notrack','1'); localStorage.removeItem('oontz_did'); }
      else localStorage.removeItem('oontz_notrack');
    }catch(e){ return line('this browser will not let me write that flag','w'); }
    line(off ? '▸ tracking off. reload and nothing in `privacy` section 4 is collected here again.'
             : '▸ tracking back on. reload and it resumes.', off ? 'ok' : 'dim');
    line('  do not track is honoured too, and `notrack` again flips this back.','dim');
  },
  /* The long form lives on the other site, where you can scroll. This is the
     pointer, not a copy of it. */
  language: function(){ line();
    w('<span class="b">  The Song Is the Source</span>');
    w('<span class="dim">  notes toward an audio programming language. history, theory,</span>');
    w('<span class="dim">  semantics, architecture, metaphors, and a checklist you can build</span>');
    w('<span class="dim">  your own from. ~21,000 words, written to be forked.</span>');
    w('  <a href="https://oontz.music/language" target="_blank" rel="noopener">oontz.music/language →</a>');
    line(); },
  repo: function(){ line();
    w('<span class="dim">  every line of this, including the synth:</span>');
    w('  <a href="https://github.com/charley-forey/oontz" target="_blank" rel="noopener">github.com/charley-forey/oontz →</a>');
    w('<span class="dim">  the format lives in docs/OONTZ-FORMAT.md. take the lot.</span>');
    line(); },
  go: function(){ CMDS.compose(['hardtechno','5']); },
  compose: function(a){
    var style=(a[0]||'hardtechno').toLowerCase();
    var mins=parseFloat(a[1])||5, curve=(a[2]||'').toLowerCase();   // blank = let the seed choose
    if(!CO.GENRES[style]) return line('styles: '+Object.keys(CO.GENRES).join(' '),'w');
    loadSong(CO.compose(style, Math.max(1,Math.min(12,mins)), curve),
             CO.GENRES[style].note);
  },
  styles: function(){ line();
    Object.keys(CO.GENRES).forEach(function(k){
      var G=CO.GENRES[k];
      w('  <span class="k">'+esc(k)+'</span><span class="dim">'+G.bpm+' BPM · '+
        esc(G.note)+'</span>'); }); line(); },
  curves: function(){ line();
    Object.keys(CO.TEMPLATES).forEach(function(k){
      w('  <span class="k">'+esc(k)+'</span><span class="dim">'+
        esc(CO.TEMPLATES[k].join(' → '))+'</span>'); }); line(); },
  /* Two halves: how it is built, and how it sounds. The second one renders the
     loudest section and measures it, so every line carries a number. */
  grade: async function(a){
    if(!song) return line(CP.err_nosong,'w');
    var crit=CO.critique(song), sc=CO.score(crit); line();
    w('<span class="b">'+esc(song.name)+' — arrangement '+sc+'/100</span>'); line();
    crit.forEach(function(c){ w(sev(c[0]) + esc(c[1]) + '</span>'); });
    if(a && a[0]==='arrangement') return line();
    line();
    var pr = w('<span class="dim">  listening…</span>');
    try{
      var m = await EAR.measure(song); EARLAST = m;
      var mix = EAR.critiqueMix(m), ms = CO.score(mix);
      pr.remove();
      w('<span class="b">the mix — '+ms+'/100</span> <span class="dim">measured on <span class="a">'+
        esc(m.section)+'</span>, the loudest section</span>'); line();
      mix.forEach(function(c){ w(sev(c[0]) + esc(c[1]) + '</span>'); });
      line(); EAR.table(m).forEach(function(r){ w('<span class="dim">  '+esc(r)+'</span>'); });
      line();
      w('<span class="dim">  <span class="a">improve</span> will fix the worst of it and measure again.</span>');
      line();
    }catch(e){ pr.remove(); line('  could not render to listen: '+(e.message||e),'w'); }
  },
  /* Render, grade, fix the worst thing, render again. Stops when the score stops
     rising. No model call: theory plus measurement, on your machine. */
  improve: async function(a){
    if(!song) return line(CP.err_nosong,'w');
    var rounds = Math.max(1, Math.min(12, parseInt(a[0],10) || 6));
    snapshot('improve'); line();
    w('<span class="b">improving '+esc(song.name)+'</span> <span class="dim">render → measure → fix the worst → again</span>');
    var last = -1, stall = 0, first = null, i;
    for(i = 1; i <= rounds; i++){
      var pr = w('<span class="dim">  ['+i+'] listening…</span>');
      var m, sc;
      try{ m = await EAR.measure(song); EARLAST = m;
        sc = CO.score(EAR.critiqueMix(m)); }
      catch(e){ pr.remove(); line('  could not render: '+(e.message||e),'w'); break; }
      if(first === null) first = sc;
      pr.innerHTML = '<span class="dim">  ['+i+'] mix '+sc+'/100</span>';
      /* One flat round is normal - a fix can clear a fault without moving the
         score until the next one lands. Two in a row means it is done. */
      if(sc <= last){ if(++stall >= 2){ w('<span class="dim">  no further gain — stopping.</span>'); break; } }
      else stall = 0;
      last = Math.max(last, sc);
      var did = EAR.fixWorst(song, m);
      if(!did){ w('<span class="ok">  nothing left to fix at this threshold.</span>'); break; }
      w('<span class="a">  → '+esc(did)+'</span>');
      E.jump(E.songbar);                       // the live engine picks the edit up
    }
    try{ var fm = await EAR.measure(song); EARLAST = fm;
      var fs = CO.score(EAR.critiqueMix(fm));
      w('<span class="'+(fs>first?'ok':'dim')+'">  mix '+first+' → '+fs+'/100</span>');
    }catch(e){}
    line(); w('<span class="dim">  <span class="a">grade</span> for the full verdict · <span class="a">undo</span> puts it back</span>'); line();
    draw();
  },
  freq: async function(){ if(!song) return line(CP.err_nosong,'w');
    var pr = w('<span class="dim">  listening…</span>');
    try{ var m = await EAR.measure(song); EARLAST = m; pr.remove(); line();
      w('<span class="dim">  where each track actually lives, on <span class="a">'+esc(m.section)+'</span></span>'); line();
      EAR.table(m).forEach(function(r){ w('<span class="dim">  '+esc(r)+'</span>'); }); line();
    }catch(e){ pr.remove(); line('  could not render: '+(e.message||e),'w'); } },
  play: function(){
    if(!song && !(E.order||[]).length) return line(CP.err_nosong,'w');
    E.play(); PLAYAT = Date.now();
    ev('play', {id: NOWID, source: 'cmd', of_ms: Math.round(songSeconds(song) * 1000)});
    line('▸ playing','dim'); },
  /* `exit`, `quit` and `q` all alias here, and in deck mode stopping the studio
     transport is a no-op that reads as a broken command. One guard, and all four
     verbs mean the obvious thing on the page you are actually looking at. */
  stop: function(){ if(MODE === 'deck') return CMDS.mode(['studio']);
    E.stop();
    ev('stop', {id: NOWID, played_ms: PLAYAT ? Date.now() - PLAYAT : 0,
                of_ms: Math.round(songSeconds(song) * 1000)});
    PLAYAT = 0; line('▸ stopped','dim'); },
  bpm: function(a){ var v=parseFloat(a[0]);
    if(!isFinite(v)||v<60||v>220) return line(CP.err_bpm,'w');
    E.setBpm(v); if(song) song.bpm=v; line('▸ '+v+' BPM','dim'); },
  gallery: async function(){ line();
    w('<span class="b">what people published.</span> <span class="dim">each is a few KB of text.</span>');
    var d=w('<span class="dim">  loading…</span>');
    try{
      var r=await fetch(API+'/gallery?limit_n=15'), j=await r.json(); d.remove();
      if(!j.songs||!j.songs.length){ line();
        return w('<span class="dim">  nobody has published anything yet. be the first. type <span class="a">go</span> then <span class="a">publish</span>.</span>'); }
      GAL = j.songs;
      j.songs.forEach(function(sg,i){
        w('  <span class="a">'+String(i+1).padStart(2)+'</span>  <span class="b">'+
          esc(String(sg.title).slice(0,22).padEnd(22))+'</span><span class="dim">'+
          String(Math.round(sg.bpm)).padStart(4)+' BPM  '+
          esc(String(sg.kkey||'').padEnd(9))+mmss(sg.seconds)+'  '+esc(sg.by||'')+'</span>');
      });
      line(); w('<span class="dim">  <span class="a">open 3</span> to load one. you get the arrangement, not just the audio.</span>'); line();
    }catch(e){ d.remove(); line('  gallery unreachable right now','w'); } },
  open: async function(a){
    var n=parseInt(a[0],10);
    if(!GAL.length) return line('type `gallery` first','w');
    var it=GAL[n-1]; if(!it) return line('no such number','w');
    try{ var r=await fetch(API+'/songs/'+it.id), j=await r.json();
      loadSong(j.data, 'by '+(j.by||'someone')+' · '+j.plays+' plays');
    }catch(e){ line('could not load that one','w'); } },
  login: async function(a){
    var em=(a[0]||'').trim();
    if(!em || em.indexOf('@')<0) return line('login you@example.com','w');
    try{ var r=await fetch(API+'/auth/request',{method:'POST',
        headers:{'content-type':'application/json'}, body:JSON.stringify({email:em})});
      var j=await r.json();
      ev('signin_request', {sent: j.sent ? 1 : 0});
      if(j.sent) line('▸ check your email. the link signs you in.','ok');
      else if(j.link){ line('▸ mail is off on this deploy, here is your link:','w');
        w('  <a href="'+esc(j.link)+'">'+esc(j.link)+'</a>'); }
      else line('▸ could not send that: '+(j.why||'unknown'),'w');
    }catch(e){ line('auth unreachable','w'); } },
  /* `publish` and `share` do the same thing; this one just insists on your name
     being on it. Both hand the link over the same way. */
  publish: async function(){
    if(!token) return line('`share` works signed out. `publish` puts your name on it — `login you@example.com`','w');
    ev('song_publish', {bars: song ? OZ.totalBars(song) : 0, remix: REMIX_OF ? 1 : 0});
    return CMDS.share([]);
  },
  clear: function(){ OUT.innerHTML='<div id="slack"></div>'; },
  mute: function(a){ var t=a[0]; if(!E.tracks[t]) return line('mute <track>','w');
    E.setTrack(t,{mute:!E.tracks[t].mute}); draw(); line('▸ '+t+(E.tracks[t].mute?' muted':' on'),'dim'); },
  solo: function(a){ E.focus=a[0]||E.focus; line('▸ '+E.key('x',true),'dim'); draw(); },
  gain: function(a){ var t=a[0], v=parseFloat(a[1]); if(!E.tracks[t]||!isFinite(v)) return line('gain <track> 0..1.2','w');
    E.setTrack(t,{gain:Math.max(0,Math.min(1.2,v))}); line('▸ '+t+' gain '+v,'dim'); },
  /* The mixer verbs the AI prompt and the lesson both assume exist. */
  sidechain: function(a){ var t=a[0], v=parseFloat(a[1]);
    if(!E.tracks[t]||!isFinite(v)) return line('sidechain <track> 0..1   (how hard it ducks on the kick)','w');
    E.setTrack(t,{sc:Math.max(0,Math.min(1,v))}); teach('sidechain');
    line('▸ '+t+' ducks '+Math.round(Math.max(0,Math.min(1,v))*100)+'% on every kick','dim'); },
  pan: function(a){ var t=a[0], v=parseFloat(a[1]);
    if(!E.tracks[t]||!isFinite(v)) return line('pan <track> -1..1','w');
    E.setTrack(t,{pan:Math.max(-1,Math.min(1,v))}); teach('pan'); line('▸ '+t+' pan '+v,'dim'); },
  filter: function(a){ var t=a[0], hz=parseFloat(a[1]);
    if(!E.tracks[t]||!isFinite(hz)) return line('filter <track> <hz>   (the lowpass on a pitched voice)','w');
    E.setTrack(t,{fc:Math.max(40,Math.min(18000,hz))}); teach('cutoff'); line('▸ '+t+' cutoff '+Math.round(hz)+' Hz','dim'); },
  tune: function(a){ var t=a[0], hz=parseFloat(a[1]);
    if(!E.tracks[t]||!isFinite(hz)) return line('tune <track> <hz>','w');
    E.setTrack(t,{tune:hz}); teach('tune'); line('▸ '+t+' tune '+hz,'dim'); },
  swing: function(a){ var v=parseFloat(a[0]); if(!isFinite(v)) return line('swing 0..60','w');
    E.swing=Math.max(0,Math.min(60,v)); if(song) song.swing=E.swing; line('▸ swing '+E.swing,'dim'); },
  focus: function(a){ if(!E.tracks[a[0]]) return line('focus <track>','w'); E.focus=a[0]; draw(); line('▸ pads edit '+a[0],'dim'); },
  perform: function(){ IN.blur(); },
  /* what a thing does, in sound terms - the same table the desktop teaches from */
  why: function(a){
    var T = window.OONTZ_THEORY, topic = (a[0]||'').toLowerCase();
    if(!topic){
      if(!song) return line('why <thing> — e.g. why sidechain, why swing, why cutoff','w');
      var at = OZ.sectionAt(song, E.songbar); line();
      w('<span class="dim">  you are in <span class="b">'+esc(at?at.name:'?')+'</span>'+
        (at?' ('+at.sec.role+', energy '+(at.sec.energy||0).toFixed(2)+', bar '+(at.within+1)+' of '+at.sec.bars+')':'')+'</span>');
      var g = (T.genres||{})[(song.meta||{}).style];
      if(g) w('<span class="dim">  '+esc(g.note)+'</span>');
      var gr = T.grooves && T.grooves[song.groove];
      if(gr) w('<span class="dim">  groove <span class="a">'+esc(song.groove)+'</span>: '+esc(gr.why)+'</span>');
      line(); return w('<span class="dim">  <span class="a">why sidechain</span> · <span class="a">why swing</span> · <span class="a">rules</span> · <span class="a">grade</span></span>');
    }
    var txt = (T.why||{})[topic];
    if(!txt){ var hits = Object.keys(T.why||{}).filter(function(k){ return k.indexOf(topic)===0; });
      if(hits.length===1) txt = T.why[hits[0]];
      else return line('no explanation for '+topic+'. try: '+Object.keys(T.why||{}).slice(0,14).join(' '),'w'); }
    line(); w('<span class="dim">  '+esc(txt)+'</span>'); line(); },
  learn: function(){ LESSON_AT = 0; TEACH = true; lessonStep(); },
  palette: function(){ openPal(); },
  /* Two knobs for legibility, because a fixed answer is wrong for someone. */
  calm: function(a){ var on = a[0] ? a[0] !== 'off' : !document.body.classList.contains('calm');
    document.body.classList.toggle('calm', on);
    try{ localStorage.setItem('oontz_calm', on ? '1' : ''); }catch(e){}
    line('▸ visuals ' + (on ? 'dimmed - the words win' : 'back up'), 'dim'); },
  text: function(a){
    var cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--size'), 10) || 15;
    var v = a[0] === '+' ? cur + 1 : a[0] === '-' ? cur - 1 : parseInt(a[0], 10);
    if(!isFinite(v)) return line('text 17 · text + · text -   (11-28)', 'w');
    v = Math.max(11, Math.min(28, v));
    document.documentElement.style.setProperty('--size', v + 'px');
    try{ localStorage.setItem('oontz_size', String(v)); }catch(e){}
    draw(); line('▸ ' + v + 'px', 'dim'); },
  /* R / `rec`: what you hear, effects and all, tapped after the compressor. `rec screen`
     adds a screen capture and lets the browser mux the two. */
  rec: async function(a){
    if(REC){ if(REC !== 'pending') REC.stop(); return; }
    if(!window.MediaRecorder) return line('this browser cannot record','w');
    REC = 'pending';                              // claim it before any await
    var c = E.start(), video = a[0]==='screen' || a[0]==='video';
    var dst = c.createMediaStreamDestination(); E.analyser.connect(dst);
    var stream = dst.stream;
    if(video){ try{ var disp = await navigator.mediaDevices.getDisplayMedia({video:true, audio:false, preferCurrentTab:true});
        stream = new MediaStream(disp.getVideoTracks().concat(dst.stream.getAudioTracks()));
        disp.getVideoTracks()[0].onended = function(){ if(REC) REC.stop(); };
      }catch(e){ REC = null; try{ E.analyser.disconnect(dst); }catch(_e){} return line('screen capture was refused','w'); } }
    var want = video ? ['video/webm;codecs=vp9,opus','video/webm','video/mp4'] : ['audio/webm;codecs=opus','audio/webm','audio/mp4'];
    var mime = want.filter(function(m){ return MediaRecorder.isTypeSupported(m); })[0];
    var chunks = [], r;
    try{ r = new MediaRecorder(stream, mime ? {mimeType: mime} : {}); }
    catch(e){ REC = null; try{ E.analyser.disconnect(dst); }catch(_e){}
      return line('could not start a recorder: '+(e.message||e),'w'); }
    r.ondataavailable = function(ev){ if(ev.data && ev.data.size) chunks.push(ev.data); };
    r.onstop = function(){ REC = null; PS1.style.color = '';
      try{ E.analyser.disconnect(dst); }catch(e){} stream.getTracks().forEach(function(t){ t.stop(); });
      var ext = (r.mimeType||'').indexOf('mp4') >= 0 ? 'mp4' : 'webm';
      var name = 'oontz-' + (song ? song.name : 'session').replace(/[^\w-]+/g,'_') + '.' + ext;
      saveBlob(new Blob(chunks, {type: r.mimeType}), name);
      w('<span class="ok">■ saved '+esc(name)+'</span> <span class="dim">exactly what you heard</span>'); };
    r.start(1000); REC = r; PS1.style.color = 'var(--hot)';
    if(!E.playing) line('  (nothing is playing yet - space or `play`)','dim');
    w('<span class="hot">● recording'+(video?' screen + audio':'')+'</span> <span class="dim">R or `rec` again to stop</span>');
  },
  /* A clip is the thing that actually travels. A link gets scrolled past; ten
     seconds of the drop with the visuals on it gets watched.

     The audio is rendered OFFLINE first and played back while the canvas is
     captured, so the sound is the exact deterministic mix rather than whatever
     survived a busy main thread. No screen-share prompt either, unlike `rec
     screen` - captureStream needs no permission at all. */
  clip: async function(a){
    if(!song) return line(CP.err_nosong,'w');
    if(CLIP) return line('already making one','w');
    var cv = document.getElementById('viz');
    if(!cv || !cv.captureStream)
      return line('this browser cannot capture the canvas — try `watch` plus the screen recorder your phone already has','w');
    var mime = pickMime(CLIP_MIMES);
    if(!mime){ ev('clip_failed',{why:'no mime'});
      return line('this browser cannot encode video — `share` gives a link that previews everywhere','w'); }
    var bars = Math.max(4, Math.min(12, Math.round(10 / (240 / (song.bpm || 140)))));
    if(a[0] && +a[0]) bars = Math.max(1, Math.min(32, +a[0]|0));
    var d = w('<span class="dim">  rendering '+bars+' bars…</span>');
    CLIP = true;
    var t0 = Date.now(), out = null;
    try{
      var buf = await OZ.renderSlice(song, {bar: E.songbar, bars: bars, channels: 2});
      d.remove();
      var side = 1080, cc = document.createElement('canvas');
      cc.width = cc.height = side;
      var cx = cc.getContext('2d');
      var ctx = E.start();
      if(window.OONTZ_VIZ && OONTZ_VIZ.status().mode === 'off') OONTZ_VIZ.mode('auto');
      var src = ctx.createBufferSource(); src.buffer = buf;
      var dst = ctx.createMediaStreamDestination();
      src.connect(dst); src.connect(ctx.destination);      // heard while captured
      var stream = new MediaStream(cc.captureStream(30).getVideoTracks()
                                     .concat(dst.stream.getAudioTracks()));
      var burn = SHARED_URL || 'oontz.sh';
      var raf = 0, paint = function(){
        raf = requestAnimationFrame(paint);
        var r = clipRect(cv.width, cv.height);
        try{ cx.drawImage(cv, r.sx, r.sy, r.s, r.s, 0, 0, side, side); }catch(e){}
        cx.font = '500 30px ui-monospace, Menlo, Consolas, monospace';
        cx.textBaseline = 'alphabetic';
        cx.shadowColor = 'rgba(0,0,0,.95)'; cx.shadowBlur = 12;
        cx.fillStyle = '#ffffff'; cx.textAlign = 'left';
        cx.fillText(String(song.name).slice(0, 28), 40, side - 40);
        cx.fillStyle = '#3ff0e0'; cx.textAlign = 'right';
        cx.fillText(burn, side - 40, side - 40);
        cx.shadowBlur = 0;
      };
      paint();
      out = await new Promise(function(res, rej){
        var chunks = [], r;
        try{ r = new MediaRecorder(stream, {mimeType: mime}); }catch(e){ return rej(e); }
        r.ondataavailable = function(e){ if(e.data && e.data.size) chunks.push(e.data); };
        r.onstop = function(){ res(new Blob(chunks, {type: r.mimeType || mime})); };
        r.start(200);
        src.onended = function(){ setTimeout(function(){ try{ r.stop(); }catch(e){} }, 120); };
        src.start();
        setTimeout(function(){ if(r.state !== 'inactive') r.stop(); },
                   (buf.duration + 2) * 1000);          // a guard, if onended never comes
      });
      cancelAnimationFrame(raf);
      stream.getTracks().forEach(function(t){ t.stop(); });
    }catch(e){
      if(d.parentNode) d.remove();
      CLIP = false; ev('clip_failed',{why:String(e && e.message || e)});
      return line('could not make a clip: '+esc(String(e && e.message || e)),'w');
    }
    CLIP = false;
    var ext = mime.indexOf('mp4') >= 0 ? 'mp4' : 'webm';
    var name = 'oontz-' + String(song.name).replace(/[^\w-]+/g,'_') + '.' + ext;
    ev('clip_made', {ms: Date.now()-t0, bytes: out.size, mime: mime});
    var f = null;
    try{ f = new File([out], name, {type: out.type || mime}); }catch(e){}
    var el = w('<span class="ok">▸ '+bars+' bars, '+Math.round(out.size/1024)+'KB.</span> ');
    if(f && navigator.canShare && navigator.canShare({files:[f]})){
      var b = document.createElement('button'); b.className='chip'; b.textContent='send it';
      b.onclick = function(){ navigator.share({files:[f], text: burn})
        .then(function(){ ev('share_native',{kind:'clip'}); }).catch(function(){}); };
      el.appendChild(b);
    }
    var dl = document.createElement('button'); dl.className='chip'; dl.textContent='save it';
    dl.onclick = function(){ saveBlob(out, name); };
    el.appendChild(dl);
    if(ext === 'webm')
      w('<span class="dim">  (webm — Instagram and TikTok will not take it, but X and Discord will)</span>');
  },
  /* ask: the AI proposes command lines; an empty Enter runs them, anything else discards. */
  ask: async function(a){
    var q = a.join(' '); if(!q) return line('ask make it darker and half time','w');
    var at = song ? OZ.sectionAt(song, E.songbar) : null;
    var state = {bpm: E.bpm, swing: E.swing, key: song && song.key, scale: song && song.scale,
      section: at && at.name, role: at && at.sec.role, bar: E.songbar, tracks: E.tracks, order: E.order,
      commands: Object.keys(CMDS).concat(E.order)};
    var d = w('<span class="dim">  thinking…</span>');
    var t0 = Date.now();
    ev('ai_ask', {source: 'ask', prompt_len: q.length, text: q.slice(0,300)});
    try{
      var hdr = {'content-type':'application/json'};
      var myKey = localStorage.getItem('oontz_key');   // linked with `key` — browser-only
      if(myKey) hdr['x-anthropic-key'] = myKey;
      var r = await fetch(API+'/ai/ask', {method:'POST', headers:hdr,
        body: JSON.stringify({prompt: q, state: state})});
      var j = await r.json(); d.remove();
      ev('ai_result', {source: 'ask', ms: Date.now()-t0, n: (j.commands||[]).length,
                       ok: (j.commands||[]).length ? 1 : 0});
      if(!j.commands || !j.commands.length) return line('▸ '+(j.error||'no suggestion'),'w');
      PENDING = j.commands; line();
      j.commands.forEach(function(c){
        var okc = musical(c);
        w('  <span class="dim">▸</span> <span class="'+(okc?'a':'dim')+'"'+
          (okc?'':' style="text-decoration:line-through"')+'>'+esc(c)+'</span>'+
          (okc?'':' <span class="dim">not a musical command — skipped</span>')); });
      w('<span class="dim">  Enter runs these '+j.commands.length+' · type anything else to discard · `undo` takes them back</span>'); line();
    }catch(e){ d.remove(); ev('ai_result', {source: 'ask', ms: Date.now()-t0, n: 0, ok: 0,
                                            error: String(e && e.message || e).slice(0,120)});
      line('the AI is unreachable right now','w'); }
  },
  /* -------------------------------------------------------- the arrangement
     You could compose a song and edit any track inside it, but you could not
     change its shape - no add, remove, reorder or resize existed anywhere, so a
     generated arrangement was final. These mirror the desktop's `sec` verbs.
     Bars stay multiples of 8 because the grader, the dancers and the DJ all
     count in eights. */
  sec: function(a){
    if(!song) return line(CP.err_nosong,'w');
    var sub = (a[0]||'list').toLowerCase(), at = OZ.sectionAt(song, E.songbar);
    var here = at ? at.name : song.order[0];
    function bars8(v, dflt){ var n = parseInt(v,10); if(!isFinite(n)) n = dflt;
      return Math.max(8, Math.min(64, Math.round(n/8)*8)); }
    function total(){ return OZ.totalBars(song); }
    function after(){ E.loadSong(song); draw();
      return line('▸ ' + song.order.length + ' sections, ' + total() + ' bars · ' + mmss(songSeconds(song)),'dim'); }

    if(sub === 'list'){
      line();
      song.order.forEach(function(n,i){ var s2 = song.sections[n];
        w('  <span class="'+(n===here?'a2':'dim')+'">'+(n===here?'▸':' ')+' '+String(i+1).padStart(2)+
          '  '+esc(n.padEnd(10))+'</span><span class="dim">'+String(s2.bars).padStart(3)+
          ' bars  '+esc((s2.role||'').padEnd(7))+' energy '+(s2.energy||0).toFixed(2)+'</span>'); });
      line(); return w('<span class="dim">  sec add drop 16 · sec len 32 · sec del break2 · sec move drop2 1 · sec role build</span>');
    }
    snapshot('sec ' + sub);
    if(sub === 'add'){
      var role = (a[1]||'drop').toLowerCase(), n = bars8(a[2], 16);
      var base = song.sections[here];
      var name = role, k = 2; while(song.sections[name]) name = role + (k++);
      var copy = JSON.parse(JSON.stringify(base));
      copy.name = name; copy.role = role; copy.bars = n;
      copy.energy = ({intro:0.15, build:0.55, drop:0.95, break:0.2, verse:0.5, outro:0.2})[role];
      if(copy.energy == null) copy.energy = 0.5;
      copy.automation = [];
      song.sections[name] = copy;
      song.order.splice(song.order.indexOf(here)+1, 0, name);   // next to where you are
      line('▸ added ' + name + ', ' + n + ' bars, after ' + here,'dim');
      return after();
    }
    if(sub === 'del' || sub === 'rm'){
      var n2 = a[1] || here;
      if(!song.sections[n2]) return line('no section called ' + n2,'w');
      if(song.order.length <= 2) return line('a song needs more than one section','w');
      song.order = song.order.filter(function(x){ return x !== n2; });
      if(!song.order.some(function(x){ return x === n2; })) delete song.sections[n2];
      E.songbar = 0;
      line('▸ removed ' + n2,'dim');
      return after();
    }
    if(sub === 'len'){
      var name3 = a.length > 2 ? a[1] : here, n3 = bars8(a[a.length-1], 16);
      if(!song.sections[name3]) return line('no section called ' + name3,'w');
      song.sections[name3].bars = n3;
      line('▸ ' + name3 + ' is ' + n3 + ' bars','dim');
      return after();
    }
    if(sub === 'move'){
      var name4 = a[1], to = parseInt(a[2],10);
      if(!song.sections[name4]) return line('no section called ' + name4,'w');
      if(!isFinite(to)) return line('sec move <name> <position>','w');
      to = Math.max(1, Math.min(song.order.length, to)) - 1;
      var from = song.order.indexOf(name4);
      song.order.splice(from, 1); song.order.splice(to, 0, name4);
      line('▸ ' + name4 + ' is now section ' + (to+1),'dim');
      return after();
    }
    if(sub === 'copy'){
      var src = a[1] || here;
      if(!song.sections[src]) return line('no section called ' + src,'w');
      var nm = src.replace(/\d+$/,''), k2 = 2, dst = nm + k2;
      while(song.sections[dst]) dst = nm + (++k2);
      song.sections[dst] = JSON.parse(JSON.stringify(song.sections[src]));
      song.sections[dst].name = dst;
      song.order.splice(song.order.indexOf(src)+1, 0, dst);
      line('▸ copied ' + src + ' to ' + dst,'dim');
      return after();
    }
    if(sub === 'role'){
      var name5 = a.length > 2 ? a[1] : here, r = (a[a.length-1]||'').toLowerCase();
      if(!song.sections[name5]) return line('no section called ' + name5,'w');
      var e = ({intro:0.15, build:0.55, drop:0.95, break:0.2, verse:0.5, outro:0.2})[r];
      if(e == null) return line('role is one of: intro build drop break verse outro','w');
      song.sections[name5].role = r; song.sections[name5].energy = e;
      line('▸ ' + name5 + ' is a ' + r + ' now','dim');
      return after();
    }
    UNDO.pop();                                   // nothing happened, do not leave an undo step
    return line('sec list|add|del|len|move|copy|role','w');
  },
  name: function(a){
    if(!song) return line(CP.err_nosong,'w');
    var t = a.join(' ').trim();
    if(!t) return line('name <title>   (it is "' + esc(song.name) + '")','w');
    snapshot('rename');
    song.name = t.slice(0, 60);
    draw(); line('▸ called "' + esc(song.name) + '" now','dim');
  },
  undo: function(a){
    var n = Math.max(1, Math.min(20, parseInt(a && a[0], 10) || 1)), last = null, did = 0;
    for(var i = 0; i < n; i++){ var l = undoOne(); if(l === null) break; last = l; did++; }
    if(!did) return line('nothing to undo','w');
    ev('ai_undo', {verb: String(last||'').slice(0,40), n: did});
    line('▸ undid ' + (did > 1 ? did + ' changes, back past ' : '') + last, 'dim'); },
  /* jam: the AI is a bandmate, not an oracle. Every N bars it makes one small
     move, out loud, and `undo` vetoes it. */
  jam: function(a){
    var v = (a[0]||'').toLowerCase();
    if(v === 'off'){ JAM.on = false; return line('▸ jam off','dim'); }
    if(!v && JAM.on) return line('▸ jamming every '+JAM.bars+' bars · jam off ends it','dim');
    if(v === 'style'){ JAM.style = a.slice(1).join(' ');
      return line(JAM.style ? '▸ jam leans '+esc(JAM.style) : '▸ jam style <mood> — darker, funkier, sparser, unhinged…', JAM.style?'ok':'w'); }
    var bars = parseInt(v === 'on' ? a[1] : v, 10);
    if(v && v !== 'on' && !isFinite(bars)) return line(CP.jam_usage,'w');
    JAM.on = true; JAM.bars = Math.max(2, Math.min(64, isFinite(bars) ? bars : 8));
    JAM.mark = E.songbar; JAM.turns = 0;
    line('▸ '+CP.jam_on(JAM.bars),'ok');
    if(!E.playing) line('  '+CP.jam_needs_play,'dim');
  },
  real: function(){ line('▸ '+CP.real_go,'ok'); location.href='/py/'; },
  /* produce: the closed loop, watchable. grade -> worst fault -> one fix -> regrade,
     until the target or the rounds run out. A round that makes it worse is reverted
     on the spot. One `undo` takes back the whole pass. */
  produce: async function(a){
    if(!song) return line(CP.err_nosong,'w');
    if(PRODUCING) return line('already producing — patience','w');
    var target = Math.min(100, parseInt(a[0],10) || 90), rounds = Math.min(12, parseInt(a[1],10) || 6);
    var sc = CO.score(CO.critique(song));
    if(sc >= target) return line('▸ already at '+sc+'/100 — raise the bar: produce '+(Math.min(100,sc+5)),'ok');
    PRODUCING = true; snapshot('produce');
    var passStart = UNDO.length;                  /* one undo returns here */
    line('▸ '+CP.produce_on(sc, target, rounds),'ok');
    var worse = 0;
    for(var r = 1; r <= rounds && sc < target; r++){
      var crit = CO.critique(song);
      var faults = crit.filter(function(c){ return c[0]==='bad'; })
                   .concat(crit.filter(function(c){ return c[0]==='warn'; }))
                   .slice(0, 5).map(function(c){ return c[1]; });
      if(!faults.length){ line('  round '+r+': the grader is out of complaints at '+sc+'/100','dim'); break; }
      var pr = w('<span class="dim">  round '+r+': thinking about — '+esc(faults[0].slice(0,70))+'…</span>');
      var j = null;
      try{ j = await askAI('PRODUCE ROUND '+r+': the track scores '+sc+'/100. Open faults, worst first: '
             +faults.join(' | ')+'. Fix the FIRST fault with the fewest commands (1-3 lines). Do not touch '
             +'anything the grader is happy with. End with "# <six words on the fix>".',
             {grade: {score: sc, faults: faults}, produce_round: r}); }catch(e){}
      pr.remove();
      if(!j || !j.commands || !j.commands.length){ line('  round '+r+': no move offered — stopping','dim'); break; }
      snapshot();
      j.commands.slice(0, 3).forEach(run);
      var now = CO.score(CO.critique(song));
      if(now < sc){ CMDS.undo(); worse++;
        line('  round '+r+': '+sc+' → '+now+' — reverted'+(j.why?' ('+esc(j.why)+')':''),'w');
        if(worse >= 2){ line('  two bad rounds — stopping while ahead','dim'); break; }
      } else {
        line('  round '+r+': '+sc+' → <span class="'+(now>sc?'ok':'dim')+'">'+now+'</span>'
             +(j.why ? ' <span class="dim">· '+esc(j.why)+'</span>' : ''), now>sc?'ok':'dim');
        sc = now; worse = 0;
      }
    }
    UNDO.splice(passStart);                       /* collapse the pass to one undo step */
    PRODUCING = false; draw();
    line('▸ '+CP.produce_done(sc, target),'b');
  },
  /* dream: prose in, an arranged track out — compose first, then pushes toward the words. */
  dream: async function(a){
    var wish = a.join(' ').trim();
    if(!wish) return line(CP.dream_usage,'w');
    if(PRODUCING) return line('the producer is mid-pass — let it finish','w');
    var d = w('<span class="dim">  dreaming…</span>');
    var j = null;
    try{ j = await askAI('DREAM: build a whole track from this wish: "'+wish+'". Reply with FIRST one line '
           +'`compose <style> <minutes> <curve>` choosing style from ['+Object.keys(CO.GENRES).join(' ')
           +'] and curve from ['+Object.keys(CO.TEMPLATES).join(' ')+'], THEN up to 8 command lines that '
           +'push the result toward the wish (voices, patterns, bpm, swing, filters, gains). '
           +'End with "# <six words on the vibe>".', {dream: wish}); }catch(e){}
    d.remove();
    if(!j || !j.commands || !j.commands.length) return line('▸ '+(j && j.error || 'the dream did not answer'),'w');
    snapshot();
    j.commands.slice(0, 9).forEach(run);
    if(j.why) line('▸ '+esc(j.why),'b');
    if(song) line('▸ theory says '+CO.score(CO.critique(song))+'/100 · `produce` to push it · `undo` to wake up','dim');
  },
  /* the format, in hand: source out, load in, diff between */
  source: async function(a){
    if(!song) return line(CP.err_nosong,'w');
    var doc = Object.assign({format: 'oontz-song-1'}, song);
    var text = JSON.stringify(doc), kb = (text.length/1024).toFixed(1);
    if((a[0]||'') === 'save'){
      var fn = (song.name||'song').replace(/[^a-zA-Z0-9_-]+/g,'_')+'.oontz';
      saveBlob(new Blob([JSON.stringify(doc, null, 1)], {type:'application/json'}), fn);
      return line('▸ saved '+fn+' · '+kb+'KB. the whole song, not a recording of it.','ok');
    }
    if((a[0]||'') === 'copy'){
      try{ await navigator.clipboard.writeText(text); return line('▸ '+kb+'KB on the clipboard — the complete song. paste it anywhere text goes.','ok'); }
      catch(e){ return line('the clipboard said no — `source save` downloads instead','w'); }
    }
    line('▸ '+esc(song.name)+' is '+kb+'KB of JSON: '+(song.order||[]).length+' sections, every note, every knob. '+CP.source_hint,'dim');
  },
  /* ------------------------------------------------------- a local library
     There was exactly one slot - `oontz_song`, overwritten on unload - so a
     second idea destroyed the first unless you had signed in. This keeps as many
     as fit, in this browser, with no account. `take` is still the server one. */
  save: function(a){
    if(!song) return line(CP.err_nosong,'w');
    var nm = a.join(' ').trim() || song.name;
    if(!nm) return line('save <name>','w');
    var lib = readLib();
    lib[nm] = {saved: Date.now(), bars: OZ.totalBars(song), bpm: song.bpm,
               style: (song.meta||{}).style, data: song};
    if(!writeLib(lib)) return line('no room left in this browser — `songs`, then `forget <name>`','w');
    song.name = nm; draw();
    ev('song_save', {bars: OZ.totalBars(song), bpm: song.bpm, n: Object.keys(lib).length});
    line('▸ saved "'+esc(nm)+'" · '+Object.keys(lib).length+' here','dim');
  },
  songs: function(){
    var lib = readLib(), names = Object.keys(lib).sort(function(x,y){ return lib[y].saved - lib[x].saved; });
    if(!names.length) return line('nothing saved yet — `save <name>` keeps one here','dim');
    line();
    names.forEach(function(n){ var e = lib[n];
      w('  <span class="k">'+esc(n)+'</span><span class="dim">'+
        String(e.bpm||'?').padStart(4)+' BPM  '+String(e.bars||'?').padStart(4)+' bars  '+
        esc(String(e.style||'').padEnd(11))+' '+ago(e.saved)+'</span>'); });
    line(); return w('<span class="dim">  <span class="a">load '+esc(names[0])+'</span> · <span class="a">forget '+esc(names[0])+'</span></span>');
  },
  forget: function(a){
    var key = a.join(' ').trim(), lib = readLib();
    if(!lib[key]) return line('nothing saved as "'+esc(key)+'"','w');
    delete lib[key]; writeLib(lib);
    line('▸ forgot "'+esc(key)+'"','dim');
  },
  name: function(a){
    if(!song) return line(CP.err_nosong,'w');
    var t = a.join(' ').trim();
    if(!t) return line('name <title>   (it is "'+esc(song.name)+'" just now)','w');
    snapshot('rename'); song.name = t.slice(0, 60); draw();
    line('▸ called "'+esc(song.name)+'" now','dim');
  },
  load: function(a){
    var raw = a.join(' ').trim();
    if(!raw) return CMDS.songs([]);
    /* A brace is pasted JSON; anything else is a name in the local library. */
    if(raw.charAt(0) !== '{'){
      var lib = readLib();
      var hit = lib[raw] || lib[Object.keys(lib).filter(function(k){
        return k.toLowerCase().indexOf(raw.toLowerCase()) === 0; })[0]];
      if(!hit) return line('nothing saved as "'+esc(raw)+'" — `songs` lists them','w');
      snapshot('load');
      return loadSong(hit.data, 'loaded "'+esc(hit.data.name)+'"');
    }
    var sg; try{ sg = JSON.parse(raw); }catch(e){ return line('that is not JSON. `source copy` on a song makes some.','w'); }
    if(sg.format && sg.format !== 'oontz-song-1' && sg.format !== 'thud-song-1')   // thud-song-1: the pre-rename name, still in the wild
      return line('unknown format '+esc(String(sg.format))+' — this player speaks oontz-song-1','w');
    if(!sg.order || !sg.sections) return line('JSON, but not a song: it needs order and sections','w');
    snapshot('load'); loadSong(sg, 'loaded from source');
  },
  diff: async function(a){
    if(!song) return line(CP.err_nosong,'w');
    var other = null, label = '';
    if(!a[0]){
      other = UNDO[UNDO.length-1]; label = 'last snapshot';
      if(!other) return line('nothing to diff against yet — edits and jam turns leave snapshots','w');
    } else if(a[0] === 'take' && a[1]){
      if(!token || !window.OONTZ_ACCOUNT) return line('takes need a sign-in','w');
      try{ var t = await OONTZ_ACCOUNT.req('GET','/takes/'+a[1]); other = JSON.parse(t.data); label = 'take '+t.name; }
      catch(e){ return line('no such take of yours','w'); }
    } else {
      try{ var r = await fetch(API+'/songs/'+encodeURIComponent(a[0])); var j = await r.json();
        if(!r.ok || !j.data) return line('▸ '+esc((j&&j.error)||'not found'),'w');
        other = j.data; label = j.title; }
      catch(e){ return line('could not reach the server','w'); }
    }
    line(); w('<span class="b">'+esc(label)+' → '+esc(song.name)+'</span>');
    OZ.songDiff(other, song).forEach(function(l){
      var c = l[0] === '+' ? 'ok' : (l[0] === '-' ? 'hot' : 'a');
      w('  <span class="'+c+'">'+esc(l)+'</span>'); });
    line();
  },
  room: async function(a){
    var v = (a[0]||'').toLowerCase();
    if(v === 'leave'){ var had = ROOM.code; ROOM.code = null;
      if(ROOM.ws) try{ ROOM.ws.close(); }catch(e){}
      ROOM.ws = null; ROOM.others = 0; ROOM.gotSong = false; draw();
      return line(had ? '▸ left '+had : 'you were not in a room','dim'); }
    if(v === 'who') return line(ROOM.code ? '▸ room '+ROOM.code+' · you and '+ROOM.others+' other'+(ROOM.others===1?'':'s') : 'no room. `room new` starts one.','dim');
    if(v === 'new' || !v){
      if(!v && ROOM.code) return CMDS.room(['who']);
      if(!v) return line(CP.room_usage,'w');
      try{
        var r = await fetch(API+'/rooms', {method:'POST'});
        var j = await r.json();
        if(!j.code) return line('▸ '+esc(j.error||'no room came back'),'w');
        ROOM.gotSong = true;                     /* the creator's song is the room's song */
        roomJoin(j.code);
        line('▸ '+CP.room_new(j.code),'b');
      }catch(e){ line('could not reach the server','w'); }
      return; }
    ROOM.gotSong = false;
    roomJoin(v.toUpperCase());
  },
  similar: async function(){
    if(!song) return line(CP.err_nosong,'w');
    var d = w('<span class="dim">  asking the gallery what this resembles…</span>');
    try{
      var r = await fetch(API+'/similar', {method:'POST', headers:{'content-type':'application/json'},
        body: JSON.stringify({data: song})});
      var j = await r.json(); d.remove();
      if(!j.songs || !j.songs.length) return line('nothing public is structurally close — you are onto something original','ok');
      line('▸ public tracks like yours:','b');
      j.songs.forEach(function(sg){
        w('  <span class="a">'+esc(sg.id)+'</span> '+esc(sg.title)+' <span class="dim">'+Math.round(sg.score*100)+'% · '+esc((sg.why||[]).join(', '))+' · by '+esc(sg.handle||'?')+'</span>'); });
      line('<span class="dim">  hear one on oontz.music: play &lt;id&gt;</span>');
    }catch(e){ d.remove(); line('could not reach the server','w'); } },
  remix: async function(a){
    var id = (a[0]||'').trim();
    if(!id) return line(CP.remix_usage,'w');
    var d = w('<span class="dim">  fetching the source…</span>');
    try{
      var r = await fetch(API+'/songs/'+encodeURIComponent(id)); var j = await r.json(); d.remove();
      if(!r.ok || !j.data) return line('▸ '+esc(j.error||'not found'),'w');
      loadSong(j.data, 'a remix begins');
      REMIX_OF = id; song.name = (j.title||'untitled')+' (flip)';
      line('▸ '+CP.remix_on(j.title, j.by),'ok');
    }catch(e){ d.remove(); line('could not reach the server','w'); } },
  tilt: function(a){
    var T = window.OONTZ_TOUCH;
    if(!T || !T.tiltEnable) return line('tilt is a phone thing — open this on one','w');
    if((a[0]||'') === 'off'){ T.tiltOff(); return line('▸ tilt off','dim'); }
    line('▸ asking for motion access…','dim');
    T.tiltEnable(function(ok){
      line(ok ? '▸ tilted: lean the phone to sweep the filter. a hard shake is a spinback. `tilt off` ends it.'
              : 'motion access said no — tilt needs it','' + (ok?'ok':'w'));
    }); },
  midi: function(a){
    var M = window.OONTZ_MIDI; if(!M) return;
    if((a[0]||'') === 'off'){ M.off(); return line('▸ midi off','dim'); }
    line('▸ asking the browser for MIDI access…','dim');
    M.connect(function(names, err){
      if(err) return line('▸ '+esc(err),'w');
      if(!names.length) return line('▸ no MIDI inputs found. plug one in — hot-plug works.','w');
      line('▸ listening to '+esc(names.join(', ')),'ok');
      w('<span class="dim">  pads 36-51 are the 16 steps · 52/53 sections · sustain pedal is play/stop · CC74 or the modwheel sweeps the filter</span>');
    }); },
  sounds: function(){ line();
    w('  <span class="dim">'+Object.keys(OZ.VOICES).sort().join(' · ')+'</span>');
    w('  <span class="dim">'+CP.sounds_hint+'</span>'); line(); },
  watch: function(){ var V = window.OONTZ_VIZ; if(!V) return;
    line('▸ '+CP.watch_on,'dim'); V.watch(true); },
  viz: function(a){ var V = window.OONTZ_VIZ; if(!V) return;
    var v = (a[0]||'').toLowerCase();
    if(!v) return line('▸ '+CP.viz_status(V.status())+' · '+CP.viz_usage,'dim');
    if(v==='why') return line(CP.viz_why,'dim');
    if(v==='modes'){ line(); (CP.viz_modes||[]).forEach(function(kv){
        w('  <span class="k">'+esc(kv[0])+'</span><span class="dim">'+esc(kv[1])+'</span>'); }); return line(); }
    if(v==='set'){ var x = V.set(a[1], a[2]);
      return x==null ? line(CP.viz_usage,'w') : line('▸ '+CP.viz_set(a[1], x),'dim'); }
    if(!V.mode(v)) return line(CP.err_viz(v),'w');
    line('▸ viz '+v,'dim'); },
  theme: function(a){ var V = window.OONTZ_VIZ; if(!V) return;
    var t = (a[0]||'').toLowerCase();
    if(t === 'make'){ var th = V.make(a[1], a.slice(2, 8), a[7]);
      return th ? line('▸ theme '+esc(th.name)+' is yours — it travels with the song when you publish','ok')
                : line(CP.theme_make_usage,'w'); }
    if(t === 'random'){ var r = V.random();
      return line('▸ '+r.colors.map(function(c){ return '<span style="color:'+c+'">█</span>'; }).join('')+' — rolled. `theme random` again to reroll, `theme make <name> '+r.colors.join(' ')+'` to keep it','ok'); }
    if(t === 'del'){ return V.unmake(a[1]) ? line('▸ gone','dim') : line('only your own themes can go','w'); }
    if(!t){ line(); Object.keys(V.THEMES).forEach(function(k){
        var th=V.THEMES[k]; w('  <span class="k">'+esc(k)+'</span><span class="dim">'+
          th.colors.map(function(c){return '<span style="color:'+c+'">█</span>';}).join('')+'</span>'); });
      return line(); }
    if(!V.theme(t)) return line('not a theme. `theme` lists them.','w');
    line('▸ theme '+t,'dim'); },
  /* -- decks -- */
  mode: function(a){ var m = (a[0]||(MODE==='deck'?'studio':'deck')).toLowerCase();
    if(m!=='deck' && m!=='studio') return line('mode deck|studio','w');
    if(m === MODE){ draw(); return; }
    if(m==='deck'){ DECKWAS = {playing: !!E.playing, bar: E.songbar|0};
      MODE = m; document.body.classList.add('deck');
      E.stop(); E.start();
      /* Every deck key - space, s, l, the crossfader, M itself - lives behind a
         handler that bails while the prompt has focus, and the prompt ALWAYS has
         focus. touch.js has blurred before dispatching since the pads shipped;
         desktop never did, which is why the decks have been keyboard-dead. */
      IN.blur();
      /* Two loops on purpose: the mixer paints its canvases on rAF, which a browser
         throttles to nothing in a background tab, and the HUD's one text line keeps a
         plain interval so it is still right when you come back to it. */
      if(window.OONTZ_MIXER) OONTZ_MIXER.show();
      if(!DECKTIMER) DECKTIMER = setInterval(function(){ if(MODE==='deck') drawSoon(); }, 100);
      line('▸ DECK. tap a track below to load it · M or ✕ to go back','dim'); }
    else { MODE = m; document.body.classList.remove('deck');
      if(window.OONTZ_MIXER) OONTZ_MIXER.hide();
      mixStop();                       /* mixTick bails on MODE!=='deck', so a set left running here never ends */
      var D = E.decks(); D.a.stop(); D.b.stop();
      if(DECKTIMER){ clearInterval(DECKTIMER); DECKTIMER = null; }
      if(DECKWAS && DECKWAS.playing){ E.jump(DECKWAS.bar); E.play(); }   /* deck mode stopped it; put it back */
      DECKWAS = null; IN.focus();
      line('▸ STUDIO','dim'); }
    draw(); },
  mix: async function(a){
    var v = (a[0]||'').toLowerCase();
    if(v === 'off' || v === 'stop'){ mixStop(); return line('▸ mix off — the decks are yours','dim'); }
    if(!v) return line(CP.mix_usage,'w');
    var pl = null;
    try{ if(token && window.OONTZ_ACCOUNT) pl = await OONTZ_ACCOUNT.req('GET','/playlists/'+v); }catch(e){}
    if(!pl){ try{ var r = await fetch(API+'/p/'+encodeURIComponent(v)); if(r.ok) pl = await r.json(); }catch(e){} }
    if(!pl || !pl.songs || !pl.songs.length) return line('no playable playlist with that id. `playlists` lists yours.','w');
    mixStop(); MIX.q = pl.songs; MIX.i = 0; MIX.deck = 'a'; MIX.on = true;
    if(MODE !== 'deck') CMDS.mode(['deck']);
    line('▸ '+CP.mix_on(pl.title, pl.songs.length),'ok');
    var pr = w('<span class="dim">  rendering '+esc(MIX.q[0].title||MIX.q[0].id)+'…</span>');
    var ok0 = await mixLoad('a', MIX.q[0]); pr.remove();
    if(!ok0){ mixStop(); return line('could not render the first track','w'); }
    E.crossfade(-1); E.decks().a.play(0); MIX.phase = 'play';
    if(MIX.q[1]) mixLoad('b', MIX.q[1]);
    MIX.t = setInterval(mixTick, 400);
    draw(); },
  dload: async function(a){
    var name = (a[0]||'').toLowerCase(), what = a[1]||'this', D = E.decks(), d = D[name];
    if(!d) return line('dload a|b this | <gallery number> | <style>','w');
    var sg = null;
    if(what==='this'){ if(!song) return line(CP.err_nosong,'w'); sg = JSON.parse(JSON.stringify(song)); }
    else if(/^\d+$/.test(what)){ var it = GAL[parseInt(what,10)-1]; if(!it) return line('type `gallery` first','w');
      try{ var r = await fetch(API+'/songs/'+it.id); sg = (await r.json()).data; }catch(e){ return line('could not load that one','w'); }
      /* a private or deleted track answers without a .data, and the undefined used to
         travel all the way into gridFor and die there with nothing on screen */
      if(!sg) return line('that one is not public any more','w'); }
    else if(CO.GENRES[what]) sg = CO.compose(what, 3, 'classic');
    else return line('dload a|b this | <gallery number> | <style>','w');
    if(MODE!=='deck') CMDS.mode(['deck']);
    var pr = w('<span class="dim">  rendering onto '+name+'…</span>');
    try{ var t0 = performance.now(), nm = esc(sg.name);      // inside the try: a bad song must not throw before the catch exists
      /* A deck renders in chunks, so this percentage is real work finished, not a
         guess - and the render yields between chunks, so it actually paints.
         onPartial is the point of the whole thing: the deck becomes playable after
         the FIRST chunk, about a second in, and the rest of the track arrives
         underneath it while you are already mixing. */
      var first = true, playableAt = 0;
      var rr = await OZ.renderSong(sg, function(f){
        pr.innerHTML = '<span class="dim">  ' + (first ? 'rendering ' : 'ready — filling in ') +
          nm + ' on ' + name + '… ' + Math.round(f * 100) + '%</span>';
      }, {raw: true, onPartial: function(part){                // the live master chain does the mastering
        if(first){
          first = false; playableAt = performance.now() - t0;
          d.load(part); DECKFOC = name;
          line('▸ ' + name.toUpperCase() + ' is playable — ' + (playableAt / 1000).toFixed(1) + 's', 'ok');
        } else d.upgrade(part);
        draw();
      }});
      if(first){ d.load(rr); DECKFOC = name; } else d.upgrade(rr);
      pr.innerHTML = '<span class="ok">  '+name.toUpperCase()+' ← '+esc(sg.name)+'</span> <span class="dim">'+mmss(rr.seconds)+' · '+rr.grid.length+' beats on the grid · rendered in '+((performance.now()-t0)/1000).toFixed(1)+'s</span>';
    }catch(e){ pr.innerHTML = '<span class="w">  render failed: '+esc(e.message||e)+'</span>'; }
    draw(); },
  deck: function(a){
    var D = E.decks(), d = D[(a[0]||'').toLowerCase()], sub = (a[1]||'play').toLowerCase();
    if(!d) return line('deck a|b play|pause|sync|loop N|unloop|cue|rate R|next|prev','w');
    if(!d.r) return line('nothing on that deck. dload '+a[0]+' this','w');
    var o = d === D.a ? D.b : D.a; DECKFOC = d.name;
    if(sub==='play') d.play();
    else if(sub==='pause' || sub==='stop') d.stop();
    else if(sub==='cue'){ d.stop(); d.pos0 = 0; }
    else if(sub==='sync'){ if(!o.r) return line('the other deck is empty','w'); d.syncTo(o);
      line('▸ '+d.name+' → '+d.bpm().toFixed(2)+' BPM (rate '+d.rate.toFixed(4)+') · phase '+d.beatPhase().toFixed(3)+' vs '+o.beatPhase().toFixed(3),'dim'); }
    else if(sub==='loop'){ d.loopBeats(parseInt(a[2],10)||4); }
    else if(sub==='unloop'){ d.loopBeats(0); }
    else if(sub==='rate'){ d.setRate(parseFloat(a[2])||1); }
    else if(sub==='next' || sub==='prev'){ line('▸ '+d.name+' → '+d.seekMark(sub==='next'?1:-1),'dim'); }
    else return line('deck a|b play|pause|sync|loop N|unloop|cue|rate R|next|prev','w');
    draw(); },
  eq: function(a){
    var D = E.decks(), d = D[(a[0]||'').toLowerCase()], band = (a[1]||'').toLowerCase(), v = parseFloat(a[2]);
    if(!d || !isFinite(v)) return line('eq a|b low|mid|high 0..2   (0 is a kill)','w');
    if(d.eq(band, v) == null) return line('eq a|b low|mid|high 0..2','w');
    d.kill[band] = v <= 0.001; draw(); line('▸ '+d.name+' '+band+' '+v,'dim'); },
  xf: function(a){ var v = parseFloat(a[0]); if(!isFinite(v)) return line('xf -1..1   (-1 is all A)','w');
    if(v > 1 && v <= 100) v = v/50 - 1;                      // xf 0..100 also works
    E.crossfade(Math.max(-1, Math.min(1, v))); draw(); },
  export: async function(a){
    /* Stems: renderTracks already puts every track on its own channel for the
       ear to measure, so this is that render, split into one WAV each. */
    if((a && a[0]) === 'stems'){
      if(!song) return line(CP.err_nosong,'w');
      E.start();
      var at = OZ.sectionAt(song, E.songbar);
      var bar = EAR.barOfSection(song, at ? at.name : song.order[0]);
      var pr = w('<span class="dim">  rendering every track on its own…</span>');
      try{
        var per = await OZ.renderTracks(song, {bar: bar});
        if(!per.names.length){ pr.remove(); return line('nothing is playing in this section','w'); }
        var C = window.OfflineAudioContext || window.webkitOfflineAudioContext;
        var one = new C(1, per.buf.length, per.buf.sampleRate);
        per.names.forEach(function(n, i){
          var b = one.createBuffer(1, per.buf.length, per.buf.sampleRate);
          b.getChannelData(0).set(per.buf.getChannelData(i));
          var el = document.createElement('a');
          el.href = URL.createObjectURL(OZ.wavBlob(b));
          el.download = 'oontz-'+String(song.name).replace(/[^\w-]+/g,'_')+'-'+n+'.wav';
          document.body.appendChild(el); el.click(); el.remove();
          setTimeout(function(){ URL.revokeObjectURL(el.href); }, 30000);
        });
        pr.innerHTML = '<span class="ok">  '+per.names.length+' stems saved</span> <span class="dim">'+
          esc(per.names.join(', '))+' — one bar of '+esc(at?at.name:'')+'</span>';
      }catch(e){ pr.innerHTML = '<span class="w">  stems failed: '+esc(e.message||e)+'</span>'; }
      return;
    }
    if((a && a[0]) === 'midi'){
      if(!song) return line(CP.err_nosong,'w');
      var bytes = OZ.songToMidi(song);
      var mname = 'oontz-'+song.name.replace(/[^\w-]+/g,'_')+'.mid';
      var mel = document.createElement('a');
      mel.href = URL.createObjectURL(new Blob([bytes], {type:'audio/midi'}));
      mel.download = mname; document.body.appendChild(mel); mel.click(); mel.remove();
      setTimeout(function(){ URL.revokeObjectURL(mel.href); }, 30000);
      return line('▸ '+mname+' — '+(bytes.length/1024).toFixed(1)+'KB of standard MIDI. it opens in any DAW.','ok');
    }
    return CMDS._exportWav();
  },
  _exportWav: async function(){
    if(!song) return line(CP.err_nosong,'w'); E.start();
    var pr = w('<span class="dim">  rendering '+esc(song.name)+' offline…</span>');
    try{ var rr = await OZ.renderSong(song); var name = 'oontz-'+song.name.replace(/[^\w-]+/g,'_')+'.wav';
      saveBlob(OZ.wavBlob(rr.buf), name);
      pr.innerHTML = '<span class="ok">  saved '+esc(name)+'</span> <span class="dim">'+mmss(rr.seconds)+' · 16-bit · the same render the decks use</span>';
    }catch(e){ pr.innerHTML = '<span class="w">  render failed: '+esc(e.message||e)+'</span>'; } }
};
var MODE = 'studio', DECKFOC = 'a', DECKTIMER = null, DECKWAS = null;

/* -- mix: a playlist becomes a set. The scheduler only owns the crossfader while
   a blend is running; grab it (or `mix off`) and the set is yours. -- */
var MIX = {on:false, q:[], i:0, deck:'a', phase:'idle', t:0, b0:0, bms:1};
function mixEase(p){ return p * p * (3 - 2 * p); }
async function mixLoad(name, item){
  try{
    var r = await fetch(API + '/songs/' + encodeURIComponent(item.id));
    var j = await r.json(); if(!j.data) return false;
    var rr = await OZ.renderSong(j.data, null, {raw: true});
    E.decks()[name].load(rr);
    return true;
  }catch(e){ return false; }
}
function mixStop(){ MIX.on = false; MIX.phase = 'idle'; if(MIX.t){ clearInterval(MIX.t); MIX.t = 0; } }
function mixTick(){
  if(!MIX.on || MODE !== 'deck') return;
  var D = E.decks(), cur = D[MIX.deck], oth = D[MIX.deck === 'a' ? 'b' : 'a'];
  if(MIX.phase === 'play'){
    if(!cur.r || !cur.playing) return;
    var left = cur.r.seconds - cur.pos();
    var lead = Math.min(16 * 240 / cur.bpm(), cur.r.seconds / 3);   /* 16 bars, or a third of a short track */
    if(oth.r && !oth.playing && left <= lead){          /* time to begin the blend */
      MIX.phase = 'blend'; MIX.b0 = Date.now(); MIX.bms = Math.max(3000, left * 1000 - 500);
      oth.syncTo(cur); oth.play();
      w('<span class="dim">  ♪ mix: <span class="b">'+esc(oth.r.name)+'</span> coming in over '+Math.round(MIX.bms/1000)+'s</span>');
    } else if(!oth.r && left <= 0.3){                    /* nothing next: the set ends */
      cur.stop(); mixStop(); w('<span class="ok">  ♪ mix done — '+(MIX.i+1)+' tracks.</span>');
    }
  } else if(MIX.phase === 'blend'){
    var p = mixEase(Math.min(1, (Date.now() - MIX.b0) / MIX.bms));
    var from = MIX.deck === 'a' ? -1 : 1;
    E.crossfade(from * (1 - 2 * p));
    if(p >= 1){
      cur.stop(); var freed = MIX.deck;
      MIX.deck = MIX.deck === 'a' ? 'b' : 'a'; MIX.i++; MIX.phase = 'play';
      var nxt = MIX.q[MIX.i + 1];
      if(nxt) mixLoad(freed, nxt); else D[freed].r = null;
      draw();
    }
  }
}
var DECK_KEYS = [
  ["1 / 2", "focus deck A / B"], ["space", "play / pause the focused deck"], ["s", "sync it to the other deck"],
  ["l / u", "4-beat loop / unloop"], [", .", "crossfader toward A / B"], ["7 8 9", "kill low / mid / high"],
  ["[ ]", "sweep the master filter"], ["\\", "spinback"], ["< >", "previous / next phrase"], ["M", "back to the studio"]
];
function deckKey(k){
  var D = E.decks(), d = D[DECKFOC], o = d === D.a ? D.b : D.a;
  if(k==='1' || k==='2'){ DECKFOC = k==='1'?'a':'b'; return 'deck '+DECKFOC; }
  if(k==='M' || k==='m'){ CMDS.mode(['studio']); return 'studio'; }
  if(k===',' || k==='.'){ E.crossfade(Math.max(-1, Math.min(1, D.xf + (k===','?-0.1:0.1)))); return 'xf '+D.xf.toFixed(1); }
  if(k==='[' || k===']' || k==='\\' || k==='`') return E.key(k, true);
  if(!d.r) return 'deck '+DECKFOC+' is empty';
  if(k===' '){ if(d.playing) d.stop(); else d.play(); return d.playing?'play '+DECKFOC:'pause '+DECKFOC; }
  if(k==='s'){ if(!o.r) return 'the other deck is empty'; d.syncTo(o); return 'sync '+DECKFOC+' → '+d.bpm().toFixed(2)+' BPM'; }
  if(k==='l'){ d.loopBeats(4); return 'loop 4'; }
  if(k==='u'){ d.loopBeats(0); return 'loop off'; }
  if(k==='7' || k==='8' || k==='9'){ var band = {7:'low',8:'mid',9:'high'}[k]; var on = !d.kill[band];
    d.kill[band] = on; d.eq(band, on ? 0 : 1); return DECKFOC+' '+band+(on?' killed':' back'); }
  if(k==='<' || k==='>') return '→ '+d.seekMark(k==='>'?1:-1);
  return null;
}
var REC = null, PENDING = null, UNDO = [], EARLAST = null, UNDO_LAST = null, UNDO_AT = 0;
var CLIP = false;              /* one clip at a time - two recorders fight over the canvas */
var SHARED_URL = '';           /* the last link minted this session, burned into a clip */
var SHARED_ID  = '';           /* which song that link IS, so re-sharing updates it instead of minting a twin */
var REMIX_OF = null;                             /* set by `remix`, carried by `publish` */
var PRODUCING = false;                           /* produce owns the AI while it runs; jam waits */
async function askAI(prompt, extraState){
  var at = song ? OZ.sectionAt(song, E.songbar) : null;
  var state = {bpm: E.bpm, swing: E.swing, key: song && song.key, scale: song && song.scale,
    section: at && at.name, role: at && at.sec.role, bar: E.songbar, tracks: E.tracks, order: E.order,
    commands: Object.keys(CMDS).concat(E.order)};
  if(extraState) Object.keys(extraState).forEach(function(k){ state[k] = extraState[k]; });
  var hdr = {'content-type':'application/json'};
  var myKey = localStorage.getItem('oontz_key'); if(myKey) hdr['x-anthropic-key'] = myKey;
  var src = (extraState && extraState.source) || 'askAI', t0 = Date.now();
  ev('ai_ask', {source: src, prompt_len: String(prompt||'').length, text: String(prompt||'').slice(0,300)});
  try{
    var r = await fetch(API+'/ai/ask', {method:'POST', headers:hdr,
      body: JSON.stringify({prompt: prompt, state: state})});
    var j = await r.json();
    ev('ai_result', {source: src, ms: Date.now()-t0, n: (j.commands||[]).length,
                     ok: (j.commands||[]).length ? 1 : 0});
    return j;
  }catch(e){ ev('ai_result', {source: src, ms: Date.now()-t0, n: 0, ok: 0,
                              error: String(e && e.message || e).slice(0,120)}); throw e; }
}

/* The model proposes music, never account actions. It has no business reaching
   `publish`, `login`, `key`, `playlist del` or `rec`, and the server prompt already
   claims the client refuses - this is what makes that true. Anything not on the
   list is shown struck through and skipped. */
/* Commands that change the song, and therefore take an undo snapshot. */
var MUTATES = {};
("bpm swing gain pan filter tune sidechain mute solo compose go improve produce " +
 "dream load remix sec name").split(" ").forEach(function(v){ MUTATES[v] = 1; });

/* `go` and `compose` replace the entire song, which is a thing the model may
   legitimately propose - you see the line and press Enter. `song` is NOT here:
   it is an alias for `go` (ALIAS, below), so leaving it in let a bare `song`
   pass the filter and recompose everything while looking like a query. Aliases
   are resolved before the check now, so no alias can smuggle a verb past it. */
var MUSICAL = ("bpm swing gain pan filter tune sidechain mute solo focus compose go " +
  "play stop grade improve freq why styles curves theory rules bands sec name " +
  "save load stems").split(" ");
function musical(cmd){
  var v0 = String(cmd).trim().split(/\s+/)[0].toLowerCase();
  var v = ALIAS[v0] || v0;                       // resolve first, or an alias walks straight through
  return MUSICAL.indexOf(v) >= 0 || !!(E.tracks && E.tracks[v]) || !!OZ.VOICES[v];
}
var TEACH = false, TOLD = {}, LESSON_AT = -1;
/* Set for a first-time visitor's very first pattern edit, and cleared by it: the
   moment they change a character and hear it, they have done the whole idea, and
   that is the one moment worth naming. */
var FIRSTEDIT = false;

/* ---------------------------------------------------------- teaching by doing */
/* One line, the first time you touch a thing. Never twice - a tutor that repeats
   itself is a nag, and this is the same table the desktop teaches from. */
function teach(verb){
  if(!TEACH || TOLD[verb]) return;
  var txt = ((window.OONTZ_THEORY||{}).why||{})[verb];
  if(!txt) return;
  TOLD[verb] = 1;
  w('<span class="dim">  ⓘ '+esc(txt.split(". ")[0])+'.</span>');
}

var LESSON = [
  ["a kick", "type <span class=\"a\">kick x...x...x...x...</span> — four on the floor, the heartbeat of the whole genre.",
   function(){ return hasHits('kick'); }],
  ["press play", "type <span class=\"a\">play</span>, or press Esc then space. It loops until you stop it; nothing here breaks.",
   function(){ return E.playing; }],
  ["hats", "type <span class=\"a\">hat ..x...x...x...x.</span> — between the kicks. A hat on the offbeat is why house feels faster than it is.",
   function(){ return hasHits('hat'); }],
  ["by hand", "press Esc to leave the prompt, then <span class=\"a\">2</span> to focus the hats and <span class=\"a\">k</span> to toggle step 16. Or just click the step in the rack.",
   function(){ var t=E.tracks.hat; return t && t.pat && /[xX]/.test(t.pat.slice(15,16)); }],
  ["a bassline", "type <span class=\"a\">bass a1 . a1~ . c2 . a1 .</span> — a1 is a note, ~ slides into the next one.",
   function(){ return hasHits('bass'); }],
  ["get out of the kick's way", "type <span class=\"a\">sidechain bass 0.7</span> — now the bass ducks on every kick instead of fighting it for the same 60Hz.",
   function(){ var t=E.tracks.bass; return t && t.sc >= 0.5; }],
  ["a whole song", "type <span class=\"a\">go</span>. That is the arrangement grammar writing you a track, drop and all.",
   function(){ return !!song; }],
  ["let it mark its own homework", "type <span class=\"a\">grade</span>. It renders the loudest section and measures it — then <span class=\"a\">improve</span> fixes what it finds.",
   function(){ return !!EARLAST; }]
];
function hasHits(n){ var t = E.tracks[n]; return !!(t && t.pat && t.pat.replace(/[.\-]/g,'').length); }
function lessonStep(){
  if(LESSON_AT < 0) return;
  if(LESSON_AT >= LESSON.length){ LESSON_AT = -1; line();
    w('<span class="ok">  that is the whole instrument.</span> <span class="dim">everything else is more of this. <span class="a">help</span> for the rest.</span>'); line(); return; }
  var st = LESSON[LESSON_AT]; line();
  w('<span class="a2">  '+(LESSON_AT+1)+'/'+LESSON.length+'  '+esc(st[0])+'</span>');
  w('<span class="dim">  '+st[1]+'</span>');
}
function lessonCheck(){
  if(LESSON_AT < 0 || LESSON_AT >= LESSON.length) return;
  if(LESSON[LESSON_AT][2]()){ LESSON_AT++;
    w('<span class="ok">  ✓</span>'); lessonStep(); }
}

/* ------------------------------------------------------------- the palette */
var PAL = document.getElementById('pal'), PALIN = document.getElementById('palin'),
    PALLIST = document.getElementById('pallist'), PALSEL = 0, PALROWS = [];
function palItems(){
  var out = [], T = window.OONTZ_THEORY || {};
  (CP.help||[]).forEach(function(kv){ out.push([kv[0], kv[1], kv[0]]); });
  Object.keys(CMDS).forEach(function(c){
    if(!out.some(function(o){ return o[2].split(' ')[0] === c; })) out.push([c, 'command', c]); });
  Object.keys(CO.GENRES||{}).forEach(function(g){
    out.push(['compose '+g, T.genres && T.genres[g] ? T.genres[g].note : 'a whole song', 'compose '+g+' 5']); });
  Object.keys(T.why||{}).forEach(function(k){ out.push(['why '+k, T.why[k].split('. ')[0], 'why '+k]); });
  (E.order||[]).forEach(function(n){ out.push(['focus '+n, 'the pads edit '+n, 'focus '+n]); });
  Object.keys(OZ.VOICES).forEach(function(n){
    var r = (T.freq_roles||{})[n];
    out.push([n+' x...x...x...x...', r ? r.note : 'a pattern on '+n, n+' x...x...x...x...']); });
  return out;
}
/* subsequence match, so "cmpac" finds "compose acid" */
function fuzzy(q, s){
  q = q.toLowerCase(); s = s.toLowerCase();
  if(!q) return 0;
  var i = 0, score = 0, last = -1;
  for(var k = 0; k < s.length && i < q.length; k++){
    if(s[k] === q[i]){ score += (last === k-1 ? 3 : 1) + (k === 0 ? 5 : 0); last = k; i++; }
  }
  return i === q.length ? score : -1;
}
function palRender(){
  var q = PALIN.value.trim();
  PALROWS = palItems().map(function(it){ return {it: it, s: q ? fuzzy(q, it[0]+' '+it[1]) : 1}; })
    .filter(function(r){ return r.s >= 0; })
    .sort(function(a, b){ return b.s - a.s; }).slice(0, 60).map(function(r){ return r.it; });
  if(PALSEL >= PALROWS.length) PALSEL = 0;
  PALLIST.innerHTML = PALROWS.map(function(it, i){
    return '<div class="pi'+(i===PALSEL?' sel':'')+'" data-i="'+i+'"><span class="pc">'+
      esc(it[0])+'</span><span class="pd">'+esc(it[1])+'</span></div>'; }).join('');
  var sel = PALLIST.querySelector('.sel'); if(sel) sel.scrollIntoView({block:'nearest'});
}
function openPal(){ PAL.classList.add('on'); PAL.dataset.from = ''; document.body.classList.add('palout'); PALIN.value=''; PALSEL=0; palRender(); PALIN.focus(); }
function closePal(){ PAL.classList.remove('on'); document.body.classList.remove('palout');
  if(MODE === 'deck') IN.blur(); else IN.focus(); }   /* focusing the prompt would re-deafen the deck keys */
function palRun(){ var it = PALROWS[PALSEL]; if(!it) return; closePal(); run(it[2]); }
PALIN.addEventListener('input', function(){ PALSEL = 0; palRender(); });
PALIN.addEventListener('keydown', function(e){
  if(e.key === 'Escape'){ e.preventDefault(); closePal(); }
  else if(e.key === 'Enter'){ e.preventDefault(); palRun(); }
  else if(e.key === 'ArrowDown'){ e.preventDefault(); PALSEL = Math.min(PALROWS.length-1, PALSEL+1); palRender(); }
  else if(e.key === 'ArrowUp'){ e.preventDefault(); PALSEL = Math.max(0, PALSEL-1); palRender(); }
  e.stopPropagation();
});
PALLIST.addEventListener('click', function(e){
  var row = e.target.closest('.pi'); if(!row) return;
  PALSEL = +row.dataset.i; palRun();
});
/* Dismiss only if the press STARTED on the backdrop. A tap is one gesture, but the
   click it produces is hit-tested where the finger LIFTS - and ⌘ opens the palette on
   pointerdown, so by the time the finger comes up the overlay is already covering the
   button. The click then landed on #pal and shut the palette in the same tap: on a
   phone the command button simply did not work. (Mouse users never saw it: a click
   whose down and up have different targets is dispatched on their common ancestor.)
   It also stops a drag that starts in the input and ends on the backdrop from closing. */
PAL.addEventListener('pointerdown', function(e){ PAL.dataset.from = e.target === PAL ? '1' : ''; });
PAL.addEventListener('click', function(e){ if(e.target === PAL && PAL.dataset.from === '1') closePal(); });
var EAR = window.OONTZ_EAR;
function sev(k){ return {good:'<span class="ok">  ✓ ', warn:'<span class="w">  ! ',
                         bad:'<span class="hot">  ✗ '}[k] || '<span class="dim">  '; }
/* -- rooms: a chatroom whose messages happen to be music. Local musical
   commands broadcast; incoming ones run, echoed as ◂ handle. Everyone hears
   their own render of the same evolving song (shared clock is the v2). -- */
var ROOM = {code: null, ws: null, others: 0, remote: false, retried: false};
function roomWire(cmd){                          /* pure: should this line broadcast? */
  if(!ROOM.ws || ROOM.remote) return false;
  return musical(cmd);
}
function roomSend(obj){
  try{ if(ROOM.ws && ROOM.ws.readyState === 1) ROOM.ws.send(JSON.stringify(obj)); }catch(e){}
}
function roomJoin(code){
  var url = API.replace(/^http/, 'ws') + '/ws/room/' + encodeURIComponent(code);
  var ws = new WebSocket(url);
  ws.onopen = function(){
    ROOM.code = code; ROOM.ws = ws; ROOM.retried = false;
    roomSend({t: 'hello', handle: (localStorage.getItem('oontz_handle') || 'someone')});
    if(!song) roomSend({t: 'sync?'});
    line('▸ '+CP.room_in(code), 'ok'); draw();
  };
  ws.onmessage = function(ev){
    var m; try{ m = JSON.parse(ev.data); }catch(e){ return; }
    if(m.t === 'hello'){ ROOM.others++;
      w('<span class="dim">  ◂ '+esc(m.from)+' joined the room</span>');
      roomSend({t: 'here', to: m.from});         /* so the joiner can count us */
      if(song) roomSend({t: 'song', doc: song});
      draw(); return; }
    if(m.t === 'here'){
      if(m.to === (localStorage.getItem('oontz_handle') || 'someone')) ROOM.others++;
      draw(); return; }
    if(m.t === 'bye'){ ROOM.others = Math.max(0, ROOM.others - 1);
      w('<span class="dim">  ◂ '+esc(m.from)+' left</span>'); draw(); return; }
    if(m.t === 'sync?'){ if(song) roomSend({t: 'song', doc: song}); return; }
    if(m.t === 'song' && m.doc && !ROOM.gotSong){
      ROOM.gotSong = true;
      if(song) snapshot();
      ROOM.remote = true;
      try{ loadSong(m.doc, 'the room\u2019s track'); }finally{ ROOM.remote = false; }
      return; }
    if(m.t === 'cmd' && m.line){
      w('<span class="a2">◂ '+esc(m.from||'someone')+'</span> <span class="dim">'+esc(m.line)+'</span>');
      ROOM.remote = true;
      try{ run(m.line); }finally{ ROOM.remote = false; }
      return; }
  };
  ws.onclose = function(){
    if(ROOM.code && !ROOM.retried){ ROOM.retried = true;
      w('<span class="dim">  the room dropped — retrying once…</span>');
      setTimeout(function(){ if(ROOM.code) roomJoin(ROOM.code); }, 1500);
    } else if(ROOM.code){
      line('the room is gone — you are solo again','w');
      ROOM.code = null; ROOM.ws = null; ROOM.others = 0; draw();
    }
  };
}
var JAM = {on:false, bars:8, mark:0, turns:0, busy:false, style:''};
setInterval(async function(){
  if(!JAM.on || JAM.busy || PRODUCING || !E.playing || MODE === 'deck' || !song) return;
  var total = OZ.totalBars(song), gone = (E.songbar - JAM.mark + total) % total;
  if(gone < JAM.bars) return;
  JAM.mark = E.songbar; JAM.busy = true;
  try{
    var at = OZ.sectionAt(song, E.songbar);
    var crit = CO.critique(song), sc = CO.score(crit);   /* jam has ears: it hears what the grader hears */
    var faults = crit.filter(function(c){ return c[0] !== 'good'; }).slice(0, 4).map(function(c){ return c[1]; });
    var state = {bpm: E.bpm, swing: E.swing, key: song.key, scale: song.scale,
      section: at && at.name, role: at && at.sec.role, bar: E.songbar, tracks: E.tracks, order: E.order,
      commands: Object.keys(CMDS).concat(E.order), jam_turn: ++JAM.turns,
      grade: {score: sc, faults: faults}};
    var hdr = {'content-type':'application/json'};
    var myKey = localStorage.getItem('oontz_key'); if(myKey) hdr['x-anthropic-key'] = myKey;
    ev('ai_ask', {source: 'jam', turn: JAM.turns, style: String(JAM.style||'').slice(0,60)});
    var r = await fetch(API+'/ai/ask', {method:'POST', headers:hdr,
      body: JSON.stringify({prompt: 'JAM TURN '+JAM.turns+': you are playing live alongside a human, currently in the '
        +(at ? at.name : 'song')+'. Make exactly ONE small, tasteful, reversible move that fits this moment - vary a pattern, '
        +'nudge a filter or gain, thin or thicken one element. Two lines only if inseparable. Subtle beats clever; '
        +'never touch more than one track. If state.grade lists faults, prefer the move that fixes one. '
        +(JAM.style ? 'Mood bias, from the human: '+JAM.style+'. ' : '')
        +'End with one line: "# <six words or fewer on why>".', state: state})});
    var j = await r.json();
    ev('ai_result', {source: 'jam', turn: JAM.turns, n: (j.commands||[]).length,
                     ok: (j.commands||[]).length ? 1 : 0});
    if(j.commands && j.commands.length){
      snapshot();
      w('<span class="dim">  ♪ jam'+(j.why ? ': <span class="b">'+esc(j.why)+'</span>' : ':')+'</span>');
      j.commands.slice(0, 2).forEach(run);
      w('<span class="dim">  ♪ <span class="a">undo</span> vetoes it · jam off ends it</span>');
    }
  }catch(e){}
  JAM.busy = false;
}, 700);
/* Undo used to cover only the AI's moves: `improve`, `produce`, `dream`, an
   accepted `ask`, and a rack click. Every typed pattern, every pad, and every
   mixer verb changed the song without recording anything - so pressing undo after
   typing `gain hat 0.4` silently reverted to whatever the AI last did, which is
   worse than not having undo at all.

   `label` is what you are undoing, so it can say so. A gesture that fires many
   times - dragging across the rack, holding a pad - coalesces into one entry;
   past a second of quiet, the next change starts a new one. */
/* The local library is one storage key, so a quota failure is one failure. */
function readLib(){
  try { return JSON.parse(localStorage.getItem('oontz_lib') || '{}'); } catch(e){ return {}; }
}
function writeLib(lib){
  try { localStorage.setItem('oontz_lib', JSON.stringify(lib)); return true; }
  catch(e){ return false; }
}
function ago(t){
  var s = Math.max(0, (Date.now() - (t||0)) / 1000);
  if(s < 90) return 'just now';
  if(s < 5400) return Math.round(s/60) + ' min ago';
  if(s < 172800) return Math.round(s/3600) + ' h ago';
  return Math.round(s/86400) + ' d ago';
}

function snapshot(label){
  if(!song) return;
  var now = Date.now();
  if(label && label === UNDO_LAST && now - UNDO_AT < 900){ UNDO_AT = now; return; }
  UNDO_LAST = label || null; UNDO_AT = now;
  UNDO.push({song: JSON.parse(JSON.stringify(song)), label: label || "that"});
  if(UNDO.length > 40) UNDO.shift();
}
function undoOne(){
  if(!UNDO.length) return null;
  var e = UNDO.pop();
  UNDO_LAST = null;
  song = e.song; E.loadSong(song); draw();
  return e.label;
}
var GAL = [];
var ALIAS = {'?':'help','ls':'help','start':'go','make':'go','song':'go','q':'stop','wav':'export','render':'export','crossfade':'xf',
  'send':'share','post':'share','video':'clip','github':'repo','source-code':'repo',
  'tos':'terms','legal':'terms',
  'exit':'stop','quit':'stop','cls':'clear','about':'what','dj':'decks','keymap':'keys',
  'm':'decks','deck':'decks',
  'critique':'grade','score':'grade','signin':'login','account':'login'};

/* Every typed line, every AI-proposed line and every egg goes through here, so
   this is the one place that knows which verbs people actually reach for and
   which ones blow up.
   ponytail: `ms` is dispatch time, not completion — the async commands return a
   promise this does not await. Await it if per-command latency ever matters. */
function run(raw){
  var t0 = Date.now(), s0 = (raw||'').trim();
  if(!s0) return;
  var v0 = s0.split(/\s+/)[0].toLowerCase(), v = ALIAS[v0] || v0;
  try{ var r = runCmd(raw); ev('cmd_result', {verb: v, ok: 1, ms: Date.now()-t0}); return r; }
  catch(err){ ev('cmd_result', {verb: v, ok: 0, error: String(err && err.message || err).slice(0,120),
                                ms: Date.now()-t0}); throw err; }
}
function runCmd(raw){
  var s=(raw||'').trim(); if(!s) return;
  w('<span class="a2">oontz.sh &gt;</span> '+esc(s));
  var parts=s.split(/\s+/), v0=parts[0], args=parts.slice(1);
  var v=ALIAS[v0.toLowerCase()]||v0.toLowerCase();
  if(E.tracks && !E.tracks[v] && OZ.VOICES[v] && args.length){
    E.start(); E.setTrack(v, {voice: v, pat: "", gain: 1});   // name a voice and you have a track
  }
  /* Anything that edits the song records it first, so undo means the last thing
     YOU did rather than the last thing the AI did. */
  if(MUTATES[v] || (E.tracks && E.tracks[v] && args.length)) snapshot(v);
  if(E.tracks && E.tracks[v]){
    if(args.length === 2 && /^\*\d+$/.test(args[1])) args = [OZ.expandPat(args)];  // x... *4
    var pat=args[0]||'';
    if(args.length>1 || /^[a-g]/i.test(pat)){        // notes: bass a1 . a1~ c2!
      var notes=args.map(function(t){ return t.toLowerCase(); });
      if(!notes.every(function(t){ return t==='.'||t==='-'||OZ.noteHz(t)>0; })) return line(CP.err_pattern,'w');
      E.setTrack(v,{notes:notes, pat:notes.map(function(t){ return t==='.'||t==='-'?'.':(t.indexOf('!')>=0?'X':'x'); }).join('')});
    } else {
      if(!/^[xXoO.\-?]+$/.test(pat)) return line(CP.err_pattern,'w');
      E.setTrack(v,{pat:pat}); }
    if(!E.playing) E.play(); draw();
    line('▸ '+v+' '+args.join(' '),'dim');
    if(FIRSTEDIT){                               /* they just did the whole idea; say so once */
      FIRSTEDIT = false;
      line();
      w('<span class="ok">  ' + esc(CP.first_after || 'you just edited music by typing.') + '</span>');
      ev('first_run', {step: 'edited', verb: v});
    }
    teach(v); setTimeout(lessonCheck, 60); return; }
  if(v === 'bpm' && args[0] === '420'){ var rr = CMDS.bpm(['420']); line('medicinal.','dim'); return rr; }
  if(CMDS[v]){ var r = CMDS[v](args); teach(v); setTimeout(lessonCheck, 60); return r; }
  if(s.toLowerCase().indexOf('boots and cats') === 0){
    snapshot(); run('kick x.x.x.x.x.x.x.x.'); run('hat .x.x.x.x.x.x.x.x');
    return line(CP.egg_boots || 'that is, verbatim, how techno is pronounced.','ok'); }
  if(v === 'dance') return dance();
  if(v === 'credits') return credits();
  if(v === 'sudo') return line(CP.egg_sudo || 'this incident will be reported to the groove authorities.','w');
  var dym = didYouMean(v, Object.keys(CMDS).concat(Object.keys(E.tracks || {})));
  if(dym) return w('<span class="w">no `'+esc(v0)+'`. did you mean <span class="k">'+esc(dym)+'</span>?</span>');
  /* Plenty of people arrive assuming this is a chatbot and type a sentence. That
     used to resolve to a verb like `how`, miss the typo table above, and print
     "how: no" - a dead end, with the AI that could have answered it one invisible
     word away. A greeting gets a greeting; anything sentence-shaped gets asked. */
  if(GREETING.test(v)) return w('<span class="dim">  '+esc(CP.nl_hello ? CP.nl_hello(v0)
    : 'this is an instrument, not a chatbot — try `go`.')+'</span>');
  if(looksLikeProse(s, parts)){
    line(CP.nl_route || 'not a command — passing it to the AI.','dim');
    ev('nl_fallback', {words: parts.length, q: s.slice(0, 120)});
    return CMDS.ask(parts);
  }
  line(CP.err_cmd?CP.err_cmd(v0):v0+': no', 'w');
}
var GREETING = /^(hi|hey|hello|yo|sup|hiya|howdy|thanks|thankyou|ta|cheers|ok|okay|lol|wow|nice|cool)$/;
/* Sentence-shaped, not command-shaped. Everything the instrument actually takes is
   a verb plus terse arguments, and every one of those has already been handled by
   the time this runs - so a question mark, or three-plus words none of which named
   a track or a verb, is prose. Two words is left alone deliberately: `foo bar` is
   far more likely a typo'd command than a question, and didYouMean owns that. */
function looksLikeProse(s, parts){
  if(/\?\s*$/.test(s)) return true;
  if(parts.length < 3) return false;
  return /^[a-z' ]+$/i.test(s.replace(/[.,!?]/g, ''));   /* words, not patterns like x..x */
}

/* one-typo forgiveness: closest verb within edit distance 1 (2 for long words) */
function didYouMean(v, verbs){
  if(v.length < 3) return null;
  var best = null, bestD = (v.length > 6 ? 2 : 1) + 1;
  verbs.forEach(function(w2){
    if(Math.abs(w2.length - v.length) >= bestD) return;
    var d = lev(v, w2);
    if(d < bestD){ bestD = d; best = w2; }
  });
  return bestD <= (v.length > 6 ? 2 : 1) ? best : null;
}
function lev(a, b){
  var m = a.length, n = b.length, row = [];
  for(var j = 0; j <= n; j++) row[j] = j;
  for(var i = 1; i <= m; i++){
    var prev = row[0]; row[0] = i;
    for(var k = 1; k <= n; k++){
      var cur = row[k];
      row[k] = Math.min(row[k] + 1, row[k-1] + 1, prev + (a[i-1] === b[k-1] ? 0 : 1));
      prev = cur;
    }
  }
  return row[n];
}
var DANCER = ['(>\'-\')>','^(\'-\')^','<(\'-\'<)','^(\'-\')^'];
var DANCE_T = 0;
function dance(){
  if(DANCE_T) clearInterval(DANCE_T);
  var d = w('<span class="a">  '+esc(DANCER[0])+'</span>'), i2 = 0, beats = 0;
  var per = Math.max(120, 60000 / (E.bpm || 128));
  DANCE_T = setInterval(function(){
    i2 = (i2 + 1) % DANCER.length; beats++;
    d.innerHTML = '<span class="a">  '+esc(DANCER[i2])+'</span>';
    if(beats >= 8){ clearInterval(DANCE_T); DANCE_T = 0;
      d.innerHTML += ' <span class="dim">— it had to stop somewhere</span>'; }
  }, per);
}
function credits(){
  line();
  [['every sound','arithmetic'],['every bug','also arithmetic'],
   ['the grader','ruthless, correct'],['the AI','in the room, knows it'],
   ['you','the good part']].forEach(function(kv){
    w('  <span class="dim">'+esc(kv[0])+'</span>  <span class="b">'+esc(kv[1])+'</span>'); });
  line();
}
var _soloRun = run;
run = function(raw){                             /* the room hears every musical move */
  var s = (raw||'').trim();
  var out = _soloRun(raw);
  if(s && roomWire(s)) roomSend({t: 'cmd', line: s});
  return out;
};

/* ------------------------------------------------- the prompt, as a real one
   History, completion and a hint strip. A terminal without ↑ and Tab is a text
   box wearing a terminal costume. */
var HINT = document.getElementById('hint');
var HIST = [], HI = 0, DRAFT = '', TABS = null;
try { HIST = JSON.parse(localStorage.getItem('oontz_hist') || '[]'); } catch(e){}
HI = HIST.length;

function verbs(){
  return Object.keys(CMDS).concat(Object.keys(ALIAS), Object.keys(E.tracks || {}))
    .filter(function(v, i, a){ return a.indexOf(v) === i; }).sort();
}
function usageFor(v){
  var row = (CP.help || []).filter(function(kv){ return kv[0].split(' ')[0] === v; })[0];
  if(row) return row[0] + '   ' + row[1];
  if(E.tracks && E.tracks[v]) return v + ' x...x...x...x...   a pattern for ' + v +
    (E.tracks[v].notes ? ', or notes: ' + v + ' a1 . c2 .' : '');
  return null;
}
/* PgUp/PgDn/Home/End scroll the log from anywhere, typing or performing. */
function scrollKey(k){
  var page = OUT.clientHeight * 0.85;
  if(k === 'PageUp') OUT.scrollTop -= page;
  else if(k === 'PageDown') OUT.scrollTop += page;
  else if(k === 'Home') OUT.scrollTop = 0;
  else if(k === 'End') { tail(); return true; }
  else return false;
  TAIL.classList.toggle('on', !atBottom());
  return true;
}
function hint(){
  var v = IN.value, parts = v.trim().split(/\s+/), head = (parts[0] || '').toLowerCase();
  if(!v.trim()){ HINT.innerHTML = PENDING
    ? '<b>Enter</b> runs the ' + PENDING.length + ' proposed lines · type anything else to discard'
    : ''; return; }
  if(parts.length > 1 || v.slice(-1) === ' '){
    var u = usageFor(ALIAS[head] || head);
    HINT.innerHTML = u ? esc(u).replace(/^(\S+)/, '<b>$1</b>') : '';
    return;
  }
  var hits = verbs().filter(function(x){ return x.indexOf(head) === 0; });
  if(!hits.length){ HINT.innerHTML = '<span style="color:var(--warn)">no command starts with ' + esc(head) + '</span>'; return; }
  if(hits.length === 1){ var u2 = usageFor(ALIAS[hits[0]] || hits[0]);
    HINT.innerHTML = '<i>' + esc(hits[0]) + '</i>' + (u2 ? '   ' + esc(u2.replace(/^\S+\s*/, '')) : '') + '   <span style="opacity:.7">Tab</span>';
    return; }
  HINT.innerHTML = hits.slice(0, 9).map(function(x, i){
    return i ? '<b>' + esc(x) + '</b>' : '<i>' + esc(x) + '</i>'; }).join('  ') +
    (hits.length > 9 ? '  <span style="opacity:.6">+' + (hits.length - 9) + '</span>' : '') +
    '   <span style="opacity:.7">Tab</span>';
}
/* The dropdown: what you could type, visible and pickable. ArrowDown enters it,
   Enter/Tab takes the highlighted row, a tap takes any row, Esc dismisses. With
   nothing highlighted every key behaves exactly as before. */
var SUG = document.createElement('div'); SUG.id = 'sug';
document.getElementById('bar').appendChild(SUG);
var SUGS = {hits: [], i: -1};
function sugClose(){ SUGS.hits = []; SUGS.i = -1; SUG.classList.remove('on'); }
function sugRender(){
  if(!SUGS.hits.length) return sugClose();
  SUG.innerHTML = SUGS.hits.map(function(v, i){
    var u = usageFor(ALIAS[v] || v) || '';
    return '<div data-v="'+esc(v)+'"'+(i===SUGS.i?' class="sel"':'')+'><b>'+esc(v)+'</b><span>'+
      esc(u.replace(/^\S+\s*/, ''))+'</span></div>';
  }).join('');
  SUG.classList.add('on');
}
/* Verbs whose whole job is the argument. Running these bare only prints a usage
   line, so a tap fills the box and leaves the dropdown to offer the argument next. */
var NEEDS_ARG = ('bpm gain pan filter tune mute solo sidechain swing focus name save ' +
  'forget load remix diff open dload eq xf sec style dream ask key handle login take mix'
  ).split(' ');
function needsArg(v){
  return NEEDS_ARG.indexOf(v) >= 0 || argHits(v, '').length > 0;
}

/* Tapping a suggestion RUNS it, which is the only thing a tap can sensibly mean.
   Two things it must not do, both of which it used to:
     - leave the text sitting in the box, so the tap looked like it did nothing;
     - lose focus. The drum pads are gated on `document.activeElement === IN`, so a
       tap that dropped focus turned every following letter into a kick. Focus is
       taken FIRST, while the row is still under the finger, and the list is closed
       on the next frame - closing it here retargets the click to the log beneath,
       which is how a tap could even run some other command printed down there. */
function sugPick(v){
  IN.focus();
  if(needsArg(v)){ IN.value = v + ' '; hint(); requestAnimationFrame(function(){ sugClose(); suggest(); }); return; }
  IN.value = ''; hint();
  requestAnimationFrame(sugClose);
  run(v);
}
var ARGS = {
  gallery: ['pat','like','top'], viz: [], theme: [], room: ['new','who','leave'],
  source: ['save','copy'], export: ['midi','stems'], diff: ['take'], jam: ['on','off','style'],
  mix: ['off'], playlist: ['new','add','public','del'], tilt: ['off'], watch: [],
  share: ['why','link'], clip: []
};
function argHits(verb, partial){
  var base = ARGS[verb];
  if(verb === 'viz' && window.OONTZ_VIZ) base = ['auto','off'].concat(Object.keys(OONTZ_VIZ.MODES));
  if(verb === 'theme' && window.OONTZ_VIZ) base = Object.keys(OONTZ_VIZ.THEMES).concat(['random','make','del']);
  if(!base) return [];
  return base.filter(function(a2){ return a2.indexOf(partial) === 0 && a2 !== partial; }).slice(0, 6);
}
function suggest(){
  var v = IN.value, parts = v.trim().split(/\s+/), head = (parts[0]||'').toLowerCase();
  if(head && (parts.length === 2 || (parts.length === 1 && v.slice(-1) === ' '))){
    var verb = ALIAS[head] || head;
    var partial = (parts[1] || '').toLowerCase();
    var ah = argHits(verb, partial);
    if(ah.length){ SUGS.hits = ah.map(function(a2){ return head + ' ' + a2; });
      if(SUGS.i >= SUGS.hits.length) SUGS.i = -1;
      sugRender(); return; }
  }
  if(!head || parts.length > 1 || v.slice(-1) === ' ') return sugClose();
  var hits = verbs().filter(function(x){ return x.indexOf(head) === 0 && x !== head; }).slice(0, 6);
  SUGS.hits = hits; if(SUGS.i >= hits.length) SUGS.i = -1;
  sugRender();
}
SUG.addEventListener('pointerdown', function(e){
  e.preventDefault();
  var d = e.target.closest('[data-v]'); if(d) sugPick(d.dataset.v);
});

IN.addEventListener('input', function(){ TABS = null; hint(); suggest(); });

/* What the line COST to type - not what was typed. The text itself rides on
   prompt_submit; the keystroke stream is counted and thrown away. */
var KS = {n: 0, back: 0, at: 0, paste: 0};
function ksReset(){ KS = {n: 0, back: 0, at: 0, paste: 0}; }
IN.addEventListener('paste', function(){ KS.paste = 1; });

IN.addEventListener('keydown', function(e){
  var kk = e.key || '';
  if(!KS.at) KS.at = Date.now();
  if(kk === 'Backspace') KS.back++; else if(kk.length === 1) KS.n++;
  if((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')){ e.preventDefault(); openPal(); return; }
  if(scrollKey(e.key)){ e.preventDefault(); return; }
  if(SUGS.hits.length){
    if(e.key === 'ArrowDown'){ e.preventDefault(); SUGS.i = (SUGS.i + 1) % SUGS.hits.length; sugRender(); return; }
    if(e.key === 'ArrowUp' && SUGS.i >= 0){ e.preventDefault(); SUGS.i--; sugRender(); return; }
    if((e.key === 'Enter' || e.key === 'Tab') && SUGS.i >= 0){ e.preventDefault(); sugPick(SUGS.hits[SUGS.i]); return; }
    if(e.key === 'Escape'){ e.preventDefault(); sugClose(); return; }
  }
  if(e.key==='Enter'){ var v=IN.value; IN.value=''; TABS=null; sugClose();
    if(v.trim()){ var pv0 = v.trim().split(/\s+/)[0].toLowerCase();
      ev('prompt_submit', {text: v.trim().slice(0,300), verb: ALIAS[pv0]||pv0, len: v.trim().length,
        site: 'app', think_ms: KS.at ? Date.now()-KS.at : 0, strokes: KS.n, backspaces: KS.back,
        paste: KS.paste, from_history: HI < HIST.length ? 1 : 0}); }
    ksReset();
    if(v.trim()){ if(HIST[HIST.length-1] !== v.trim()) HIST.push(v.trim());
      if(HIST.length > 100) HIST.shift();
      try{ localStorage.setItem('oontz_hist', JSON.stringify(HIST)); }catch(err){} }
    HI = HIST.length; DRAFT = '';
    if(PENDING){ var ps=PENDING; PENDING=null;
      if(!v.trim()){ ev('ai_accept', {n: ps.length, kept: ps.filter(musical).length});
        snapshot('the ai'); ps.filter(musical).forEach(run); hint(); return; }
      ev('ai_reject', {n: ps.length}); line('  discarded','dim'); }
    run(v); hint(); }
  else if(e.key==='Tab'){                       // complete, then cycle
    e.preventDefault();
    var parts = IN.value.trim().split(/\s+/), head = (parts[0]||'').toLowerCase();
    if(parts.length > 1) return;
    if(!TABS){ TABS = {hits: verbs().filter(function(x){ return x.indexOf(head) === 0; }), i: -1, stem: head}; }
    if(!TABS.hits.length) return;
    TABS.i = (TABS.i + 1) % TABS.hits.length;
    IN.value = TABS.hits[TABS.i] + (TABS.hits.length === 1 ? ' ' : '');
    hint(); suggest();
  }
  else if(e.key==='ArrowUp'){ e.preventDefault();
    if(HI === HIST.length) DRAFT = IN.value;
    if(HI > 0){ HI--; IN.value = HIST[HI]; hint(); } }
  else if(e.key==='ArrowDown'){ e.preventDefault();
    if(HI < HIST.length){ HI++; IN.value = HI === HIST.length ? DRAFT : HIST[HI]; hint(); } }
  else if(e.key==='l' && e.ctrlKey){ e.preventDefault(); CMDS.clear(); }
  else if(e.key==='u' && e.ctrlKey){ e.preventDefault(); IN.value=''; hint(); }
  else if(e.key==='Escape'){ e.preventDefault(); IN.blur(); } });
IN.addEventListener('blur', function(){ sugClose(); PS1.innerHTML='<span class="w">perform</span> <span class="dim">: to type</span>'; });
IN.addEventListener('focus', function(){ PS1.innerHTML='oontz.sh&nbsp;&gt;'; });
var PS1 = document.getElementById('ps1');
/* Submit on pointerdown, not click. On a phone the soft keyboard is open and the
   input has focus: a tap on the button blurs it first, the keyboard collapses, the
   bar slides down out from under the finger, and the click lands on whatever moved
   into that spot - so the arrow did nothing. preventDefault keeps focus (and the
   keyboard) put, which is also what makes the next command typeable straight away. */
document.getElementById('gobtn').addEventListener('pointerdown', function(e){
  e.preventDefault();
  var v = IN.value; IN.value = ''; if(v.trim()) run(v); hint();
  try{ IN.focus({preventScroll: true}); }catch(err){ IN.focus(); }
});
/* smart paste: a .oontz source dropped into the prompt just works */
IN.addEventListener('paste', function(e){
  try{
    var txt = (e.clipboardData || window.clipboardData).getData('text') || '';
    if(!IN.value && txt.trim()[0] === '{' && txt.indexOf('"sections"') >= 0){
      e.preventDefault();
      IN.value = 'load ' + txt.trim();
      HINT.innerHTML = 'that looks like a song — <b>Enter</b> loads it';
    }
  }catch(err){}
});
var KONAMI = [];
addEventListener('keydown', function(e){
  KONAMI.push(e.key); if(KONAMI.length > 10) KONAMI.shift();
  if(KONAMI.join(',').toLowerCase().endsWith('arrowup,arrowup,arrowdown,arrowdown,arrowleft,arrowright,arrowleft,arrowright,b,a')){
    KONAMI = [];
    if(window.OONTZ_VIZ){ OONTZ_VIZ.theme('blacklight'); OONTZ_VIZ.mode('kaleido'); OONTZ_VIZ.flare(10000); }
    line(CP.egg_konami || 'you found the rave.','a2');
  }
});
var lastMsg = null;
addEventListener('keydown', function(e){
  if((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')){ e.preventDefault(); openPal(); return; }
  if(PAL.classList.contains('on')) return;
  if(document.activeElement===IN || e.ctrlKey || e.metaKey || e.altKey) return;
  if(scrollKey(e.key)){ e.preventDefault(); return; }
  if(e.key===':' || e.key==='Enter'){ e.preventDefault(); IN.focus(); return; }
  if(e.key==='?'){ e.preventDefault(); block((MODE==='deck'?DECK_KEYS:OZ.KEYS).map(function(kv){ return {c:kv[0], d:kv[1]}; })); return; }
  if(e.key==='R'){ e.preventDefault(); CMDS.rec && CMDS.rec([]); return; }
  if(e.key==='M' && MODE!=='deck'){ e.preventDefault(); CMDS.mode(['deck']); return; }
  var m = MODE==='deck' ? deckKey(e.key) : E.key(e.key, true);
  if(m===null) return;
  e.preventDefault();
  if(MUTATES[e.key] || OZ.PADS.indexOf(e.key) >= 0 || "zx".indexOf(e.key) >= 0) snapshot("a key");
  if(e.repeat && lastMsg && lastMsg.d.parentNode) lastMsg.d.innerHTML='<span class="dim">  '+esc(m)+'</span>';
  else lastMsg = {d: w('<span class="dim">  '+esc(m)+'</span>')};   // a held key updates one line, not a wall
  draw();
});
addEventListener('keyup', function(e){ if(document.activeElement!==IN){ var m=E.key(e.key,false); if(m) w('<span class="dim">  '+esc(m)+'</span>'); } });
/* The rack is not a readout, it is the instrument: click a step to toggle it,
   click a track name to focus it. Same edit path as the pads. */
RACK.addEventListener('click', function(e){
  if(PAINT.moved) return;                        /* a sweep already did the work */
  var st = e.target.closest('.st');
  if(st){ e.stopPropagation(); snapshot('a step');
    line('▸ ' + E.toggleStep(st.dataset.t, +st.dataset.i), 'dim'); draw(); return; }
  var tk = e.target.closest('.trk');
  /* a ghost lane's label names a track that is not playing yet, so it carries no
     data-t - without this it focused `undefined` and the pads edited nothing */
  if(tk && tk.dataset.t){ e.stopPropagation(); E.focus = tk.dataset.t; draw(); } });

/* Hold and sweep across cells to paint hits like a real step sequencer. The
   first cell's toggle decides the brush (drawing or erasing); every cell the
   pointer enters gets that state. Click still toggles a single step. */
var PAINT = {on: false, brush: false, moved: false, seen: {}};
RACK.addEventListener('pointerdown', function(e){
  var st = e.target.closest('.st');
  if(!st) return;
  PAINT.on = true; PAINT.moved = false; PAINT.seen = {};
  var tr = E.tracks[st.dataset.t];
  var ch = tr && (tr.pat || '')[OZ.patIndex(tr.pat || '', E.songbar, +st.dataset.i)];
  PAINT.brush = !(ch && ch !== '.' && ch !== '-');     /* toggle of the first cell */
  try{ RACK.setPointerCapture(e.pointerId); }catch(err){}
});
RACK.addEventListener('pointermove', function(e){
  if(!PAINT.on) return;
  var el = document.elementFromPoint(e.clientX, e.clientY);
  var st = el && el.closest && el.closest('.st');
  if(!st) return;
  var key = st.dataset.t + ':' + st.dataset.i;
  if(PAINT.seen[key]) return;
  PAINT.seen[key] = 1;
  if(!PAINT.moved){ PAINT.moved = true; snapshot('painting');
    var first = Object.keys(PAINT.seen)[0];
    E.setStep(st.dataset.t, +st.dataset.i, PAINT.brush); draw(); return; }
  E.setStep(st.dataset.t, +st.dataset.i, PAINT.brush); draw();
});
function paintEnd(){ if(PAINT.on){ PAINT.on = false;
  setTimeout(function(){ PAINT.moved = false; }, 50); } }
addEventListener('pointerup', paintEnd);
addEventListener('pointercancel', paintEnd);

/* The section map is a transport: click a bar, or drag across it to scrub. */
function hudSeek(e){
  var sq = e.target.closest && e.target.closest('.sq');
  if(!sq || !song) return;
  E.jump(+sq.dataset.bar); draw();
}
HUD.addEventListener('pointerdown', function(e){
  if(!song) return;
  hudSeek(e);
  /* capture throws NotFoundError when there is no live pointer (a synthetic event,
     or a pointer that ended before we got here) - dragging still works without it */
  try{ HUD.setPointerCapture && HUD.setPointerCapture(e.pointerId); }catch(err){}
  HUD.dataset.drag = '1';
});
HUD.addEventListener('pointermove', function(e){ if(HUD.dataset.drag) hudSeek(e); });

/* The stage folds away. A phone in landscape starts folded, because there the two
   panels cost more than they tell you; everywhere else it starts open. The choice
   sticks, so the instrument opens the way you left it. */
var TIGHT = document.getElementById('tight');
var SHORT = matchMedia('(max-height:520px) and (orientation:landscape)');
function setTight(on){
  document.body.classList.toggle('tight', !!on);
  TIGHT.textContent = on ? '+' : '−';
  TIGHT.setAttribute('aria-label', (on ? 'expand' : 'collapse') + ' the stage');
  try{ localStorage.setItem('oontz.tight', on ? '1' : '0'); }catch(e){}
}
(function(){
  var saved = null;
  try{ saved = localStorage.getItem('oontz.tight'); }catch(e){}
  setTight(saved === null ? SHORT.matches : saved === '1');
})();
TIGHT.addEventListener('pointerdown', function(e){
  e.preventDefault(); e.stopPropagation();          /* never let the seek handler see it */
  setTight(!document.body.classList.contains('tight'));
  draw();
});
/* pointerdown, not click: the deck bar sits over #stage, whose pointer handler seeks. */
document.getElementById('deckx').addEventListener('pointerdown', function(e){
  e.preventDefault(); e.stopPropagation(); CMDS.mode(['studio']);
});
document.getElementById('deckpal').addEventListener('pointerdown', function(e){
  e.preventDefault(); e.stopPropagation(); openPal();
});
addEventListener('pointerup', function(){ delete HUD.dataset.drag; });

OUT.addEventListener('scroll', function(){ TAIL.classList.toggle('on', !atBottom()); });
TAIL.addEventListener('click', function(e){ e.stopPropagation(); tail(); });
var COARSE = matchMedia('(pointer: coarse)').matches;
addEventListener('click', function(e){
  if(e.target.tagName==='A') return;
  if(e.target.id==='tail') return;
  var k = e.target.closest('.k');                 /* tap a listed command: it runs */
  if(k && OUT.contains(k)){ run(k.textContent.trim()); return; }
  if(COARSE && !e.target.closest('#bar')) return; /* a phone tap should not summon the keyboard */
  if(MODE === 'deck' && !e.target.closest('#bar')) return;   /* nor should a click re-deafen the deck keys */
  IN.focus(); });

/* the working song survives a refresh */
/* installable, and offline once visited — the engine never needed a server */
if('serviceWorker' in navigator && (location.protocol==='https:' || location.hostname==='localhost'))
  addEventListener('load', function(){ navigator.serviceWorker.register('sw.js').catch(function(){}); });

addEventListener('beforeunload', function(){ try{ if(song) localStorage.setItem('oontz_song', JSON.stringify(song)); }catch(e){} });

/* magic-link return: #token=... */
(function(){ var m=(location.hash||'').match(/token=([^&]+)/);
  if(m){ token=m[1]; localStorage.setItem('oontz_token',token);
    ev('signin_done', {});
    history.replaceState(null,'',location.pathname+location.search); } })();

(async function boot(){
  /* Read this BEFORE anything prints: a first-timer gets a track, not a menu.
     The menu is five verbs to read before you have heard a sound, and the funnel
     said 77% of arrivals never typed a character. Anyone who has been here keeps
     the screen they know. */
  var firstTime = false;
  try{ firstTime = !localStorage.getItem('oontz_seen'); }catch(e){}
  LOGO.forEach(function(l){ w('<span class="a2">'+esc(l)+'</span>','big'); });
  line();
  await type(CP.tagline||'techno from a command line.','b',13);
  line();
  (CP.boot||[]).forEach(function(t){ w('<span class="dim">  '+esc(t)+'</span>'); });
  line();
  if(!firstTime){
    (CP.menu||[]).forEach(function(kv){
      w('  <span class="k">'+esc(kv[0])+'</span><span class="dim">'+esc(kv[1])+'</span>'); });
    line();
  }
  if(token){ w('<span class="dim">  signed in. <span class="a">share</span> puts a track in the gallery.</span>');
    claimAll(); }
  /* A whole song carried in the fragment: no id, no server, nothing to look up. */
  var sm = (location.hash||'').match(/[#&]s=([A-Za-z0-9_-]+)/);
  if(sm){
    try{
      var sg = await OZ.unpackSong(sm[1]);
      loadSong(sg, 'someone sent you this whole song in a URL');
      ev('share_open', {kind:'url'});
      armPlay('');
      IN.focus(); return;
    }catch(e){ line('that link is damaged — ask for it again','w'); }
  }
  /* ?song= is the old shape and still arrives from anywhere it was pasted; #song=
     is what the share page links to, because ?song= now redirects. */
  var deep = new URLSearchParams(location.search).get('song') ||
             ((location.hash||'').match(/[#&]song=([A-Za-z0-9_-]+)/)||[])[1];
  if(deep){
    try{
      var dr = await fetch(API+'/songs/'+encodeURIComponent(deep));
      var dj = await dr.json();
      if(dj && dj.data){
        loadSong(dj.data, 'from the gallery · by ' + (dj.by || '?'));
        ev('share_open', {kind:'id', id: deep});
        armPlay(deep);
        IN.focus(); return;
      }
      /* a dead id used to fall through in silence, which reads as a broken site */
      line('that track is gone or private — '+esc(deep),'w');
    }catch(e){ line('could not reach the gallery for '+esc(deep),'w'); }
  }
  try{ var sz = localStorage.getItem('oontz_size');
    if(sz) document.documentElement.style.setProperty('--size', sz + 'px');
    if(localStorage.getItem('oontz_calm')) document.body.classList.add('calm');
  }catch(e){}
  /* A first-time visitor gets taught, once. Anyone who has been here keeps the
     screen they know. */
  try{
    if(firstTime){
      localStorage.setItem('oontz_seen', '1');
      TEACH = true;
      /* Arrive holding the track. loadSong puts every pattern in the rack, so the
         source IS on screen; armPlay makes hearing it one tap; and the only thing
         asked for is one character back, on a line they can already see. */
      var FIRST = 'kick x.x.x.x.x.x.x.x.';        // double time: unmistakable, and one edit
      loadSong(starterSong(), CP.first_hello, true);
      armPlay('', function(){
        line();
        w('<span class="a">  ' + esc(CP.first_move ? CP.first_move('kick', 'x.x.x.x.x.x.x.x.')
            : 'now change it: type ' + FIRST) + '</span>');
        IN.value = ''; IN.focus();
        FIRSTEDIT = true;
        ev('first_run', {step: 'played'});
      });
      ev('first_run', {step: 'armed'});
    }
  }catch(e){}
  try{ var saved = localStorage.getItem('oontz_song');
    if(saved){ song = JSON.parse(saved); E.loadSong(song); draw();
      w('<span class="dim">  restored <span class="b">'+esc(song.name)+'</span> from last time. <span class="a">play</span> to hear it.</span>'); }
  }catch(e){}
  IN.focus();
  OUT.scrollTop = 0;                             /* arrival = the title, not the tail */
})();
