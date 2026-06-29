"use client";
// Filmo in-browser video editor — ported from the standalone Walk Studio editor
// (studio/editor/src/App.jsx) and adapted for Next 15 / React 19. The studio
// version loaded runs over /api/editor/* (filesystem); here the run's render props
// arrive as `initialProps` (loaded from InsForge `runs.props` by the page) and Save
// is wired to the `saveEditedProps` server action via the `onSave` callback.
//
//   ┌──────────────────────────────────────────────────────────────┐
//   │  FILMO top bar — back · wordmark · run label · Save           │
//   ├───────────────────────────────────────────┬──────────────────┤
//   │  PREVIEW STAGE (@remotion/player)          │   INSPECTOR       │
//   │  ◀ ▶ play/scrub                            │   text/theme/timing│
//   ├───────────────────────────────────────────┤                   │
//   │  BOTTOM TIMELINE — scene clips ∝ duration   │                   │
//   └───────────────────────────────────────────┴──────────────────┘
//
// Selecting a clip/element drives the inspector AND seeks the Player. Every
// inspector control mutates `props` state and the Player re-renders instantly
// (the live-edit point of the whole feature).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Player } from "@remotion/player";
import { Timeline } from "../_composition/Timeline";
import { EditPanel, TEXT_KEY_FOR_FIELD } from "./EditPanel.jsx";
import { TimelineTrack } from "./TimelineTrack.jsx";
import { PlayerControls } from "./PlayerControls.jsx";
import { SelectionOverlay, usePreviewSelection } from "./SelectionOverlay.jsx";
import { InlineEditor } from "./InlineEditor.jsx";
import { useShortcuts } from "./useShortcuts.js";
import { Button, Pill, Icon } from "./ui.jsx";
import "./editor.css";

// Filmo wordmark lockup (the same mark the rest of the app uses — soft blue blob
// + ring, NO coral tile, NO emoji) + an "Editor" tag so this reads as part of Filmo.
function Wordmark() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <svg width="26" height="26" viewBox="14 13 56 56" aria-hidden="true" style={{ display: "block" }}>
        <path
          fillRule="evenodd"
          fill="#3B82F6"
          d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"
        />
      </svg>
      <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
        <span style={{ fontWeight: 700, fontSize: 17, letterSpacing: -0.4, color: "var(--text)" }}>Filmo</span>
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

export function Editor({ runId, initialProps, brand, goal, assetBaseUrl, musicAssetName, downloadUrl, onSave, onExport, onBack }) {
  // The live, editable props. Seed the asset base so the preview resolves the run's
  // screenshots / VO / music against the InsForge bucket (when one is provided).
  const [props, setProps] = useState(() => seedProps(initialProps, assetBaseUrl));
  const [activeIdx, setActiveIdx] = useState(0);
  const [status, setStatus] = useState("Ready");
  const [statusKind, setStatusKind] = useState("ok"); // idle | working | ok | error
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [frame, setFrame] = useState(0);
  const [selected, setSelected] = useState(null); // { sceneId, field } | null
  const [hoverSel, setHoverSel] = useState(null);
  const [focusField, setFocusField] = useState(null); // { field, nonce } -> inspector
  const [editing, setEditing] = useState(null); // inline text edit state

  const playerRef = useRef(null);
  const stageRef = useRef(null);
  const propsRef = useRef(props);
  useEffect(() => {
    propsRef.current = props;
  }, [props]);

  const note = (msg, kind = "idle") => {
    setStatus(msg);
    setStatusKind(kind);
  };

  // Apply an immutable mutator and bump props identity so the Player re-renders.
  const update = useCallback((mutator) => {
    setProps((p) => (p ? mutator(p) : p));
    setDirty(true);
  }, []);

  const dur = Math.max(1, props?.total_frames || 1);
  const fps = props?.fps || 30;

  // Inline-edit value: scene.data[key] of the scene being edited (resolved by id).
  const editIdx = editing ? (props?.scenes || []).findIndex((s) => s.id === editing.sceneId) : -1;
  const editValue = editIdx >= 0 ? props?.scenes?.[editIdx]?.data?.[editing.key] ?? "" : "";
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

  // Select a scene by index: drive the inspector AND seek the Player to its in_frame.
  const selectScene = useCallback(
    (i, { clearElement = true } = {}) => {
      setActiveIdx(i);
      if (clearElement) setSelected(null);
      const s = propsRef.current?.scenes?.[i];
      if (s && playerRef.current) {
        const f = s.in_frame || 0;
        playerRef.current.pause();
        playerRef.current.seekTo(f);
        setFrame(f);
      }
    },
    []
  );

  // Select a composition ELEMENT clicked in the live preview (coral->blue box +
  // inspector focus + seek into the scene's hold so the box hugs real content).
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
      const f = Math.round(Math.min(outF - 2, inF + (outF - inF) * 0.45));
      playerRef.current.pause();
      playerRef.current.seekTo(Math.max(inF, f));
      setFrame(Math.max(inF, f));
    }
  }, []);

  // Seek the Player from the timeline track (click / scrub-drag). The track passes
  // a target frame; we clamp, pause, seek, and reflect it in `frame` so the playhead
  // + PlayerControls + inline overlays all track the new position live.
  const seekToFrame = useCallback(
    (f) => {
      const target = Math.max(0, Math.min(dur - 1, Math.round(f)));
      const pl = playerRef.current;
      if (pl) {
        pl.pause();
        pl.seekTo(target);
      }
      setFrame(target);
    },
    [dur]
  );

  const beginInlineEdit = useCallback(({ sceneId, field }) => {
    const key = TEXT_KEY_FOR_FIELD[field];
    if (!key) return;
    playerRef.current?.pause();
    setEditing({ sceneId, field, key });
  }, []);
  const endInlineEdit = useCallback(() => setEditing(null), []);

  const onEnter = useCallback(() => {
    if (editing) return false;
    if (selected && TEXT_KEY_FOR_FIELD[selected.field]) {
      beginInlineEdit(selected);
      return true;
    }
    return false;
  }, [editing, selected, beginInlineEdit]);

  const onEscape = useCallback(() => {
    if (editing) {
      setEditing((cur) => (cur ? { ...cur, cancel: (cur.cancel || 0) + 1 } : cur));
    } else if (selected) {
      setSelected(null);
    }
  }, [editing, selected]);

  usePreviewSelection(stageRef, {
    enabled: !!props,
    onPick: selectElement,
    onHover: (el) =>
      setHoverSel(
        el ? { sceneId: el.getAttribute("data-scene-id"), field: el.getAttribute("data-field") } : null
      ),
    onActivate: beginInlineEdit,
  });

  useShortcuts({ playerRef, total: dur, fps, enabled: !!props, frame, setFrame, onEscape, onEnter });

  // SAVE — hand the current props to the page's saveEditedProps server action.
  const save = async () => {
    if (!onSave) return;
    setBusy(true);
    note("Saving edits…", "working");
    try {
      const res = await onSave(props);
      if (res && res.ok === false) {
        note("Save failed" + (res.error ? ": " + res.error : ""), "error");
      } else {
        note("Saved", "ok");
        setDirty(false);
      }
    } catch (e) {
      note("Save failed: " + (e?.message || String(e)), "error");
    } finally {
      setBusy(false);
    }
  };

  // EXPORT — save the edits, then enqueue a re-render that produces a NEW video.
  // The run page polls runs.edited_url and surfaces the "Edited" cut when it lands.
  const exportVideo = async () => {
    if (!onExport) return;
    setExporting(true);
    note("Exporting — saving edits & queuing re-render…", "working");
    try {
      const res = await onExport(props);
      if (res && res.ok === false) {
        note("Export failed" + (res.error ? ": " + res.error : ""), "error");
      } else {
        note("Re-render queued — your edited video is rendering. Watch the run page.", "ok");
        setDirty(false);
      }
    } catch (e) {
      note("Export failed: " + (e?.message || String(e)), "error");
    } finally {
      setExporting(false);
    }
  };

  const inputProps = useMemo(() => props || {}, [props]);
  const secs = (dur / fps).toFixed(1);

  const statusDot = {
    idle: "var(--dim)",
    working: "var(--accent)",
    ok: "var(--pos)",
    error: "var(--neg)",
  }[statusKind];

  return (
    <div
      className="ws-editor-root"
      style={{ display: "flex", height: "calc(100vh - 56px)", minHeight: 560, flexDirection: "column", position: "relative" }}
    >
      {/* ===================================================== FILMO TOP BAR */}
      <header
        className="ws-glass"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "0 16px 0 14px",
          height: 56,
          margin: "12px 14px 0",
          borderRadius: "var(--r-card)",
          flex: "0 0 auto",
          position: "relative",
          zIndex: 30,
        }}
      >
        <button
          type="button"
          onClick={onBack}
          title="Back to build"
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
          Back
        </button>

        <div style={{ width: 1, height: 26, background: "var(--glass-edge)" }} />
        <Wordmark />
        <div style={{ width: 1, height: 26, background: "var(--glass-edge)" }} />

        {/* Run label (read-only — the editor is scoped to THIS run) */}
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <span style={{ fontSize: 9.5, letterSpacing: 1.2, textTransform: "uppercase", color: "var(--muted)", fontWeight: 700 }}>
            Editing
          </span>
          <span
            style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 280 }}
            title={goal || brand || runId}
          >
            {brand || goal || "Brand video"}
          </span>
        </div>

        <div style={{ flex: 1 }} />

        {/* Live status chip */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginRight: 4 }}>
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: 999,
              background: statusDot,
              boxShadow: statusKind === "working" ? "0 0 9px var(--accent-glow-strong)" : "none",
              animation: statusKind === "working" ? "ws-pulse 1.4s var(--ease) infinite" : "none",
            }}
          />
          <span style={{ fontSize: 11.5, color: "var(--text-2)", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {status}
          </span>
        </div>

        {downloadUrl ? (
          <a
            href={downloadUrl}
            className="ws-backnav"
            title="Download the delivered video as an MP4"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              appearance: "none",
              textDecoration: "none",
              background: "var(--glass)",
              color: "var(--text-2)",
              border: "1px solid var(--line)",
              borderRadius: "var(--r-ctl)",
              padding: "7px 13px",
              fontSize: 12.5,
              fontWeight: 600,
              cursor: "pointer",
              whiteSpace: "nowrap",
              flex: "0 0 auto",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Download
          </a>
        ) : null}
        <Button kind="glass" onClick={save} disabled={busy || exporting || !props} icon={busy ? <Icon.spinner /> : <Icon.save />}>
          {busy ? "Saving…" : dirty ? "Save edits" : "Saved"}
        </Button>
        <Button kind="primary" onClick={exportVideo} disabled={exporting || busy || !props} icon={exporting ? <Icon.spinner /> : <Icon.export />} title="Save edits and re-render a new video">
          {exporting ? "Exporting…" : "Export video"}
        </Button>
      </header>

      {/* ======================================================== BODY
          LEFT  = inspector (sliders & fields)
          RIGHT = preview canvas (top) + scene timeline (below)         */}
      <div style={{ display: "flex", flex: 1, minHeight: 0, padding: "12px 14px 14px", gap: 14 }}>
        {/* ------------------------------ LEFT: INSPECTOR RAIL */}
        <aside
          className="ws-glass"
          style={{
            width: 392,
            flex: "0 0 392px",
            borderRadius: "var(--r-card)",
            position: "relative",
            zIndex: 12,
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          {/* Inspector body — the slider/field editor for the selected scene.
              (EditPanel renders its own sticky "Inspector" header.) */}
          <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
            {props ? (
              <EditPanel props={props} activeIdx={activeIdx} setActiveIdx={selectScene} update={update} focusField={focusField} musicAssetName={musicAssetName} />
            ) : (
              <div style={{ padding: 20, color: "var(--muted)" }}>No props loaded.</div>
            )}
          </div>
        </aside>

        {/* ------------------------ RIGHT: PREVIEW CANVAS + TIMELINE */}
        <main style={{ flex: 1, minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column", gap: 14, position: "relative" }}>
          <div
            style={{
              position: "absolute",
              inset: -14,
              pointerEvents: "none",
              opacity: 0.6,
              backgroundImage:
                "linear-gradient(rgba(20,23,28,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(20,23,28,.04) 1px, transparent 1px)",
              backgroundSize: "46px 46px",
              maskImage: "radial-gradient(820px 520px at 50% 34%, #000 0%, transparent 80%)",
              WebkitMaskImage: "radial-gradient(820px 520px at 50% 34%, #000 0%, transparent 80%)",
            }}
          />

          <section style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, position: "relative" }}>
            <div style={{ width: "100%", maxWidth: 1080, height: "100%", minHeight: 0, display: "flex", flexDirection: "column", gap: 13, alignItems: "stretch" }}>
              <div style={{ flex: "0 0 auto", display: "flex", alignItems: "center", gap: 9, alignSelf: "stretch", justifyContent: "center", flexWrap: "wrap" }}>
                <Pill tone="live">LIVE PREVIEW</Pill>
                <span style={{ width: 3, height: 3, borderRadius: 999, background: "var(--dim)" }} />
                <Pill>16 : 9 · 1920×1080</Pill>
                <Pill>{props?.scenes?.length ?? 0} scenes</Pill>
                <Pill>{secs}s · {fps}fps</Pill>
                <span style={{ flex: 1 }} />
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10.5, color: "var(--muted)", fontWeight: 600 }}>
                  <span style={{ display: "inline-flex", color: "var(--accent)" }}><Icon.cursor /></span>
                  Click any element to select &amp; edit
                </span>
              </div>

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
                  alignItems: "center",
                  justifyContent: "center",
                  // The 16/9 stage derives its size from this card. Without a concrete
                  // width to measure against, aspect-ratio collapsed the stage to 0×0
                  // (blank preview). overflow:hidden + the centered flex keep the stage
                  // bounded by the card's real width/height.
                  overflow: "hidden",
                }}
              >
                <div
                  ref={stageRef}
                  style={{ position: "relative", aspectRatio: "16 / 9", height: "100%", width: "auto", maxHeight: "100%", maxWidth: "100%", margin: "auto", borderRadius: 12, overflow: "hidden", background: "var(--video-bg)", boxShadow: "0 0 0 1px rgba(14,19,32,.08) inset" }}
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

              {props ? (
                <div style={{ flex: "0 0 auto", width: "min(680px, 100%)" }}>
                  <PlayerControls playerRef={playerRef} frame={frame} setFrame={setFrame} total={dur} fps={fps} />
                </div>
              ) : null}
            </div>
          </section>

          {props ? (
            <section className="ws-glass" style={{ flex: "0 0 auto", borderRadius: "var(--r-card)", padding: "12px 16px 14px", position: "relative", zIndex: 5 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <span style={{ color: "var(--accent)", display: "flex" }}><Icon.film /></span>
                <span style={{ fontSize: 10.5, letterSpacing: 1.5, textTransform: "uppercase", color: "var(--text-2)", fontWeight: 700 }}>Timeline</span>
                <span style={{ fontSize: 10.5, color: "var(--dim)", fontFamily: "var(--code)" }}>click a clip or a preview element to select + seek</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontSize: 10.5, color: "var(--muted)", fontFamily: "var(--code)", fontVariantNumeric: "tabular-nums" }}>
                  frame {Math.round(frame)} / {dur}
                </span>
              </div>
              <TimelineTrack props={props} activeIdx={activeIdx} onSelect={selectScene} onSeek={seekToFrame} currentFrame={frame} total={dur} fps={fps} />
            </section>
          ) : null}
        </main>
      </div>
    </div>
  );
}

// Seed the editor's props: deep-clone the loaded run props (so edits never mutate
// the server payload) and inject the asset base URL the preview resolves against.
function seedProps(initialProps, assetBaseUrl) {
  if (!initialProps) return null;
  const cloned = structuredClone(initialProps);
  if (assetBaseUrl && cloned.assetBaseUrl == null) cloned.assetBaseUrl = assetBaseUrl;
  return cloned;
}
