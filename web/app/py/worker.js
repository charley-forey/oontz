/* The Python side of the spike: Pyodide + numpy + the real oontz package, in a
 * worker so a slow bar can never glitch the page. The main thread asks; this
 * answers. Every render is timed — the number this spike exists to produce. */
importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js");

let web = null;
const times = [];

async function boot() {
  const t0 = performance.now();
  const py = await loadPyodide();
  const t1 = performance.now();
  await py.loadPackage("numpy");
  const t2 = performance.now();
  const zip = await (await fetch("oontz.zip")).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/app" });
  py.runPython("import sys; sys.path.insert(0, '/app')");
  web = py.pyimport("oontz.web");
  const hello = web.boot();
  const t3 = performance.now();
  const ms = (a, b) => Math.round(b - a);
  console.log("[oontz-py] pyodide " + ms(t0, t1) + "ms · numpy " + ms(t1, t2) + "ms · oontz " + ms(t2, t3) + "ms");
  return { hello: hello, pyodide: ms(t0, t1), numpy: ms(t1, t2), oontz: ms(t2, t3) };
}

const booted = boot();

self.onmessage = async (e) => {
  const m = e.data;
  await booted;
  try {
    if (m.t === "boot") {
      postMessage({ t: "boot", info: await booted });
    } else if (m.t === "do") {
      postMessage({ t: "echo", text: web.do(m.cmd) });
    } else if (m.t === "key") {
      postMessage({ t: "key", echo: web.key(m.ch) });
    } else if (m.t === "page") {
      postMessage({ t: "page", text: web.page(m.cols, m.rows, m.step) });
    } else if (m.t === "bar") {
      const t0 = performance.now();
      const bytes = web.render_bar().toJs();          // Uint8Array copy of the bar
      const ms = performance.now() - t0;
      times.push(ms);
      console.log("[oontz-py] render " + ms.toFixed(0) + "ms");
      if (times.length === 8) {
        const s = times.slice().sort((a, b) => a - b);
        console.log("[oontz-py] 8 bars · min " + s[0].toFixed(0) + "ms · median " +
                    s[4].toFixed(0) + "ms · max " + s[7].toFixed(0) + "ms");
      }
      const buf = new Float32Array(bytes.buffer, bytes.byteOffset, bytes.length / 4).slice();
      postMessage({ t: "bar", buf: buf, ms: ms }, [buf.buffer]);
    }
  } catch (err) {
    console.log("[oontz-py] error " + err);
    postMessage({ t: "error", text: String(err) });
  }
};
