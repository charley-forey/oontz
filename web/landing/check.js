/* The landing gate. `node web/landing/check.js`. No deps.
 * Railway builds this service from web/landing alone, so the engine the page
 * loads is a copy of web/app/oontz.js. A copy drifts; this fails the moment it does. */
"use strict";
var fs = require("fs"), path = require("path"), A = require("assert");
var here = __dirname, app = path.join(here, "..", "app"), eng = path.join(here, "engine");

var files = fs.readdirSync(eng);
A.ok(files.length, "engine/ is empty");
var norm = function(p2){ return fs.readFileSync(p2, "utf8").replace(/\r\n/g, "\n"); };
files.forEach(function(f){
  A.strictEqual(norm(path.join(eng, f)), norm(path.join(app, f)),
    "web/landing/engine/" + f + " differs from web/app/" + f + " — run: cp web/app/" + f + " web/landing/engine/");
});

var html = fs.readFileSync(path.join(here, "index.html"), "utf8");
A.ok(/(?:const|var) API = "https?:\/\/[^"]+"/.test(html), "server.py reads the API base from index.html's `API = \"...\"` line");
/* Every asset, not just the engine. This page is served at /t/<id> and /p/<id> as
   well as /, so a relative src resolves against /t/ and 404s. That is not
   hypothetical: `src="copy.js"` shipped and every share page loaded with no copy,
   while the single assertion below happily passed because it only ever looked at
   one file. Check them all, and the class cannot come back. */
var rel = (html.match(/(?:src|href)="(?!https?:|\/\/|\/|#|data:|mailto:)[^"]*/g) || [])
  .filter(function(m){ return m.indexOf("${") < 0; });   /* JS template literals, not markup */
A.ok(!rel.length, "relative asset path(s) in landing/index.html, which 404 at /t/<id>: " + rel.join(", "));
A.ok(html.indexOf('src="/engine/oontz.js"') >= 0, "index.html must load /engine/oontz.js by absolute path (it is served at /t/<id> too)");
A.ok(html.indexOf("sugPick") >= 0 && html.indexOf("oontz_music_hist") >= 0 && html.indexOf("gobtn") >= 0,
  "the landing prompt has the dropdown, history, and the run chip");

var r = require("child_process").spawnSync("python", [path.join(here, "server.py"), "check"], {encoding: "utf8"});
A.strictEqual(r.status, 0, "server.py check failed:\n" + r.stdout + r.stderr);

console.log("landing checks pass  ·  " + files.join(" ") + " identical to web/app · " + r.stdout.trim());
