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
A.ok(html.indexOf('src="/engine/oontz.js"') >= 0, "index.html must load /engine/oontz.js by absolute path (it is served at /t/<id> too)");

var r = require("child_process").spawnSync("python", [path.join(here, "server.py"), "check"], {encoding: "utf8"});
A.strictEqual(r.status, 0, "server.py check failed:\n" + r.stdout + r.stderr);

console.log("landing checks pass  ·  " + files.join(" ") + " identical to web/app · " + r.stdout.trim());
