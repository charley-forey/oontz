/* Accounts: what signing in actually buys you.
 *
 * Loaded AFTER the page script, so the globals index.html defines are real here:
 * API, CMDS, token, line, w, esc, song, loadSong. It registers its commands
 * straight into CMDS — index.html stays almost untouched.
 *
 * The key (`key sk-ant-…`) lives in THIS browser's localStorage and rides each
 * `ask` request as a header. The server never stores it; there is nothing to leak.
 */
(function () {
"use strict";

function need() {
  if (!token) { line("you need an account for that. `login you@example.com`", "w"); return true; }
}

async function req(method, path, body) {
  var h = { authorization: "Bearer " + token };
  if (body !== undefined) h["content-type"] = "application/json";
  var r = await fetch(API + path, { method: method, headers: h,
    body: body === undefined ? undefined : JSON.stringify(body) });
  var j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((j && (j.error || j.detail)) || ("HTTP " + r.status));
  return j;
}

function ago(t) {
  var d = (Date.now() / 1000 - t) / 86400;
  return d < 1 ? "today" : Math.round(d) + "d ago";
}

/* -- key ------------------------------------------------------------------ */
CMDS.key = function (a) {
  var v = (a[0] || "").trim();
  if (!v) { var k = localStorage.getItem("oontz_key");
    return line(k ? "▸ a key is linked (" + k.slice(0, 10) + "…). `key off` unlinks it."
                  : "▸ no key linked. `key sk-ant-…` makes `ask` use yours. it never leaves this browser except to answer you.", "dim"); }
  if (v === "off") { localStorage.removeItem("oontz_key"); return line("▸ key unlinked", "dim"); }
  if (v.indexOf("sk-ant-") !== 0)
    return line("Anthropic keys start with sk-ant-. that one doesn't, so it isn't one.", "w");
  localStorage.setItem("oontz_key", v);
  line("▸ key linked. `ask` runs on your key now — stored in this browser only.", "ok");
};

/* -- handle --------------------------------------------------------------- */
CMDS.handle = async function (a) { if (need()) return;
  var h = (a[0] || "").trim().toLowerCase();
  if (!h) return line("handle <one_word> · your name on the gallery", "w");
  try { var j = await req("PATCH", "/me", { handle: h });
    line("▸ you are " + esc(j.handle || h) + " now", "ok"); }
  catch (e) { line("▸ " + esc(e.message), "w"); }
};

/* -- takes: private server-side snapshots, a few KB of text --------------- */
CMDS.take = async function (a) { if (need()) return;
  var sub = a[0];
  try {
    if (sub === "load" && a[1]) {
      var t = await req("GET", "/takes/" + a[1]);
      loadSong(JSON.parse(t.data), "take " + t.name);
      return;
    }
    if (sub === "rm" && a[1]) { await req("DELETE", "/takes/" + a[1]);
      return line("▸ gone", "dim"); }
    if (!song) return line(CP.err_nosong, "w");
    var name = (a.join(" ") || song.name || "take").trim();
    var j = await req("POST", "/takes", { name: name, data: JSON.stringify(song) });
    line("▸ kept as a take (" + j.id + "). it re-renders identically anywhere — a take is text, not audio.", "ok");
  } catch (e) { line("▸ " + esc(e.message), "w"); }
};
CMDS.takes = async function () { if (need()) return;
  try { var j = await req("GET", "/takes");
    if (!j.takes.length) return line("no takes yet. `take <name>` keeps the current song.", "dim");
    line();
    j.takes.forEach(function (t) {
      w("  <span class=\"a\">" + esc(t.id) + "</span> <span class=\"b\">" + esc(t.name) + "</span>" +
        " <span class=\"dim\">" + t.bytes + "b · " + ago(t.created) + " · take load " + esc(t.id) + "</span>"); });
    line();
  } catch (e) { line("▸ " + esc(e.message), "w"); }
};

/* -- playlists ------------------------------------------------------------ */
async function items(pid) { return (await req("GET", "/playlists/" + pid)).songs.map(function (s) { return s.id; }); }

CMDS.playlist = async function (a) { if (need()) return;
  var sub = (a[0] || "").toLowerCase();
  try {
    if (sub === "new") { var j = await req("POST", "/playlists", { title: a.slice(1).join(" ") || "untitled" });
      return line("▸ playlist " + j.id + " · `playlist add " + j.id + " <song id>` fills it", "ok"); }
    if (sub === "add" && a[1] && a[2]) { var ids = await items(a[1]); ids.push(a[2]);
      await req("PUT", "/playlists/" + a[1] + "/items", { song_ids: ids });
      return line("▸ " + ids.length + " tracks", "ok"); }
    if (sub === "rm" && a[1] && a[2]) { var ids2 = (await items(a[1])).filter(function (s) { return s !== a[2]; });
      await req("PUT", "/playlists/" + a[1] + "/items", { song_ids: ids2 });
      return line("▸ " + ids2.length + " tracks", "ok"); }
    if (sub === "public" && a[1]) { var p = await req("PATCH", "/playlists/" + a[1], { public: true });
      line("▸ public. anyone with this can hear it:", "ok");
      return w("  <a href=\"" + esc(p.url) + "\">" + esc(p.url) + "</a>"); }
    if (sub === "private" && a[1]) { await req("PATCH", "/playlists/" + a[1], { public: false });
      return line("▸ private again", "dim"); }
    if (sub === "del" && a[1]) { await req("DELETE", "/playlists/" + a[1]);
      return line("▸ gone", "dim"); }
    if (sub && !a[1]) { // playlist <id> — show it
      var pl = await req("GET", "/playlists/" + sub);
      line(); w("  <span class=\"b\">" + esc(pl.title) + "</span> <span class=\"dim\">" +
        (pl.public ? "public" : "private") + " · " + pl.songs.length + " tracks</span>");
      pl.songs.forEach(function (s, i) {
        w("  <span class=\"dim\">" + (i + 1) + ".</span> <span class=\"a\">" + esc(s.id) + "</span> " +
          esc(s.title) + " <span class=\"dim\">" + Math.round(s.bpm || 0) + "bpm · " + esc(s.kkey || "?") + "</span>"); });
      return line();
    }
    // bare `playlist` / `playlists`: list mine
    var mine = await req("GET", "/playlists");
    if (!mine.playlists.length) return line("no playlists. `playlist new <title>` starts one.", "dim");
    line();
    mine.playlists.forEach(function (p2) {
      w("  <span class=\"a\">" + esc(p2.id) + "</span> <span class=\"b\">" + esc(p2.title) + "</span>" +
        " <span class=\"dim\">" + p2.n + " tracks · " + (p2.public ? "public" : "private") + "</span>"); });
    line();
  } catch (e) { line("▸ " + esc(e.message), "w"); }
};
CMDS.playlists = CMDS.playlist;

window.OONTZ_ACCOUNT = { req: req };
})();
