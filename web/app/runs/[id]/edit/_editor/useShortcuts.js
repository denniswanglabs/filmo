// Editor keyboard shortcuts — wired once in App.jsx, driving the existing
// @remotion/player playerRef (the same instance the PlayerControls + timeline
// clips seek). Keeps parity with iMovie/Final-Cut muscle memory:
//
//   Space ................ play / pause
//   ArrowLeft / Right .... step -1 / +1 frame
//   Shift+Arrow .......... step -1 / +1 second (±fps)
//   Home / End ........... jump to first / last frame
//   Esc .................. deselect AND exit inline edit
//
// HARD rule: shortcuts NEVER fire while the user is typing in an input /
// textarea / contenteditable (the Inspector fields, the inline editor) — EXCEPT
// Esc, which must still cancel inline-edit + clear the selection from anywhere.
// preventDefault is called for the keys we own so Space doesn't scroll the page
// and the arrows don't move focus/scroll.
import { useEffect } from "react";

// True when focus is in a field where the keystroke is text the user is typing
// (so playback shortcuts must stand down). Covers <input>, <textarea>, and any
// contenteditable host.
function isTypingTarget(el) {
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return false;
}

// `opts` is read through a ref-free closure that is rebound on dependency change
// (App passes stable callbacks + the live frame/total/fps). Each handler reads
// the latest playerRef.current so a run reload (new Player instance) is fine.
export function useShortcuts({ playerRef, total, fps, enabled, frame, setFrame, onEscape, onEnter }) {
  useEffect(() => {
    if (!enabled) return;

    const clampSeek = (f) => {
      const pl = playerRef.current;
      if (!pl) return;
      const next = Math.max(0, Math.min(total - 1, Math.round(f)));
      pl.pause();
      pl.seekTo(next);
      setFrame(next);
    };

    const handler = (e) => {
      // Esc is special: it works even while typing (cancel inline edit / blur a
      // field / clear the selection). Let onEscape decide what to unwind.
      if (e.key === "Escape") {
        // Don't preventDefault unconditionally — let a native control (e.g. an
        // open <select>) still close — but App's onEscape clears our own state.
        onEscape?.(e);
        return;
      }

      // Every other shortcut stands down while the user is typing in a field.
      if (isTypingTarget(e.target)) return;
      // Leave modifier combos (Cmd/Ctrl/Alt) to the browser/OS — we only own
      // bare keys + Shift+Arrow.
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      // Enter (not typing in a field): enter inline-edit on the current selection
      // (App ignores it when nothing editable is selected).
      if (e.key === "Enter") {
        if (onEnter?.(e)) e.preventDefault();
        return;
      }

      const pl = playerRef.current;
      if (!pl) return;

      switch (e.key) {
        case " ": // Space — play/pause (preventDefault so the page doesn't scroll)
        case "Spacebar": {
          e.preventDefault();
          pl.isPlaying() ? pl.pause() : pl.play();
          return;
        }
        case "ArrowLeft": {
          e.preventDefault();
          clampSeek(frame - (e.shiftKey ? fps : 1));
          return;
        }
        case "ArrowRight": {
          e.preventDefault();
          clampSeek(frame + (e.shiftKey ? fps : 1));
          return;
        }
        case "Home": {
          e.preventDefault();
          clampSeek(0);
          return;
        }
        case "End": {
          e.preventDefault();
          clampSeek(total - 1);
          return;
        }
        default:
          return;
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [playerRef, total, fps, enabled, frame, setFrame, onEscape, onEnter]);
}
