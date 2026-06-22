// Dev-server API middleware for the experimental video editor.
//
// Endpoints (all under the same origin as the Vite dev server). They are
// namespaced under /api/editor/* so the SAME paths can be served by the dashboard
// server (serve.py) when the editor is folded into Walk Studio on :3030 — this dev
// middleware and serve.py implement an identical contract:
//   GET  /api/editor/runs            -> { runs: [{id, hasProps, hasFinal}] }
//   GET  /api/editor/props?id=<runId>-> the run's CLEAN props.json by default.
//                                       pass &edited=1 to explicitly load props.edited.json
//                                       (response includes hasEdited so the UI can offer it).
//   POST /api/editor/save  {id,props}-> writes runs/<id>/props.edited.json, returns the render command
//   POST /api/editor/render {id}     -> runs the existing remotion render into runs/<id>/edited.mp4,
//                                       streams status lines, finishes with a final JSON line.
//
// This is ADDITIVE: it shells out to the SAME `remotion render` invocation the
// production build_runner.py uses (build_runner.py:293-295). It does NOT import or
// modify any python. It only reads/writes files under runs/ and spawns remotion.
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

// editor/  ->  studio/  ->  repo root
const STUDIO_DIR = path.resolve(import.meta.dirname, "..");
const REPO_ROOT = path.resolve(STUDIO_DIR, "..");
const RUNS_DIR = path.join(REPO_ROOT, "runs");

const readJson = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const send = (res, code, obj) => {
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(obj));
};
const bodyJson = (req) =>
  new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });

// List every run dir that has a props.json. Newest props first (mtime desc) so a
// real, recently-generated run is at the top of the dropdown.
function listRuns() {
  if (!fs.existsSync(RUNS_DIR)) return [];
  const out = [];
  for (const name of fs.readdirSync(RUNS_DIR)) {
    const dir = path.join(RUNS_DIR, name);
    let st;
    try {
      st = fs.statSync(dir);
    } catch {
      continue;
    }
    if (!st.isDirectory()) continue;
    const props = path.join(dir, "props.json");
    if (!fs.existsSync(props)) continue;
    const edited = path.join(dir, "props.edited.json");
    let mtime = 0;
    try {
      mtime = fs.statSync(props).mtimeMs;
    } catch {}
    out.push({
      id: name,
      hasProps: true,
      hasEdited: fs.existsSync(edited),
      hasFinal: fs.existsSync(path.join(dir, "final.mp4")),
      hasEditedMp4: fs.existsSync(path.join(dir, "edited.mp4")),
      mtime,
    });
  }
  out.sort((a, b) => b.mtime - a.mtime);
  return out;
}

// The render command, mirroring build_runner.py:293-295 exactly (cwd=studio).
function renderCmd(absProps, absOut) {
  return [
    "remotion",
    "render",
    "src/index.ts",
    "Timeline",
    absOut,
    "--codec=h264",
    "--concurrency=8",
    `--props=${absProps}`,
  ];
}

export function editorApi() {
  return {
    name: "hermes-editor-api",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url, "http://localhost");
        const p = url.pathname;
        if (!p.startsWith("/api/")) return next();

        try {
          if (p === "/api/editor/runs" && req.method === "GET") {
            return send(res, 200, { runs: listRuns() });
          }

          if (p === "/api/editor/props" && req.method === "GET") {
            const id = url.searchParams.get("id");
            if (!id) return send(res, 400, { error: "missing id" });
            const dir = path.join(RUNS_DIR, id);
            const base = path.join(dir, "props.json");
            const edited = path.join(dir, "props.edited.json");
            const hasEdited = fs.existsSync(edited);
            // DEFAULT: load the CLEAN, canonical props.json. Only return the
            // edited variant when the caller explicitly opts in (&edited=1) AND
            // it exists — so a stale verification edit never silently shadows the
            // real generated props.
            const wantEdited = ["1", "true", "yes"].includes(
              (url.searchParams.get("edited") || "").toLowerCase()
            );
            const which = wantEdited && hasEdited ? edited : base;
            if (!fs.existsSync(which)) return send(res, 404, { error: "no props for " + id });
            return send(res, 200, {
              id,
              source: path.basename(which),
              hasEdited,
              props: readJson(which),
            });
          }

          if (p === "/api/editor/save" && req.method === "POST") {
            const { id, props } = await bodyJson(req);
            if (!id || !props) return send(res, 400, { error: "missing id or props" });
            const dir = path.join(RUNS_DIR, id);
            if (!fs.existsSync(dir)) return send(res, 404, { error: "no run " + id });
            const editedPath = path.join(dir, "props.edited.json");
            fs.writeFileSync(editedPath, JSON.stringify(props, null, 2));
            const absProps = path.resolve(editedPath);
            const absOut = path.resolve(path.join(dir, "edited.mp4"));
            return send(res, 200, {
              ok: true,
              wrote: editedPath,
              renderCommand: `cd ${STUDIO_DIR} && ${renderCmd(absProps, absOut).join(" ")}`,
            });
          }

          if (p === "/api/editor/render" && req.method === "POST") {
            const { id } = await bodyJson(req);
            if (!id) return send(res, 400, { error: "missing id" });
            const dir = path.join(RUNS_DIR, id);
            const editedPath = path.join(dir, "props.edited.json");
            if (!fs.existsSync(editedPath))
              return send(res, 400, { error: "no props.edited.json — Save first" });
            const absProps = path.resolve(editedPath);
            const absOut = path.resolve(path.join(dir, "edited.mp4"));
            const cmd = renderCmd(absProps, absOut);

            // Stream plain-text status lines back as the render runs. Mirrors
            // build_runner.py: cwd=studio, PATH prefixed with node_modules/.bin.
            res.statusCode = 200;
            res.setHeader("Content-Type", "text/plain; charset=utf-8");
            res.setHeader("Cache-Control", "no-cache");
            res.write(`[editor] rendering ${id} -> ${absOut}\n`);
            res.write(`[editor] cmd: ${cmd.join(" ")}\n`);

            const env = {
              ...process.env,
              PATH: path.join(STUDIO_DIR, "node_modules", ".bin") + path.delimiter + (process.env.PATH || ""),
            };
            const child = spawn(cmd[0], cmd.slice(1), { cwd: STUDIO_DIR, env });
            const onChunk = (buf) => {
              try {
                res.write(buf.toString());
              } catch {}
            };
            child.stdout.on("data", onChunk);
            child.stderr.on("data", onChunk);
            child.on("error", (e) => {
              try {
                res.write(`\n[editor] spawn error: ${e.message}\n`);
                res.end(`__DONE__ ${JSON.stringify({ ok: false, error: e.message })}\n`);
              } catch {}
            });
            child.on("close", (code) => {
              const ok = code === 0 && fs.existsSync(absOut);
              try {
                res.end(
                  `\n[editor] exit=${code} exists=${fs.existsSync(absOut)}\n` +
                    `__DONE__ ${JSON.stringify({ ok, out: ok ? absOut : null, code })}\n`
                );
              } catch {}
            });
            return;
          }

          return send(res, 404, { error: "unknown endpoint " + p });
        } catch (e) {
          return send(res, 500, { error: String(e && e.message ? e.message : e) });
        }
      });
    },
  };
}
