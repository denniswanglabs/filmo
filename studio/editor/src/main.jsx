import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";

// FOLDED-BUILD asset base. In the production build the editor is served by the
// dashboard at /editor/, NOT from Vite's publicDir root, so Remotion's
// staticFile("shot-x.png") must point at the dashboard-served public dir. The
// dashboard server (serve.py) exposes the whole project root statically, so
// studio/public/ lives at /studio/public. Setting window.remotion_staticBase
// makes staticFile() resolve to /studio/public/shot-x.png (served, Range-capable).
// In `vite` dev (import.meta.env.DEV) the dev server already serves publicDir at
// the origin root, so we leave the base unset and staticFile() returns /shot-x.png.
if (import.meta.env.PROD) {
  window.remotion_staticBase = "/studio/public";
}

createRoot(document.getElementById("root")).render(<App />);
