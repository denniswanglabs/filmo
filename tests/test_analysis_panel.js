// $0 DOM-string test for analysisPanel(). Loads app.js's analysisPanel via a tiny
// shim (the function is pure: ledger in -> HTML string out). Run: node tests/test_analysis_panel.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const src = fs.readFileSync(path.join(__dirname, "..", "dashboard", "app.js"), "utf8");
// Pull just the analysisPanel function body by evaluating app.js in a sandbox that
// stubs the browser globals it references at module load.
const sandbox = { window: {}, document: { getElementById: () => null,
  querySelectorAll: () => [], addEventListener: () => {} },
  console, setInterval: () => 0, clearInterval: () => {}, fetch: () => {} };
vm.createContext(sandbox);
try { vm.runInContext(src, sandbox); } catch (e) { /* top-level init may noop */ }

const fn = sandbox.analysisPanel;
if (typeof fn !== "function") { console.error("FAIL: analysisPanel is not defined"); process.exit(1); }

const led = { conversion_read: {
  url: "https://acme.com", verdict: "feature-led hero, zero proof, weak CTA",
  dimensions: [
    { key: "promise", score: 3, finding: "", evidence: "", fix: "" },
    { key: "outcome", score: 2, finding: "", evidence: "", fix: "" },
    { key: "proof", score: 1, finding: "no numbers", evidence: "", fix: "add proof" },
    { key: "show", score: 2, finding: "", evidence: "", fix: "" },
    { key: "specificity", score: 2, finding: "", evidence: "", fix: "" },
    { key: "cta", score: 2, finding: "", evidence: "", fix: "" } ],
  priority_fixes: [{ rank: 1, fix: "Add a proof beat", maps_to: "proof" }],
  headline_fix: "Ship 10x faster.", degraded: false } };

const html = fn(led);
const need = ["Conversion Read", "promise", "outcome", "proof", "show",
  "specificity", "cta", "Add a proof beat", "feature-led hero"];
let ok = true;
for (const s of need) { if (!html.includes(s)) { console.error("FAIL: missing " + s); ok = false; } }
// empty read -> empty string (panel hidden when no Read)
if (fn({}) !== "") { console.error("FAIL: panel should be empty without a Read"); ok = false; }
console.log(ok ? "PASS: analysisPanel renders all 6 dimensions + fixes" : "FAILED");
process.exit(ok ? 0 : 1);
