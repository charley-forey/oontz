/* Used by `python -m oontz.qa`: reads [[curve, minutes, bpm, dropLo, dropHi], ...]
 * on stdin and prints the browser composer's plan for each, so the Python and JS
 * arrangers can be held to the same answer. */
"use strict";
require("./theory.js");
require("./compose.js");
var CO = globalThis.OONTZ_COMPOSE, inp = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", function(d){ inp += d; });
process.stdin.on("end", function(){
  var out = JSON.parse(inp).map(function(c){
    return CO.arrange(c[1], c[0], c[2], [c[3], c[4]]).map(function(p){ return [p.role, p.bars]; });
  });
  process.stdout.write(JSON.stringify(out));
});
