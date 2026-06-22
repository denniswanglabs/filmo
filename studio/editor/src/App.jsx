// In-browser iMovie-style timeline video editor for Walk Studio, with Hera's
// premium design language.
//
//   ┌──────────────────────────────────────────────────────────────┐
//   │  ◇ floating glass TOP BAR — wordmark · run picker · Save/Export│
//   ├───────────────────────────────────────────┬──────────────────┤
//   │  PREVIEW STAGE (the hero)                  │   INSPECTOR       │
//   │   format/duration pills                    │   selected scene  │
//   │   ┌────────── @remotion/player ──────────┐ │   text / geometry │
//   │   │           framed dark canvas         │ │   theme / timing  │
//   │   └──────────────────────────────────────┘ │                   │
//   │   ◀ ▶  play/pause + scrub (glass pill)      │                   │
//   ├───────────────────────────────────────────┤                   │
//   │  BOTTOM TIMELINE — scene clips ∝ duration   │                   │
//   │  ruler · clip blocks · live playhead        │                   │
//   └───────────────────────────────────────────┴──────────────────┘
//
// Selecting a clip drives the inspector AND seeks the Player. Every control
// mutates `props` state and the Player re-renders instantly (live edit). Save
// writes props.edited.json; Export re-renders edited.mp4 — both unchanged.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Player } from "@remotion/player";
import { Timeline } from "../../src/timeline/Timeline";
import { EditPanel } from "./EditPanel.jsx";
import { TimelineTrack } from "./TimelineTrack.jsx";
import { PlayerControls } from "./PlayerControls.jsx";
import { SelectionOverlay, usePreviewSelection } from "./SelectionOverlay.jsx";
import { InlineEditor } from "./InlineEditor.jsx";
import { useShortcuts } from "./useShortcuts.js";
import { TEXT_KEY_FOR_FIELD } from "./EditPanel.jsx";
import { Button, Pill, Icon } from "./ui.jsx";

const DEFAULT_RUN = "r5-stripe";

// Wordmark lockup: the SAME mark the dashboard uses (a light coral-tinted
// film-frame tile + coral W-glyph — NOT a dark tile) + "Walk Studio" + an
// "Editor" tag, no emoji. Kept byte-for-byte identical to dashboard/index.html's
// .bar-logo glyph so the two surfaces read as one product.
function Wordmark({ onClick }) {
  return (
    <div
      onClick={onClick}
      title={onClick ? "Back to Walk Studio" : undefined}
      style={{ display: "flex", alignItems: "center", gap: 11, cursor: onClick ? "pointer" : "default" }}
    >
      {/* The dashboard's exact mark (dashboard/index.html .bar-logo), scaled to
          30px via the 84-unit viewBox: a light coral-tinted film-frame tile with
          sprocket holes + the coral W. NOT the old dark --stage tile. */}
      <svg width="30" height="30" viewBox="0 0 84 84" aria-hidden="true" style={{ display: "block" }}>
        <rect x="0" y="0" width="84" height="84" rx="22" fill="#FFF1EE" />
        <rect x="1" y="1" width="82" height="82" rx="21" fill="none" stroke="#F0BFB3" strokeWidth="1.5" />
        <g fill="#EAB6A9">
          <rect x="10" y="17" width="5.5" height="8" rx="2.75" />
          <rect x="10" y="38" width="5.5" height="8" rx="2.75" />
          <rect x="10" y="59" width="5.5" height="8" rx="2.75" />
          <rect x="68.5" y="17" width="5.5" height="8" rx="2.75" />
          <rect x="68.5" y="38" width="5.5" height="8" rx="2.75" />
          <rect x="68.5" y="59" width="5.5" height="8" rx="2.75" />
        </g>
        <path d="M32 20 L32 64 L42.8 53.4 L50.4 68.2 L57.6 64.6 L50 49.8 L62.8 49.8 Z" fill="#D6351C" stroke="#D6351C" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
      <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
        <span style={{ fontWeight: 800, fontSize: 15.5, letterSpacing: -0.3, color: "var(--text)" }}>
          Walk <span style={{ color: "var(--accent)" }}>Studio</span>
        </span>
        <span
          style={{
            fontSize: 9.5,
            fontWeight: 700,
            letterSpacing: 1.5,
            textTransform: "uppercase",
            color: "var(--muted)",
            border: "1px solid var(--line-2)",
            borderRadius: 6,
            padding: "2px 7px",
          }}
        >
          Editor
        </span>
      </div>
    </div>
  );
}

export function App() {
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState(null);
  const [props, setProps] = useState(null);
  const [source, setSource] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const [status, setStatus] = useState("");
  const [statusKind, setStatusKind] = useState("idle"); // idle | working | ok | error
  const [log, setLog] = useState("");
  const [showLog, setShowLog] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [frame, setFrame] = useState(0); // live playhead frame (drives timeline + controls)
  // Click-to-select state: which composition element is selected (drives the coral
  // box + inspector focus), plus a transient hover target for the faint cue.
  const [selected, setSelected] = useState(null); // { sceneId, field } | null
  const [hoverSel, setHoverSel] = useState(null); // { sceneId, field } | null
  const [focusField, setFocusField] = useState(null); // { field, nonce } -> inspector
  // Inline text editing in the preview: { sceneId, field, key } when an editable
  // text element is being edited in place (double-click / Enter), else null.
  const [editing, setEditing] = useState(null);
  const playerRef = useRef(null);
  const stageRef = useRef(null); // the Player's container (delegated click target)
  // Always-current props mirror so the click/seek handlers never read a stale
  // closure (the delegated preview handler is attached once and lives long).
  const propsRef = useRef(null);
  useEffect(() => {
    propsRef.current = props;
  }, [props]);
  // Expose the player ref for deterministic seeking (dev/verify convenience).
  useEffect(() => {
    window.__player = playerRef;
  }, []);

  const note = (msg, kind = "idle") => {
    setStatus(msg);
    setStatusKind(kind);
  };

  // Load the run list, then default-load a real run so a video shows immediately.
  // When the dashboard opens the editor it deep-links the run via ?run=<id>
  // (e.g. /editor/?run=fin-stripe from a delivered build's "Edit video" button) —
  // that takes precedence over DEFAULT_RUN so the user lands on the video they
  // just generated.
  useEffect(() => {
    fetch("/api/editor/runs")
      .then((r) => r.json())
      .then((d) => {
        const list = d.runs || [];
        setRuns(list);
        const deepLink = new URLSearchParams(window.location.search).get("run");
        const pick =
          (deepLink && list.find((r) => r.id === deepLink)) ||
          list.find((r) => r.id === DEFAULT_RUN) ||
          list[0];
        if (pick) loadRun(pick.id);
      })
      .catch((e) => note("Could not list runs: " + e.message, "error"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load a run's props. DEFAULT loads the CLEAN, canonical props.json. Pass
  // { edited: true } to explicitly load the saved props.edited.json instead —
  // the default must always be the original so a stale edit never shadows it.
  const loadRun = useCallback((id, { edited = false } = {}) => {
    note("Loading " + id + (edited ? " (edited)" : "") + " …", "working");
    fetch("/api/editor/props?id=" + encodeURIComponent(id) + (edited ? "&edited=1" : ""))
      .then((r) => r.json())
      .then((d) => {
        if (d.error) return note("Load error: " + d.error, "error");
        setRunId(d.id);
        setProps(d.props);
        setSource(d.source);
        setActiveIdx(0);
        setFrame(0);
        setDirty(false);
        setSelected(null);
        setHoverSel(null);
        note("Loaded " + d.id, "ok");
      })
      .catch((e) => note("Load error: " + e.message, "error"));
  }, []);

  // File input fallback: read a local props.json off disk.
  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        setProps(JSON.parse(reader.result));
        setRunId(null);
        setSource(f.name);
        setActiveIdx(0);
        setFrame(0);
        setDirty(false);
        setSelected(null);
        setHoverSel(null);
        note("Loaded local file — Save/render need a run id", "ok");
      } catch (err) {
        note("Bad JSON: " + err.message, "error");
      }
    };
    reader.readAsText(f);
  };

  // Apply an immutable mutator and bump props identity so the Player re-renders.
  const update = useCallback((mutator) => {
    setProps((p) => (p ? mutator(p) : p));
    setDirty(true);
  }, []);

  // Total frames + fps (derived from props) — defined early because the keyboard
  // shortcut hook + inline-edit/drag handlers below need them.
  const dur = Math.max(1, props?.total_frames || 1);
  const fps = props?.fps || 30;

  // Live value the inline editor reads/writes: scene.data[key] of the scene being
  // edited (resolved by id so it matches even if activeIdx lags a frame).
  const editIdx = editing ? (props?.scenes || []).findIndex((s) => s.id === editing.sceneId) : -1;
  const editValue = editIdx >= 0 ? props?.scenes?.[editIdx]?.data?.[editing.key] ?? "" : "";

  // Live: write the inline-edited text straight into props (mirrors EditPanel's
  // setSceneData but scoped to the editing scene + key).
  const setEditValue = useCallback(
    (v) => {
      if (editIdx < 0 || !editing) return;
      update((p) => {
        const next = structuredClone(p);
        next.scenes[editIdx].data = { ...next.scenes[editIdx].data, [editing.key]: v };
        return next;
      });
    },
    [editIdx, editing, update]
  );

  // scene.id -> timeline index, so an element's data-scene-id resolves to a scene.
  const idxById = useMemo(() => {
    const m = {};
    (props?.scenes || []).forEach((s, i) => {
      if (s.id != null) m[s.id] = i;
    });
    return m;
  }, [props]);

  // Select a scene by index: drive the inspector AND seek the Player to its
  // in_frame. `clearElement` (default true) drops any element-level selection so
  // a timeline-clip click doesn't leave a coral box on a now-unrelated element.
  const selectScene = useCallback(
    (i, { clearElement = true } = {}) => {
      setActiveIdx(i);
      if (clearElement) setSelected(null);
      const s = props?.scenes?.[i];
      if (s && playerRef.current) {
        const f = s.in_frame || 0;
        playerRef.current.pause();
        playerRef.current.seekTo(f);
        setFrame(f);
      }
    },
    [props]
  );

  // Select a composition ELEMENT clicked in the live preview. Resolves the scene
  // (so the inspector + timeline clip agree), draws the coral box, nudges the
  // inspector to the matching field, and seeks to a frame where the element is
  // actually visible (its reveal has fired) so the box hugs real content — NOT to
  // the bare in_frame where hero reveals are still at opacity 0.
  const selectElement = useCallback(({ sceneId, field }) => {
    const cur = propsRef.current;
    const scenes = cur?.scenes || [];
    const i = scenes.findIndex((s) => s.id === sceneId);
    if (i < 0) return;
    setActiveIdx(i);
    setSelected({ sceneId, field });
    setFocusField({ field, nonce: Date.now() });
    const s = scenes[i];
    if (s && playerRef.current) {
      const inF = s.in_frame || 0;
      const outF = s.out_frame || inF + 1;
      // Land ~45% into the scene (clamped) — past the reveal, inside the hold —
      // so the selected element is fully on screen and the coral box hugs it.
      const f = Math.round(Math.min(outF - 2, inF + (outF - inF) * 0.45));
      playerRef.current.pause();
      playerRef.current.seekTo(Math.max(inF, f));
      setFrame(Math.max(inF, f));
    }
  }, []);

  // Enter inline-edit on a text element: pause the Player so the overlay textbox
  // hugs a stable rect, then mark { sceneId, field, key }. `key` is the scene.data
  // text key this field writes to (resolved from the field name). Non-text fields
  // (geo plates, lists) are NOT inline-editable here and are ignored.
  const beginInlineEdit = useCallback(({ sceneId, field }) => {
    const key = TEXT_KEY_FOR_FIELD[field];
    if (!key) return; // not an inline-editable text field
    playerRef.current?.pause();
    setEditing({ sceneId, field, key });
  }, []);

  // Commit / cancel just clear the editing state — edits already flowed live into
  // props via update(mutator) as the user typed (commit), or were restored by the
  // InlineEditor itself before it calls onCancel.
  const endInlineEdit = useCallback(() => setEditing(null), []);

  // Enter while an editable TEXT element is selected -> enter inline-edit mode.
  // Returns true when it handled the key (so the hook preventDefaults it).
  const onEnter = useCallback(() => {
    if (editing) return false; // already editing; let the textbox own Enter
    if (selected && TEXT_KEY_FOR_FIELD[selected.field]) {
      beginInlineEdit(selected);
      return true;
    }
    return false;
  }, [editing, selected, beginInlineEdit]);

  // Esc from anywhere: exit inline edit if active, else clear the element
  // selection. (The shortcut hook routes Escape here even while typing.)
  const onEscape = useCallback(() => {
    if (editing) {
      // Defer to the editor's own cancel path by toggling a flag it watches; the
      // simplest robust behavior is: blur the active inline input (which restores
      // the original via the InlineEditor's cancel) then clear editing.
      setEditing((cur) => {
        if (cur) {
          // signal cancel: InlineEditor reads `editing.cancelNonce` to restore.
          return { ...cur, cancel: (cur.cancel || 0) + 1 };
        }
        return cur;
      });
    } else if (selected) {
      setSelected(null);
    }
  }, [editing, selected]);

  // Wire the delegated click/hover handlers onto the Player's stage container.
  usePreviewSelection(stageRef, {
    enabled: !!props,
    onPick: selectElement,
    onHover: (el) =>
      setHoverSel(
        el
          ? { sceneId: el.getAttribute("data-scene-id"), field: el.getAttribute("data-field") }
          : null
      ),
    onActivate: beginInlineEdit, // double-click an editable text element
  });

  // Keyboard shortcuts (Space / arrows / Home / End / Esc), driving playerRef.
  useShortcuts({
    playerRef,
    total: dur,
    fps,
    enabled: !!props,
    frame,
    setFrame,
    onEscape,
    onEnter,
  });

  const save = async () => {
    if (!runId) return note("Loaded a local file — no run dir to Save into.", "error");
    setBusy(true);
    note("Saving edits …", "working");
    try {
      const r = await fetch("/api/editor/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: runId, props }),
      });
      const d = await r.json();
      if (d.error) note("Save failed: " + d.error, "error");
      else {
        note("Saved props.edited.json", "ok");
        setDirty(false);
        // We are now viewing a saved edit; reflect that in the source + run list
        // so the EDITED pill / revert toggle are accurate.
        setSource("props.edited.json");
        setRuns((rs) => rs.map((r) => (r.id === runId ? { ...r, hasEdited: true } : r)));
        setLog((d.renderCommand || "") + "\n");
      }
    } catch (e) {
      note("Save failed: " + e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const render = async () => {
    if (!runId) return note("No run id — cannot render.", "error");
    setBusy(true);
    setShowLog(true);
    note("Rendering edited.mp4 …", "working");
    setLog("");
    try {
      const resp = await fetch("/api/editor/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: runId }),
      });
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        setLog(buf.split("__DONE__")[0].slice(-6000));
      }
      const done = buf.split("__DONE__")[1];
      if (done) {
        const res = JSON.parse(done.trim());
        if (res.ok) note("Exported edited.mp4", "ok");
        else note("Render failed (exit " + res.code + ")", "error");
      } else {
        note("Render stream ended.", "idle");
      }
    } catch (e) {
      note("Render failed: " + e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  // Back to the Walk Studio dashboard. serve.py redirects "/" to the dashboard.
  // Guard against losing in-progress work: if there are unsaved edits, confirm
  // before leaving. Shared by the back control AND the clickable wordmark logo.
  const goHome = useCallback(() => {
    if (dirty && !window.confirm("Leave the editor? Unsaved edits will be lost.")) return;
    window.location.assign("/");
  }, [dirty]);

  const inputProps = useMemo(() => props || {}, [props]);
  const secs = (dur / fps).toFixed(1);
  const editedFlag = runs.find((r) => r.id === runId)?.hasEdited;
  // Whether the props currently loaded came from props.edited.json (vs the clean
  // original). Drives the EDITED pill + the revert/load-edit toggle. Default
  // loads are always the original, so this is false unless explicitly opted in.
  const viewingEdited = source === "props.edited.json";

  const revertBtnStyle = {
    appearance: "none",
    background: "var(--glass-2)",
    color: "var(--text-2)",
    border: "1px solid var(--glass-edge)",
    borderRadius: "var(--r-ctl)",
    padding: "6px 11px",
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
    whiteSpace: "nowrap",
  };

  const statusDot = {
    idle: "var(--dim)",
    working: "var(--accent)",
    ok: "var(--pos)",
    error: "var(--neg)",
  }[statusKind];

  return (
    <div style={{ display: "flex", height: "100vh", flexDirection: "column", position: "relative" }}>
      {/* ============================================== FLOATING GLASS TOP BAR */}
      <header
        className="ws-glass"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "0 16px 0 18px",
          height: 56,
          margin: "12px 14px 0",
          borderRadius: "var(--r-card)",
          flex: "0 0 auto",
          position: "relative",
          zIndex: 30,
        }}
      >
        {/* Far-left exit back to the Walk Studio dashboard. Neutral secondary
            control (NOT coral — that's reserved for Export). Left-chevron SVG
            matches the header icon vocabulary; dirty-state confirm via goHome. */}
        <button
          type="button"
          onClick={goHome}
          title="Back to Walk Studio"
          className="ws-backnav"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            appearance: "none",
            background: "var(--glass)",
            color: "var(--text-2)",
            border: "1px solid var(--line)",
            borderRadius: "var(--r-ctl)",
            padding: "7px 12px 7px 9px",
            fontSize: 12.5,
            fontWeight: 600,
            cursor: "pointer",
            whiteSpace: "nowrap",
            flex: "0 0 auto",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M14 6l-6 6 6 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Walk Studio
        </button>

        <div style={{ width: 1, height: 26, background: "var(--glass-edge)" }} />

        <Wordmark onClick={goHome} />

        <div style={{ width: 1, height: 26, background: "var(--glass-edge)" }} />

        {/* Run picker */}
        <label style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ fontSize: 10, letterSpacing: 1.4, textTransform: "uppercase", color: "var(--muted)", fontWeight: 700 }}>Run</span>
          <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
            <select
              value={runId || ""}
              onChange={(e) => loadRun(e.target.value)}
              style={{
                appearance: "none",
                background: "var(--glass-2)",
                color: "var(--text)",
                border: "1px solid var(--glass-edge)",
                borderRadius: "var(--r-ctl)",
                padding: "8px 32px 8px 12px",
                fontSize: 12.5,
                fontWeight: 600,
                fontFamily: "var(--code)",
                maxWidth: 230,
                outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="" disabled>select a run…</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id}{r.hasEdited ? "  (edited)" : ""}
                </option>
              ))}
            </select>
            <Icon.chevron style={{ position: "absolute", right: 11, color: "var(--muted)", pointerEvents: "none" }} />
          </div>
        </label>
        {/* When a saved edit exists, offer to load it (or revert to the clean
            original). The DEFAULT load is always the original props.json. */}
        {editedFlag && runId ? (
          viewingEdited ? (
            <button
              type="button"
              onClick={() => loadRun(runId)}
              title="Discard the saved edit view and reload the clean, generated props.json"
              style={revertBtnStyle}
            >
              Revert to original
            </button>
          ) : (
            <button
              type="button"
              onClick={() => loadRun(runId, { edited: true })}
              title="Load the previously saved props.edited.json for this run"
              style={revertBtnStyle}
            >
              Load saved edit
            </button>
          )
        ) : null}
        {viewingEdited ? <Pill tone="accent">EDITED</Pill> : null}

        <label style={{ fontSize: 11, color: "var(--muted)", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 5 }}>
          <input type="file" accept="application/json,.json" onChange={onFile} style={{ display: "none" }} />
          <span style={{ textDecoration: "underline", textUnderlineOffset: 2, color: "var(--text-2)" }}>open file</span>
        </label>

        <div style={{ flex: 1 }} />

        {/* Live status chip */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginRight: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: 999, background: statusDot, boxShadow: statusKind === "working" ? "0 0 9px var(--accent-glow-strong)" : "none", animation: statusKind === "working" ? "ws-pulse 1.4s var(--ease) infinite" : "none" }} />
          <span style={{ fontSize: 11.5, color: "var(--text-2)", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{status}</span>
        </div>

        <Button kind="glass" onClick={save} disabled={busy || !props} icon={<Icon.save />}>
          {dirty ? "Save edits" : "Saved"}
        </Button>
        <Button
          kind="primary"
          onClick={render}
          disabled={busy || !props || !runId}
          icon={busy ? <Icon.spinner /> : <Icon.export />}
        >
          {busy ? "Exporting…" : "Export"}
        </Button>
      </header>

      {/* ======================================================== BODY */}
      <div style={{ display: "flex", flex: 1, minHeight: 0, padding: "12px 14px 14px", gap: 14 }}>
        {/* ----------------------------- LEFT: PREVIEW STAGE + TIMELINE */}
        <main
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            gap: 14,
            position: "relative",
          }}
        >
          {/* faint grid texture behind the stage — dark hairlines at very low
              opacity so the light page doesn't read as a dead flat template */}
          <div
            style={{
              position: "absolute",
              inset: -14,
              pointerEvents: "none",
              opacity: 0.6,
              backgroundImage:
                "linear-gradient(rgba(20,23,28,.025) 1px, transparent 1px), linear-gradient(90deg, rgba(20,23,28,.025) 1px, transparent 1px)",
              backgroundSize: "46px 46px",
              maskImage: "radial-gradient(820px 520px at 50% 34%, #000 0%, transparent 80%)",
              WebkitMaskImage: "radial-gradient(820px 520px at 50% 34%, #000 0%, transparent 80%)",
            }}
          />

          {/* PREVIEW STAGE
              Height-constrained flex column. The section flexes to fill the space
              left between the top bar and the bottom timeline (flex:1, minHeight:0),
              and its inner column fills that height (height:100%, minHeight:0). The
              CANVAS row flexes/shrinks; the pills row + the controls row keep their
              natural reserved height. The canvas card is height-capped so the 16:9
              Player can never grow past the available room — which is what used to
              push the play/scrub bar down UNDER the timeline at the default window
              size. Now the preview shrinks first; the controls stay fully visible. */}
          <section
            style={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 14,
              position: "relative",
            }}
          >
            <div style={{ width: "100%", maxWidth: 1080, height: "100%", minHeight: 0, display: "flex", flexDirection: "column", gap: 13, alignItems: "center" }}>
              {/* format + duration pills ABOVE the canvas (fixed-height row) */}
              <div style={{ flex: "0 0 auto", display: "flex", alignItems: "center", gap: 9, alignSelf: "stretch", justifyContent: "center", flexWrap: "wrap" }}>
                <Pill tone="live">LIVE PREVIEW</Pill>
                <span style={{ width: 3, height: 3, borderRadius: 999, background: "var(--dim)" }} />
                <Pill>16 : 9 · 1920×1080</Pill>
                <Pill>{props?.scenes?.length ?? 0} scenes</Pill>
                <Pill>{secs}s · {fps}fps</Pill>
                <span style={{ flex: 1 }} />
                {/* discoverability cue for the headline click-to-select feature */}
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10.5, color: "var(--muted)", fontWeight: 600 }}>
                  <span style={{ display: "inline-flex", color: "var(--accent)" }}><Icon.cursor /></span>
                  Click any element to select &amp; edit
                </span>
              </div>

              {/* the framed canvas — a clean white card holding the dark video
                  (mirrors the dashboard's one dark surface sitting on white).
                  This row FLEXES + SHRINKS to fill the space left by the pills +
                  controls rows; minHeight:0 lets it shrink below content size.
                  The card sizes itself to the 16:9 Player but is capped at the
                  available height (maxHeight:100% on the aspect box) so it can
                  never overflow the column and push the controls off-screen. */}
              <div
                style={{
                  position: "relative",
                  flex: "1 1 auto",
                  minHeight: 0,
                  width: "auto",
                  maxWidth: "100%",
                  borderRadius: "var(--r-lg)",
                  padding: 10,
                  background: "var(--bg-1, #FFFFFF)",
                  border: "1px solid var(--line)",
                  boxShadow: "var(--shadow-pop)",
                  display: "flex",
                }}
              >
                {/* stageRef wraps the Player DOM: the delegated click/hover
                    handlers + the coral SelectionOverlay live on this box.
                    position:relative anchors the absolute overlay. The aspectRatio
                    + maxHeight:100% make the dark video honor BOTH the available
                    width and the available height — whichever is the binding
                    constraint — keeping the whole stage inside the flex column. */}
                <div
                  ref={stageRef}
                  style={{ position: "relative", aspectRatio: "16 / 9", maxHeight: "100%", maxWidth: "100%", margin: "auto", borderRadius: 12, overflow: "hidden", background: "var(--video-bg)", boxShadow: "0 0 0 1px rgba(20,23,28,.08) inset" }}
                >
                  {props ? (
                    <Player
                      ref={playerRef}
                      component={Timeline}
                      inputProps={inputProps}
                      durationInFrames={dur}
                      fps={fps}
                      compositionWidth={1920}
                      compositionHeight={1080}
                      loop
                      clickToPlay={false}
                      style={{ width: "100%", height: "100%", display: "block" }}
                      acknowledgeRemotionLicense
                    />
                  ) : (
                    <div style={{ color: "var(--muted)", padding: 80, textAlign: "center", aspectRatio: "16 / 9", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      Loading preview…
                    </div>
                  )}
                  {/* coral selection box + faint hover cue + FUNCTIONAL drag
                      handles (resize/move geo-backed elements), tracking the
                      live elements. Hidden visually while inline-editing text. */}
                  <SelectionOverlay
                    stageRef={stageRef}
                    selected={selected}
                    hoverSel={hoverSel}
                    frame={frame}
                    editing={editing}
                    scene={props?.scenes?.[activeIdx]}
                    update={update}
                    activeIdx={activeIdx}
                  />
                  {/* inline text editor — an overlay textbox over the element */}
                  <InlineEditor
                    stageRef={stageRef}
                    editing={editing}
                    frame={frame}
                    value={editValue}
                    onChange={setEditValue}
                    onCommit={endInlineEdit}
                    onCancel={endInlineEdit}
                  />
                </div>
              </div>

              {/* playback controls BELOW the canvas (glass pill). flex:0 0 auto so
                  this row ALWAYS keeps its full height and is never compressed or
                  covered — the preview canvas above shrinks first. */}
              {props ? (
                <div style={{ flex: "0 0 auto", width: "min(680px, 100%)" }}>
                  <PlayerControls playerRef={playerRef} frame={frame} setFrame={setFrame} total={dur} fps={fps} />
                </div>
              ) : null}
            </div>
          </section>

          {/* BOTTOM TIMELINE */}
          {props ? (
            <section
              className="ws-glass"
              style={{
                flex: "0 0 auto",
                borderRadius: "var(--r-card)",
                padding: "12px 16px 14px",
                position: "relative",
                zIndex: 5,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <span style={{ color: "var(--accent)", display: "flex" }}><Icon.film /></span>
                <span style={{ fontSize: 10.5, letterSpacing: 1.5, textTransform: "uppercase", color: "var(--text-2)", fontWeight: 700 }}>Timeline</span>
                <span style={{ fontSize: 10.5, color: "var(--dim)", fontFamily: "var(--code)" }}>click a clip or a preview element to select + seek</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontSize: 10.5, color: "var(--muted)", fontFamily: "var(--code)", fontVariantNumeric: "tabular-nums" }}>
                  frame {Math.round(frame)} / {dur}
                </span>
              </div>
              <TimelineTrack
                props={props}
                activeIdx={activeIdx}
                onSelect={selectScene}
                currentFrame={frame}
                total={dur}
                fps={fps}
              />
            </section>
          ) : null}

          {/* render log drawer (floats at the bottom when present) */}
          {log ? (
            <div
              className="ws-glass"
              style={{ borderRadius: "var(--r-card)", overflow: "hidden", flex: "0 0 auto", position: "relative", zIndex: 5 }}
            >
              <button
                onClick={() => setShowLog((s) => !s)}
                style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "9px 16px", background: "transparent", border: "none", color: "var(--muted)", textAlign: "left" }}
              >
                <Icon.chevron style={{ transform: showLog ? "rotate(0)" : "rotate(-90deg)", transition: "transform .18s var(--ease)" }} />
                <span style={{ fontSize: 10.5, letterSpacing: 1.2, textTransform: "uppercase", fontWeight: 700 }}>Render log</span>
                {busy ? <Icon.spinner style={{ color: "var(--accent)" }} /> : null}
              </button>
              {showLog ? (
                <pre style={{ margin: 0, maxHeight: 130, overflow: "auto", background: "var(--panel-3)", color: "var(--text-2)", fontSize: 10.5, lineHeight: 1.5, padding: "10px 16px", borderTop: "1px solid var(--line)", whiteSpace: "pre-wrap", fontFamily: "var(--code)" }}>
                  {log}
                </pre>
              ) : null}
            </div>
          ) : null}
        </main>

        {/* ----------------------------------------------- RIGHT: INSPECTOR */}
        <aside
          className="ws-glass"
          style={{
            width: 388,
            flex: "0 0 388px",
            overflowY: "auto",
            borderRadius: "var(--r-card)",
            position: "relative",
            zIndex: 10,
          }}
        >
          {props ? (
            <EditPanel props={props} activeIdx={activeIdx} setActiveIdx={selectScene} update={update} focusField={focusField} />
          ) : (
            <div style={{ padding: 20, color: "var(--muted)" }}>No props loaded.</div>
          )}
        </aside>
      </div>
    </div>
  );
}
