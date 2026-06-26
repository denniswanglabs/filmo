// Hera-style CLICK-TO-SELECT: select a visual element by clicking it inside the
// live @remotion/player preview. This file owns two pieces:
//
//   1) usePreviewSelection(stageRef, { onPick, enabled })
//        Attaches delegated pointer handlers on the Player's stage container.
//        On click it finds the nearest `[data-scene-id]` ancestor of the click
//        target, reads its `data-scene-id` + `data-field`, and calls onPick.
//        On hover it tracks the element under the cursor so we can draw a faint
//        cue outline (without committing a selection).
//
//   2) <SelectionOverlay> — an absolutely positioned coral box (and a fainter
//        hover cue) drawn OVER the Player, hugging the target element's bounding
//        box. It re-measures on scene change / scrub / resize / scroll so the box
//        stays glued to the element as the video animates.
//
// Why a separate overlay rather than outlining the element directly: the Player
// renders the composition as real DOM, but those nodes animate (transform/scale)
// every frame and are owned by Remotion — we must not mutate their styles. An
// absolute overlay positioned from getBoundingClientRect() tracks them cleanly.
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

// The selectable element nearest to a click/hover target (or null).
function pickEl(target, stageEl) {
  if (!target || !stageEl) return null;
  const el = target.closest?.("[data-scene-id][data-field]");
  if (!el || !stageEl.contains(el)) return null;
  return el;
}

// Read a node's box RELATIVE to a container (so the absolute overlay positions
// correctly regardless of page scroll / the stage's own offset).
function relRect(el, containerEl) {
  const r = el.getBoundingClientRect();
  const c = containerEl.getBoundingClientRect();
  return { left: r.left - c.left, top: r.top - c.top, width: r.width, height: r.height };
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// data-field -> the scene.data text key it inline-edits (single plain text value).
// Mirrors EditPanel.TEXT_KEY_FOR_FIELD; kept here so the hover cue can show an
// I-beam + "double-click to edit" only on fields that ARE inline-editable text.
// (Duplicated rather than imported to keep this overlay module self-contained;
// the set is tiny + stable.)
export const INLINE_TEXT_FIELDS = new Set([
  "title",
  "subtitle",
  "kicker",
  "heading",
  "headingAccent",
  "punchWord",
  "statement",
  "headline",
  "caption",
  "overlayTitle",
  "footnote",
  "product",
]);

// Hook: wire click-to-select + hover-cue + double-click-to-edit onto the stage.
//   onPick({sceneId,field})     fires on a committed single click,
//   onHover(el|null)            reports the hovered selectable,
//   onActivate({sceneId,field}) fires on a double-click of an editable element
//                               (App routes text fields into inline-edit mode).
export function usePreviewSelection(stageRef, { onPick, onHover, onActivate, enabled = true }) {
  const onPickRef = useRef(onPick);
  const onHoverRef = useRef(onHover);
  const onActivateRef = useRef(onActivate);
  onPickRef.current = onPick;
  onHoverRef.current = onHover;
  onActivateRef.current = onActivate;

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || !enabled) return;

    const handleClick = (e) => {
      const el = pickEl(e.target, stage);
      if (!el) return; // click on empty canvas — leave selection as-is
      // Beat the Player's own click handler so a click SELECTS, not toggles play.
      e.preventDefault();
      e.stopPropagation();
      onPickRef.current?.({
        sceneId: el.getAttribute("data-scene-id"),
        field: el.getAttribute("data-field"),
        el,
      });
    };

    // Double-click: enter inline-edit on a text element (App ignores non-text).
    //
    // ALWAYS swallow the dblclick's default action inside the preview. The live
    // <Player> renders the composition as real DOM (brand logo <img>, a captured
    // page-URL in the device chrome, selectable title text). A native double-click
    // would (a) select text and (b) — crucially — let a follow-on image/text DRAG
    // drop onto the document and NAVIGATE the browser to that asset/URL ("jumps to
    // a different page"). We preventDefault + clear the selection so a double-click
    // can ONLY ever open the inline editor and NEVER leak to a browser navigation.
    const handleDouble = (e) => {
      e.preventDefault();
      e.stopPropagation();
      try {
        window.getSelection?.()?.removeAllRanges();
      } catch {}
      const el = pickEl(e.target, stage);
      if (!el) return; // empty canvas: nothing to edit, but nav is already blocked
      onActivateRef.current?.({
        sceneId: el.getAttribute("data-scene-id"),
        field: el.getAttribute("data-field"),
        el,
      });
    };

    // Belt-and-braces: kill drag-to-navigate inside the preview. Dragging a brand
    // logo <img> (or a text run double-click selected) and dropping it on the page
    // makes the browser navigate to the image src / selected URL. The editor never
    // wants a drag here, so cancel it at the source.
    const handleDragStart = (e) => {
      if (stage.contains(e.target)) e.preventDefault();
    };

    const handleMove = (e) => {
      const el = pickEl(e.target, stage);
      onHoverRef.current?.(el || null);
      // I-beam over editable TEXT (it reads as "you can type here"); pointer over
      // other selectables (geo plates / lists open the inspector).
      const field = el?.getAttribute("data-field");
      stage.style.cursor = el ? (INLINE_TEXT_FIELDS.has(field) ? "text" : "pointer") : "default";
    };
    const handleLeave = () => {
      onHoverRef.current?.(null);
      stage.style.cursor = "default";
    };

    // Capture phase so we run BEFORE the Player's internal click-to-play handler.
    stage.addEventListener("click", handleClick, true);
    stage.addEventListener("dblclick", handleDouble, true);
    stage.addEventListener("pointermove", handleMove, true);
    stage.addEventListener("pointerleave", handleLeave, true);
    stage.addEventListener("dragstart", handleDragStart, true);
    return () => {
      stage.removeEventListener("click", handleClick, true);
      stage.removeEventListener("dblclick", handleDouble, true);
      stage.removeEventListener("pointermove", handleMove, true);
      stage.removeEventListener("pointerleave", handleLeave, true);
      stage.removeEventListener("dragstart", handleDragStart, true);
    };
  }, [stageRef, enabled]);
}

// Track a single element's box (by data-scene-id + data-field) inside the stage,
// re-measuring whenever `frame` changes (scrub/play), on resize and on a rAF tick
// while the video plays. Returns null when the element is not currently mounted
// (e.g. its scene isn't on screen). Exported so the InlineEditor overlay can hug
// the EXACT same rect the coral box uses (single source of geometry truth).
export function useTrackedRect(stageRef, sel, frame) {
  const [rect, setRect] = useState(null);
  const rafRef = useRef(0);

  const measure = useCallback(() => {
    const stage = stageRef.current;
    if (!stage || !sel) {
      setRect(null);
      return;
    }
    const el = stage.querySelector(
      `[data-scene-id="${CSS.escape(sel.sceneId)}"][data-field="${CSS.escape(sel.field)}"]`
    );
    setRect(el ? relRect(el, stage) : null);
  }, [stageRef, sel]);

  // Re-measure on selection change, on frame change (scrub/seek), and on resize.
  useLayoutEffect(() => {
    measure();
  }, [measure, frame]);

  useEffect(() => {
    if (!sel) return;
    // A short rAF loop keeps the box glued while the element animates (the first
    // ~1s of a scene reveal moves/scales it). Also covers play without frame prop
    // churn. Cheap: one getBoundingClientRect per frame, only while selected.
    let running = true;
    const tick = () => {
      if (!running) return;
      measure();
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    const onResize = () => measure();
    window.addEventListener("resize", onResize);
    return () => {
      running = false;
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", onResize);
    };
  }, [sel, measure]);

  return rect;
}

// ============================================================ DRAG GEOMETRY
// Per (archetype -> field) drag spec. Each handle drag writes scene.data.geo.<key>
// via update(mutator), LIVE. Two element kinds:
//   - "box":  a width/height-backed element (resize via corner handles) that can
//             also carry an offsetX/offsetY (move via body drag).
//   - "font": a pure-text element whose size maps cleanly to a font-size geo key
//             (resize via corner handles; no move — there is no offset literal).
// Every key listed here is one an archetype actually reads as
// `data.geo?.<key> ?? <literal>`, so when geo is absent the render is identical.
// Mins/maxes mirror the EditPanel GEO sliders so editor + drag stay in lockstep.
const DRAG_GEO = {
  "hero-title": {
    // The radial-glow "plate": resize W/H + move via offsetX/offsetY (added to
    // the archetype's center translate; absent -> 0 so identical).
    plate: {
      kind: "box",
      widthKey: "plateW", heightKey: "plateH",
      offsetXKey: "plateOffsetX", offsetYKey: "plateOffsetY",
      wMin: 200, wMax: 1600, hMin: 120, hMax: 900,
      wDefault: 1200, hDefault: 720,
    },
    title: { kind: "font", fontKey: "titleFontSize", min: 40, max: 220, default: 132 },
    subtitle: { kind: "font", fontKey: "subtitleFontSize", min: 16, max: 72, default: 34 },
  },
  "apple-hero": {
    title: { kind: "font", fontKey: "titleFontSize", min: 40, max: 220, default: 140 },
    subtitle: { kind: "font", fontKey: "subtitleFontSize", min: 16, max: 72, default: 32 },
  },
  "apple-screenshot": {
    // The browser card: resize cardW (horizontal) + shotH (vertical) + move.
    card: {
      kind: "box",
      widthKey: "cardW", heightKey: "shotH",
      offsetXKey: "cardOffsetX", offsetYKey: "cardOffsetY",
      wMin: 600, wMax: 1860, hMin: 300, hMax: 1000,
      wDefault: 1380, hDefault: 712,
    },
  },
  "apple-statement": {
    statement: { kind: "font", fontKey: "statementFontSize", min: 48, max: 200, default: 116 },
  },
};

// The drag spec for the current selection (or null if this element is text-only).
function dragSpecFor(scene, field) {
  if (!scene || !field) return null;
  return DRAG_GEO[scene.archetype]?.[field] || null;
}

// CSS-px -> composition-px scale (the stage renders the 1920-wide comp scaled to
// fit its width). One number; the comp is uniformly scaled so X and Y share it.
function compScale(stageEl) {
  const w = stageEl?.clientWidth || 0;
  return w > 0 ? 1920 / w : 1;
}

// The overlay layer: a SELECTED coral box + a fainter HOVER cue + FUNCTIONAL drag
// handles. The HOVER cue + label are pointer-events:none; only the drag-affordant
// pieces of the selected box (body + corner handles) opt back into pointer events
// so they never block a click meant for an unselected element.
export function SelectionOverlay({ stageRef, selected, hoverSel, frame, editing, scene, update, activeIdx }) {
  const selRect = useTrackedRect(stageRef, selected, frame);
  const hovRect = useTrackedRect(stageRef, hoverSel, frame);
  // Don't draw the hover cue on top of the already-selected element.
  const showHover =
    hovRect &&
    !(selected && hoverSel && selected.sceneId === hoverSel.sceneId && selected.field === hoverSel.field);

  // While inline-editing the InlineEditor owns the visuals — hide the coral box so
  // there isn't a double outline / handles fighting the textbox.
  const isEditing = !!editing && selected && editing.sceneId === selected.sceneId && editing.field === selected.field;

  const spec = dragSpecFor(scene, selected?.field);
  const canDrag = !!spec && !!update && activeIdx != null && activeIdx >= 0 && !isEditing;

  // Imperative drag: on pointerdown we snapshot the element's starting geo values
  // (current override OR the spec default) and the pointer origin, then write new
  // geo on each move scaled into composition px. A window-level listener set keeps
  // the drag alive even if the pointer leaves the small handle.
  const dragRef = useRef(null); // { mode, startX, startY, base:{...}, scale }

  const beginDrag = useCallback(
    (mode) => (e) => {
      if (!canDrag) return;
      e.preventDefault();
      e.stopPropagation();
      const stage = stageRef.current;
      const data = scene?.data || {};
      const geo = data.geo || {};
      const base = {
        w: geo[spec.widthKey] ?? spec.wDefault,
        h: geo[spec.heightKey] ?? spec.hDefault,
        ox: geo[spec.offsetXKey] ?? 0,
        oy: geo[spec.offsetYKey] ?? 0,
        font: geo[spec.fontKey] ?? spec.default,
      };
      dragRef.current = {
        mode, // "move" | corner id like "tl","tr","bl","br"
        startX: e.clientX,
        startY: e.clientY,
        base,
        scale: compScale(stage),
      };

      const onMove = (ev) => {
        const d = dragRef.current;
        if (!d) return;
        const dxComp = (ev.clientX - d.startX) * d.scale;
        const dyComp = (ev.clientY - d.startY) * d.scale;
        update((p) => {
          const next = structuredClone(p);
          const sd = next.scenes[activeIdx].data;
          sd.geo = { ...(sd.geo || {}) };
          const g = sd.geo;
          if (spec.kind === "font") {
            // Resize font: pull from the dominant axis (vertical feels natural for
            // type). Dragging a bottom handle DOWN grows it; a top handle UP grows.
            const grow =
              d.mode === "tl" || d.mode === "tr"
                ? -dyComp // top handles: up = grow
                : dyComp; // bottom handles: down = grow
            g[spec.fontKey] = clamp(Math.round(d.base.font + grow * 0.5), spec.min, spec.max);
          } else if (d.mode === "move") {
            g[spec.offsetXKey] = Math.round(d.base.ox + dxComp);
            g[spec.offsetYKey] = Math.round(d.base.oy + dyComp);
          } else {
            // Corner resize for a box. Each corner grows the box toward its
            // direction; the element is center-anchored, so width changes by
            // ~2x the horizontal drag is too aggressive — use 1x for a direct feel.
            const signX = d.mode === "tr" || d.mode === "br" ? 1 : -1;
            const signY = d.mode === "bl" || d.mode === "br" ? 1 : -1;
            g[spec.widthKey] = clamp(Math.round(d.base.w + signX * dxComp), spec.wMin, spec.wMax);
            g[spec.heightKey] = clamp(Math.round(d.base.h + signY * dyComp), spec.hMin, spec.hMax);
          }
          return next;
        });
      };
      const onUp = () => {
        dragRef.current = null;
        window.removeEventListener("pointermove", onMove, true);
        window.removeEventListener("pointerup", onUp, true);
      };
      window.addEventListener("pointermove", onMove, true);
      window.addEventListener("pointerup", onUp, true);
    },
    [canDrag, scene, spec, stageRef, update, activeIdx]
  );

  // Which corner handles do what for the current spec. Box: all four resize.
  // Font: all four resize (top grows-up, bottom grows-down). No-spec: inert (the
  // original decorative dots).
  const cornerDefs = [
    { id: "tl", style: { top: -5, left: -5 }, cursor: "nwse-resize" },
    { id: "tr", style: { top: -5, right: -5 }, cursor: "nesw-resize" },
    { id: "bl", style: { bottom: -5, left: -5 }, cursor: "nesw-resize" },
    { id: "br", style: { bottom: -5, right: -5 }, cursor: "nwse-resize" },
  ];

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 4 }}>
      {showHover ? (
        <div
          style={{
            position: "absolute",
            left: hovRect.left,
            top: hovRect.top,
            width: hovRect.width,
            height: hovRect.height,
            borderRadius: 6,
            outline: "1.5px dashed var(--accent-soft)",
            outlineOffset: 2,
            background: "rgba(59,130,246,.05)",
            transition: "all .06s linear",
          }}
        />
      ) : null}

      {selRect && !isEditing ? (
        <div
          style={{
            position: "absolute",
            left: selRect.left,
            top: selRect.top,
            width: selRect.width,
            height: selRect.height,
            borderRadius: 6,
            outline: "2px solid var(--accent)",
            outlineOffset: 2,
            boxShadow: "0 0 0 4px var(--accent-glow), 0 8px 24px -8px var(--accent-glow-strong)",
            transition: "left .06s linear, top .06s linear, width .06s linear, height .06s linear",
          }}
        >
          {/* Body drag = reposition (box specs with offset keys only). pointer-
              events:auto so it catches the drag; cursor reads "move". */}
          {canDrag && spec.kind === "box" ? (
            <div
              onPointerDown={beginDrag("move")}
              title="Drag to reposition"
              style={{
                position: "absolute",
                inset: 0,
                cursor: "move",
                pointerEvents: "auto",
                // a hair of background so the whole box is a grab target
                background: "rgba(59,130,246,.001)",
              }}
            />
          ) : null}

          {/* Corner handles. Functional when the element has a drag spec
              (box -> resize W/H; font -> resize font size); otherwise the
              original inert decorative dots. */}
          {cornerDefs.map((c) => {
            const live = canDrag;
            return (
              <span
                key={c.id}
                onPointerDown={live ? beginDrag(c.id) : undefined}
                title={
                  live
                    ? spec.kind === "font"
                      ? "Drag to resize text"
                      : "Drag to resize"
                    : undefined
                }
                style={{
                  position: "absolute",
                  ...c.style,
                  width: live ? 10 : 7,
                  height: live ? 10 : 7,
                  borderRadius: 2,
                  background: "#fff",
                  border: "1.5px solid var(--accent)",
                  boxShadow: "0 1px 2px rgba(20,23,28,.3)",
                  cursor: live ? c.cursor : "default",
                  pointerEvents: live ? "auto" : "none",
                }}
              />
            );
          })}

          {/* field tag — names what's selected, like Hera's element label.
              Appends a hint of what dragging does (resize / move). */}
          <span
            style={{
              position: "absolute",
              top: -22,
              left: -2,
              padding: "1.5px 7px",
              borderRadius: 6,
              background: "var(--accent)",
              color: "var(--accent-ink)",
              fontSize: 9.5,
              fontWeight: 800,
              letterSpacing: 0.6,
              textTransform: "uppercase",
              whiteSpace: "nowrap",
              boxShadow: "0 2px 6px rgba(59,130,246,.35)",
              fontFamily: "var(--ui)",
            }}
          >
            {FIELD_LABEL[selected?.field] || selected?.field}
            {canDrag ? (
              <span style={{ opacity: 0.75, fontWeight: 700, marginLeft: 6 }}>
                {spec.kind === "font" ? "drag = resize text" : "drag = move · corners = resize"}
              </span>
            ) : null}
          </span>
        </div>
      ) : null}
    </div>
  );
}

// Human label for the field tag shown above the selection box.
export const FIELD_LABEL = {
  title: "Title",
  subtitle: "Subtitle",
  kicker: "Kicker",
  heading: "Heading",
  headingAccent: "Heading accent",
  punchWord: "Punch word",
  statement: "Statement",
  headline: "Headline",
  caption: "Caption",
  overlayTitle: "Overlay title",
  footnote: "Footnote",
  product: "Product",
  plate: "Plate",
  card: "Card",
  bullets: "Bullets",
  cards: "Cards",
  entities: "Entities",
};
