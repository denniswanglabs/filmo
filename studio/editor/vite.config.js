import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { editorApi } from "./server-api.js";

// editor/ -> studio/
const STUDIO_DIR = path.resolve(import.meta.dirname, "..");
const SHARED = path.join(STUDIO_DIR, "node_modules"); // symlink to apple-style-demo/node_modules

// Resolve a shared dep to one concrete copy so the editor + the imported Timeline
// composition share ONE React instance (Player breaks with two Reacts).
const dep = (m) => path.join(SHARED, m);

export default defineConfig({
  root: import.meta.dirname,
  // Served UNDER /editor/ when folded into the dashboard server (serve.py rewrites
  // /editor/* -> studio/editor/dist/*). The built index.html therefore references
  // its assets as /editor/assets/..., which the dashboard maps back to dist/.
  base: "/editor/",
  // Serve studio/public/ at the dev-server root so Remotion's staticFile() paths
  // (audio, screenshots, walkthrough mp4s baked into props.json) resolve live in
  // the Player preview, exactly as they would in `remotion studio`.
  // copyPublicDir:false keeps the ~600MB of run screenshots OUT of the production
  // bundle — in the folded build the Player resolves those assets against the
  // dashboard-served /studio/public via window.remotion_staticBase (main.jsx,PROD).
  publicDir: path.join(STUDIO_DIR, "public"),
  build: {
    outDir: "dist",
    emptyOutDir: true,
    copyPublicDir: false,
  },
  server: {
    port: 3040,
    host: "127.0.0.1",
    fs: {
      // Allow importing the composition + its archetypes from ../src and the
      // shared node_modules outside the editor root.
      allow: [STUDIO_DIR, SHARED, path.resolve(STUDIO_DIR, "..")],
    },
  },
  resolve: {
    // One copy of each shared dep (the studio's symlinked install).
    alias: {
      react: dep("react"),
      "react-dom": dep("react-dom"),
      "react/jsx-runtime": path.join(dep("react"), "jsx-runtime.js"),
      "react/jsx-dev-runtime": path.join(dep("react"), "jsx-dev-runtime.js"),
      remotion: dep("remotion"),
      "@remotion/player": dep("@remotion/player"),
    },
    dedupe: ["react", "react-dom", "remotion", "@remotion/player"],
  },
  optimizeDeps: {
    // Pre-bundle the heavy shared deps from outside root.
    include: ["react", "react-dom", "react-dom/client", "remotion", "@remotion/player"],
  },
  plugins: [react(), editorApi()],
});
