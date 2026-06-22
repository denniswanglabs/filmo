// INLINE TEXT EDITOR — edit a text element IN PLACE inside the live preview.
//
// When App marks `editing = { sceneId, field, key }` (double-click an editable
// text element, or Enter while it is selected), this renders a single overlay
// textbox positioned EXACTLY over the element's tracked rect (the same
// useTrackedRect the coral SelectionOverlay uses) — we never mutate the Player's
// own animated DOM (that is deliberately avoided; the composition nodes are owned
// by Remotion and re-render every frame).
//
// Behaviour:
//   - Pre-filled with the current value, autofocused, select-all on mount.
//   - LIVE: keystrokes call update(mutator) -> props.scenes[idx].data[key], so the
//     Player re-renders as you type (the underlying element updates; this overlay
//     sits on top showing what you type).
//   - Commit on Enter (single-line) or blur; cancel on Esc (restore original).
//   - Matches the target element's font (size / family / weight / color / align /
//     letter-spacing / line-height) read from getComputedStyle so it reads as
//     in-place editing rather than a floating form field.
//
// The Player is paused by App before this mounts, so the tracked rect is stable.
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTrackedRect } from "./SelectionOverlay.jsx";

export function InlineEditor({ stageRef, editing, frame, value, onChange, onCommit, onCancel }) {
  const sel = editing ? { sceneId: editing.sceneId, field: editing.field } : null;
  const rect = useTrackedRect(stageRef, sel, frame);
  const inputRef = useRef(null);
  // The value at the moment editing began — restored verbatim on cancel (Esc).
  const originalRef = useRef("");
  // Font styles lifted from the real element so the box reads as in-place editing.
  const [font, setFont] = useState(null);
  // Snapshot the cancel signal nonce so a fresh editing session doesn't immediately
  // read a stale cancel.
  const cancelSeen = useRef(editing?.cancel || 0);

  // On (re)entering edit, capture the original value + read the element's font.
  useLayoutEffect(() => {
    if (!editing) return;
    originalRef.current = value ?? "";
    cancelSeen.current = editing.cancel || 0;
    const stage = stageRef.current;
    const el = stage?.querySelector(
      `[data-scene-id="${CSS.escape(editing.sceneId)}"][data-field="${CSS.escape(editing.field)}"]`
    );
    if (el) {
      const cs = getComputedStyle(el);
      // Many text fields render the value inside a child (e.g. the title splits to
      // lines); the container's own font is still a good match. Prefer the deepest
      // text-bearing node's font when the container has a single element child.
      const probe =
        el.childElementCount === 1 && el.firstElementChild
          ? getComputedStyle(el.firstElementChild)
          : cs;
      setFont({
        fontFamily: probe.fontFamily,
        fontSize: probe.fontSize,
        fontWeight: probe.fontWeight,
        letterSpacing: probe.letterSpacing,
        lineHeight: probe.lineHeight,
        color: probe.color,
        textAlign: cs.textAlign && cs.textAlign !== "start" ? cs.textAlign : "center",
        textTransform: probe.textTransform,
      });
    } else {
      setFont(null);
    }
    // Autofocus + select-all once mounted.
    const t = setTimeout(() => {
      const node = inputRef.current;
      if (node) {
        node.focus();
        node.select?.();
      }
    }, 0);
    return () => clearTimeout(t);
    // Re-run when the edit session identity changes (new field / re-entry).
  }, [editing?.sceneId, editing?.field, stageRef]); // eslint-disable-line react-hooks/exhaustive-deps

  // App signals a CANCEL by bumping editing.cancel (e.g. Esc routed through the
  // global shortcut while the textbox isn't the focus owner). Restore + close.
  useEffect(() => {
    if (!editing) return;
    if ((editing.cancel || 0) > cancelSeen.current) {
      cancelSeen.current = editing.cancel || 0;
      onChange(originalRef.current); // restore live value
      onCancel?.();
    }
  }, [editing, onChange, onCancel]);

  const commit = () => onCommit?.();
  const cancel = () => {
    onChange(originalRef.current); // restore the pre-edit value live
    onCancel?.();
  };

  const onKeyDown = (e) => {
    // Keep keystrokes local to the textbox; the global shortcut hook ignores
    // typing targets anyway, but stop propagation so nothing else reacts.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.stopPropagation();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      cancel();
    }
  };

  const boxStyle = useMemo(() => {
    if (!rect) return null;
    return {
      position: "absolute",
      left: rect.left,
      top: rect.top,
      width: rect.width,
      // Min height so a currently-empty field still gives a clickable target.
      height: Math.max(rect.height, 28),
    };
  }, [rect]);

  if (!editing) return null;
  // If the element isn't currently on screen we still render an input near the
  // top-left so the user can type (rare — App seeks into the hold before editing).
  const placed = boxStyle || { position: "absolute", left: 24, top: 24, width: 480, height: 60 };

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 6 }}>
      <textarea
        ref={inputRef}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        spellCheck={false}
        rows={1}
        style={{
          ...placed,
          pointerEvents: "auto",
          margin: 0,
          padding: 0,
          resize: "none",
          overflow: "hidden",
          background: "rgba(255,255,255,0.04)",
          border: "2px solid var(--accent)",
          borderRadius: 6,
          boxShadow: "0 0 0 4px var(--accent-glow), 0 10px 28px -8px var(--accent-glow-strong)",
          outline: "none",
          // Match the underlying element's typography so it reads in-place.
          fontFamily: font?.fontFamily,
          fontSize: font?.fontSize,
          fontWeight: font?.fontWeight,
          letterSpacing: font?.letterSpacing,
          lineHeight: font?.lineHeight,
          color: font?.color || "var(--text)",
          textAlign: font?.textAlign || "center",
          textTransform: font?.textTransform,
          caretColor: "var(--accent)",
          boxSizing: "border-box",
        }}
      />
    </div>
  );
}
