"use client";
// Hera-style CHAT panel — the PRIMARY way to edit a video in Filmo. The user
// types a plain-language request ("make the title bigger", "change the headline
// to X", "make scene 2 longer", "more energetic") and the agent applies it and
// re-renders. The conversation IS the edit history.
//
//   ┌────────────────────────────┐
//   │  CHAT header — Editor agent │   (tab row: Chat | Advanced lives in Editor)
//   ├────────────────────────────┤
//   │  message stream             │   user bubbles (right, blue) +
//   │   • user: "make it bigger"  │   assistant bubbles (left, neutral)
//   │   • agent: "On it…"         │
//   │   • agent: "Done — preview" │
//   ├────────────────────────────┤
//   │  ▢ input  ………………  [Send]   │
//   └────────────────────────────┘
//
// The panel is presentational + owns the message list; the actual edit call is
// handed up via `onSend(message)` (wired to the editViaChat server action by the
// page). The parent tells us when a re-render LANDS (props refreshed) via the
// `renderSignal` prop so we can flip the pending "applying…" bubble to "Done".
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "./ui.jsx";

// Suggested starter prompts — one-tap examples that teach the interaction.
const SUGGESTIONS = [
  "Make the title bigger",
  "More energetic",
  "Make scene 2 a little longer",
  "Punch up the headline",
];

let _mid = 0;
const nextId = () => `m${++_mid}-${Date.now().toString(36)}`;

function Avatar({ who }) {
  if (who === "user") {
    return (
      <div
        style={{
          width: 26,
          height: 26,
          borderRadius: 8,
          flex: "0 0 auto",
          background: "var(--field)",
          border: "1px solid var(--line-2)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--muted)",
        }}
        aria-hidden
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="8" r="3.4" stroke="currentColor" strokeWidth="1.7" />
          <path d="M5.5 19.5a6.5 6.5 0 0113 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      </div>
    );
  }
  // Filmo agent mark — the soft blue blob, matching the wordmark.
  return (
    <div
      style={{
        width: 26,
        height: 26,
        borderRadius: 8,
        flex: "0 0 auto",
        background: "var(--accent-tint)",
        border: "1px solid var(--accent-line)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      aria-hidden
    >
      <svg width="15" height="15" viewBox="14 13 56 56">
        <path fillRule="evenodd" fill="var(--accent)" d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z" />
      </svg>
    </div>
  );
}

function Bubble({ m }) {
  const isUser = m.who === "user";
  const tone =
    m.kind === "error"
      ? { bg: "rgba(192,26,43,.06)", border: "rgba(192,26,43,.35)", color: "var(--neg)" }
      : isUser
        ? { bg: "var(--accent)", border: "transparent", color: "var(--accent-ink)" }
        : { bg: "var(--panel-2)", border: "var(--line)", color: "var(--text)" };
  return (
    <div
      style={{
        display: "flex",
        gap: 9,
        flexDirection: isUser ? "row-reverse" : "row",
        alignItems: "flex-start",
      }}
    >
      <Avatar who={m.who} />
      <div
        style={{
          maxWidth: "82%",
          borderRadius: 13,
          padding: "9px 12px",
          fontSize: 13,
          lineHeight: 1.5,
          background: tone.bg,
          color: tone.color,
          border: "1px solid " + tone.border,
          borderTopRightRadius: isUser ? 4 : 13,
          borderTopLeftRadius: isUser ? 13 : 4,
          boxShadow: isUser ? "0 1px 2px rgba(20,23,28,.10)" : "var(--shadow-card)",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {m.pending ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <Icon.spinner style={{ color: isUser ? "var(--accent-ink)" : "var(--accent)" }} />
            {m.text}
          </span>
        ) : (
          m.text
        )}
        {m.changes && m.changes.length ? (
          <div style={{ marginTop: 7, display: "flex", flexWrap: "wrap", gap: 5 }}>
            {m.changes.map((c) => (
              <span
                key={c}
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: 0.4,
                  textTransform: "uppercase",
                  color: "var(--accent)",
                  background: "var(--accent-tint)",
                  border: "1px solid var(--accent-line)",
                  borderRadius: 999,
                  padding: "1px 8px",
                }}
              >
                {c}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ChatPanel({ brand, onSend, busy, renderSignal, onOpenAdvanced, disabled }) {
  const [messages, setMessages] = useState(() => [
    {
      id: nextId(),
      who: "assistant",
      text:
        `I'm your editing agent for ${brand || "this video"}. Tell me what to change in plain language — "make the title bigger", "change the headline to …", "make scene 2 longer", "more energetic" — and I'll apply it and re-render the preview on the right.`,
    },
  ]);
  const [value, setValue] = useState("");
  // The id of the pending "applying… / re-rendering…" bubble waiting for a render.
  const pendingRef = useRef(null);
  const scrollRef = useRef(null);
  const taRef = useRef(null);

  // Keep the stream pinned to the newest message.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const push = useCallback((m) => {
    const id = m.id || nextId();
    setMessages((prev) => [...prev, { ...m, id }]);
    return id;
  }, []);

  const patch = useCallback((id, patchObj) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patchObj } : m)));
  }, []);

  // When the parent reports a fresh render landed (renderSignal bumps), resolve any
  // pending "applying…" bubble into a "Done — updated preview on the right." line.
  const prevSignal = useRef(renderSignal);
  useEffect(() => {
    if (renderSignal === prevSignal.current) return;
    prevSignal.current = renderSignal;
    const pid = pendingRef.current;
    if (pid) {
      patch(pid, { pending: false, text: "Done — your updated preview is on the right." });
      pendingRef.current = null;
    }
  }, [renderSignal, patch]);

  const submit = useCallback(
    async (textArg) => {
      const text = (textArg ?? value).trim();
      if (!text || busy || disabled) return;
      setValue("");
      push({ who: "user", text });
      // The pending assistant bubble — resolves on success (render lands) or flips
      // to the returned message on noop/error.
      const pid = push({ who: "assistant", text: "On it — reading your request…", pending: true });
      try {
        const res = await onSend(text);
        if (!res || res.kind === "error" || res.ok === false) {
          patch(pid, { pending: false, kind: "error", text: res?.message || "Something went wrong applying that." });
          pendingRef.current = null;
        } else if (res.kind === "noop") {
          patch(pid, { pending: false, text: res.message || "Nothing needed changing." });
          pendingRef.current = null;
        } else {
          // applied — keep it pending; it resolves when renderSignal bumps (re-render
          // lands). Show the model's "On it…" line and the change chips.
          patch(pid, { pending: true, text: (res.message || "Applying that and re-rendering…") + " (re-rendering — this takes a moment)", changes: res.changes });
          pendingRef.current = pid;
        }
      } catch (e) {
        patch(pid, { pending: false, kind: "error", text: "Edit failed: " + (e?.message || String(e)) });
        pendingRef.current = null;
      }
    },
    [value, busy, disabled, onSend, push, patch]
  );

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const showSuggestions = messages.length <= 1 && !busy;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* CHAT header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "13px 15px",
          borderBottom: "1px solid var(--line)",
          flex: "0 0 auto",
        }}
      >
        <Avatar who="assistant" />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12.5, fontWeight: 800, color: "var(--text)", letterSpacing: 0.1 }}>Editing agent</div>
          <div style={{ fontSize: 10.5, color: "var(--muted)" }}>Describe a change · the preview updates on the right</div>
        </div>
        <span style={{ flex: 1 }} />
        {onOpenAdvanced ? (
          <button
            type="button"
            onClick={onOpenAdvanced}
            className="ws-backnav"
            title="Open the precise slider inspector"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              background: "var(--glass)",
              color: "var(--text-2)",
              border: "1px solid var(--line)",
              borderRadius: "var(--r-ctl)",
              padding: "6px 10px",
              fontSize: 11.5,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <Icon.sliders />
            Advanced
          </button>
        ) : null}
      </div>

      {/* MESSAGE STREAM */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          overscrollBehavior: "contain",
          padding: "16px 15px",
          display: "flex",
          flexDirection: "column",
          gap: 13,
        }}
        aria-live="polite"
        aria-label="Editing conversation"
      >
        {messages.map((m) => (
          <Bubble key={m.id} m={m} />
        ))}

        {showSuggestions ? (
          <div style={{ marginTop: 2, display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "var(--dim)" }}>
              Try
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={busy || disabled}
                  onClick={() => submit(s)}
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--text-2)",
                    background: "var(--field)",
                    border: "1px solid var(--line)",
                    borderRadius: 999,
                    padding: "6px 12px",
                    cursor: busy || disabled ? "default" : "pointer",
                    opacity: busy || disabled ? 0.5 : 1,
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {/* INPUT */}
      <div style={{ flex: "0 0 auto", padding: "12px 14px 14px", borderTop: "1px solid var(--line)" }}>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 9,
            background: "var(--field)",
            border: "1px solid var(--line-2)",
            borderRadius: 14,
            padding: 8,
          }}
        >
          <textarea
            ref={taRef}
            className="ws-textarea"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={disabled}
            rows={1}
            placeholder={disabled ? "Editing unavailable for this run" : "Describe a change…"}
            aria-label="Describe a change"
            style={{
              flex: 1,
              resize: "none",
              minHeight: 24,
              maxHeight: 120,
              border: "none",
              background: "transparent",
              color: "var(--text)",
              fontSize: 13,
              lineHeight: 1.45,
              outline: "none",
              padding: "5px 6px",
            }}
          />
          <button
            type="button"
            onClick={() => submit()}
            disabled={busy || disabled || !value.trim()}
            title="Send (Enter)"
            aria-label="Send"
            style={{
              flex: "0 0 auto",
              width: 36,
              height: 36,
              borderRadius: 11,
              border: "1px solid transparent",
              background: "var(--accent-grad)",
              color: "var(--accent-ink)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: busy || disabled || !value.trim() ? "default" : "pointer",
              opacity: busy || disabled || !value.trim() ? 0.5 : 1,
              boxShadow: "0 1px 2px rgba(20,23,28,.18), inset 0 1px 0 rgba(255,255,255,.22)",
            }}
          >
            {busy ? (
              <Icon.spinner />
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M5 12h13M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </button>
        </div>
        <div style={{ marginTop: 7, fontSize: 10.5, color: "var(--dim)", lineHeight: 1.4 }}>
          Each request saves your edit and re-renders. Enter to send · Shift+Enter for a new line.
        </div>
      </div>
    </div>
  );
}
