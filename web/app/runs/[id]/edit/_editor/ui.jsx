// House-style form primitives for the Walk Studio editor.
// Premium, restrained, Linear/Framer-grade. NO emojis anywhere — section markers
// and toggles use SVG glyphs / text only.
import React, { useState } from "react";

/* ------------------------------------------------------------------ icons */
export const Icon = {
  chevron: (p) => (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  plus: (p) => (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  ),
  trash: (p) => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M4 7h16M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-9 0l1 13a1 1 0 001 1h6a1 1 0 001-1l1-13"
        stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  save: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M5 3h11l3 3v15a0 0 0 01 0 0H5a2 2 0 01-2-2V5a2 2 0 012-2z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M8 3v5h7M8 21v-7h8v7" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  ),
  export: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M12 15V4m0 0L8 8m4-4l4 4" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 14v4a2 2 0 002 2h10a2 2 0 002-2v-4" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  ),
  spinner: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style={{ animation: "ws-spin .8s linear infinite" }} {...p}>
      <path d="M12 3a9 9 0 109 9" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  ),
  film: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3 9h18M3 15h18M8 4v16M16 4v16" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  play: (p) => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" {...p}>
      <path d="M8 5.2v13.6a1 1 0 001.52.85l11-6.8a1 1 0 000-1.7l-11-6.8A1 1 0 008 5.2z" />
    </svg>
  ),
  pause: (p) => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" {...p}>
      <rect x="6.5" y="5" width="3.6" height="14" rx="1.4" />
      <rect x="13.9" y="5" width="3.6" height="14" rx="1.4" />
    </svg>
  ),
  rewind: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M11 6L5 12l6 6M19 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  sliders: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="16" cy="7" r="2.4" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="8" cy="17" r="2.4" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  ),
  type: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M5 7V5h14v2M12 5v14M9 19h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  palette: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M12 3a9 9 0 100 18c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.2 0-1 .8-1.7 1.7-1.7H17a4 4 0 004-4c0-4.4-4-7.6-9-7.6z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx="7.5" cy="11.5" r="1.1" fill="currentColor" />
      <circle cx="9.5" cy="7.5" r="1.1" fill="currentColor" />
      <circle cx="14" cy="7" r="1.1" fill="currentColor" />
    </svg>
  ),
  clock: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <circle cx="12" cy="12" r="8.4" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  list: (p) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M8 6h12M8 12h12M8 18h12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="4" cy="6" r="1.3" fill="currentColor" />
      <circle cx="4" cy="12" r="1.3" fill="currentColor" />
      <circle cx="4" cy="18" r="1.3" fill="currentColor" />
    </svg>
  ),
  cursor: (p) => (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M5 3l6.5 16 2.2-6.3L20 10.5 5 3z" fill="currentColor" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  ),
};

/* ----------------------------------------------------------- collapsible Section */
export const Section = ({ title, hint, children, defaultOpen = true, badge, dense, icon, anchorId, flash }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section
      data-anchor={anchorId}
      style={{
        margin: "0 14px 12px",
        background: "var(--panel-2)",
        border: "1px solid " + (flash ? "var(--accent-line)" : "var(--line)"),
        borderRadius: "var(--r-card)",
        boxShadow: flash ? "0 0 0 3px var(--accent-glow), var(--shadow-card)" : "var(--shadow-card)",
        transition: "box-shadow .2s var(--ease), border-color .2s var(--ease)",
        overflow: "hidden",
        scrollMarginTop: 56,
      }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          width: "100%",
          padding: "11px 14px",
          background: "transparent",
          border: "none",
          color: "var(--text)",
          textAlign: "left",
        }}
      >
        {icon ? <span style={{ color: "var(--muted)", display: "flex", flex: "0 0 auto" }}>{icon}</span> : null}
        <span
          style={{
            fontSize: 10.5,
            letterSpacing: 1.6,
            textTransform: "uppercase",
            color: "var(--text-2)",
            fontWeight: 700,
          }}
        >
          {title}
        </span>
        {badge != null ? (
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "var(--muted)",
              background: "var(--field)",
              border: "1px solid var(--line)",
              borderRadius: 999,
              padding: "1px 7px",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {badge}
          </span>
        ) : null}
        {hint ? (
          <span style={{ fontSize: 11, color: "var(--dim)", fontFamily: "var(--code)" }}>{hint}</span>
        ) : null}
        <span style={{ flex: 1 }} />
        <Icon.chevron
          style={{
            color: "var(--muted)",
            transform: open ? "rotate(0deg)" : "rotate(-90deg)",
            transition: "transform .18s var(--ease)",
          }}
        />
      </button>
      {open ? <div style={{ padding: dense ? "0 13px 11px" : "2px 13px 13px" }}>{children}</div> : null}
    </section>
  );
};

/* --------------------------------------------------------------- labels / inputs */
const labelStyle = {
  display: "block",
  fontSize: 10.5,
  letterSpacing: 0.4,
  color: "var(--muted)",
  marginBottom: 5,
  fontWeight: 600,
};
const inputBase = {
  width: "100%",
  background: "var(--field)",
  border: "1px solid var(--line-2)",
  borderRadius: "var(--r-ctl)",
  color: "var(--text)",
  padding: "8px 10px",
  fontSize: 13,
  outline: "none",
};

// `anchorId` lets the click-to-select flow scroll-to + focus this field; `flash`
// briefly rings the input coral so it is obvious WHICH field the selection hit.
export const TextField = React.forwardRef(function TextField(
  { label, value, onChange, placeholder, multiline, anchorId, flash },
  ref
) {
  // Use the full `border` shorthand (not borderColor) so it doesn't conflict with
  // inputBase's `border` shorthand during the flash (avoids a React style warning).
  const flashStyle = flash
    ? { border: "1px solid var(--accent-line)", boxShadow: "0 0 0 3px var(--accent-glow)" }
    : null;
  return (
    <label data-anchor={anchorId} style={{ display: "block", marginBottom: 11, scrollMarginTop: 64 }}>
      {label ? <span style={labelStyle}>{label}</span> : null}
      {multiline ? (
        <textarea
          ref={ref}
          className="ws-textarea"
          value={value ?? ""}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          rows={2}
          style={{ ...inputBase, resize: "vertical", lineHeight: 1.45, minHeight: 56, ...flashStyle }}
        />
      ) : (
        <input
          ref={ref}
          className="ws-input"
          type="text"
          value={value ?? ""}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          style={{ ...inputBase, ...flashStyle }}
        />
      )}
    </label>
  );
});

export const NumberField = ({ label, value, onChange, min, max, step, suffix }) => (
  <label style={{ display: "block" }}>
    {label ? <span style={labelStyle}>{label}</span> : null}
    <div style={{ position: "relative" }}>
      <input
        className="ws-input"
        type="number"
        value={value ?? ""}
        min={min}
        max={max}
        step={step ?? 1}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
        style={{ ...inputBase, fontVariantNumeric: "tabular-nums", paddingRight: suffix ? 34 : 10 }}
      />
      {suffix ? (
        <span style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", fontSize: 11, color: "var(--dim)", pointerEvents: "none", fontFamily: "var(--code)" }}>
          {suffix}
        </span>
      ) : null}
    </div>
  </label>
);

/* ------------------------------------------------------------------- slider */
export const Slider = ({ label, value, fallback, onChange, min, max, step }) => {
  const v = value ?? fallback;
  const pct = Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
  const isDefault = value == null;
  return (
    <div style={{ marginBottom: 13 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ fontSize: 11.5, color: "var(--text-2)", fontWeight: 500 }}>{label}</span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "baseline",
            gap: 5,
            fontSize: 11.5,
            fontWeight: 700,
            color: isDefault ? "var(--muted)" : "var(--accent)",
            fontVariantNumeric: "tabular-nums",
            background: isDefault ? "transparent" : "var(--accent-tint)",
            border: "1px solid " + (isDefault ? "var(--line)" : "var(--accent-line)"),
            borderRadius: 999,
            padding: "1.5px 8px",
          }}
        >
          {Math.round(v)}
          {isDefault ? <span style={{ fontSize: 9, fontWeight: 600, color: "var(--dim)", letterSpacing: 0.4 }}>DEFAULT</span> : null}
        </span>
      </div>
      <input
        className="ws-range"
        type="range"
        min={min}
        max={max}
        step={step ?? 1}
        value={v}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ "--pct": pct + "%" }}
      />
    </div>
  );
};

/* ------------------------------------------------------------- color swatch */
export const ColorField = ({ label, value, onChange }) => {
  const hex = (value || "#000000").slice(0, 7);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        padding: "6px 8px",
        marginBottom: 6,
        background: "var(--field)",
        border: "1px solid var(--line)",
        borderRadius: "var(--r-ctl)",
      }}
    >
      <div style={{ position: "relative", width: 26, height: 26, flex: "0 0 auto" }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 7,
            background: hex,
            boxShadow: "0 0 0 1px rgba(255,255,255,.14) inset, 0 1px 3px rgba(0,0,0,.4)",
          }}
        />
        <input
          type="color"
          className="ws-swatch"
          value={hex}
          onChange={(e) => onChange(e.target.value)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0 }}
        />
      </div>
      <span style={{ fontSize: 11.5, color: "var(--muted)", width: 52, fontWeight: 500 }}>{label}</span>
      <input
        className="ws-input"
        type="text"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        style={{ ...inputBase, flex: 1, fontFamily: "var(--code)", fontSize: 11.5, padding: "5px 8px", textTransform: "uppercase" }}
      />
    </div>
  );
};

/* ----------------------------------------------------------------- buttons */
export const Button = ({ children, onClick, kind = "ghost", disabled, icon, title }) => {
  const [hover, setHover] = useState(false);
  const base = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    border: "1px solid var(--line-2)",
    borderRadius: "var(--r-ctl)",
    padding: "8px 14px",
    fontSize: 12.5,
    fontWeight: 600,
    letterSpacing: 0.1,
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.45 : 1,
    transition: "background .14s var(--ease), border-color .14s var(--ease), transform .1s var(--ease), box-shadow .14s var(--ease)",
    transform: hover && !disabled ? "translateY(-1px)" : "none",
    whiteSpace: "nowrap",
  };
  const kinds = {
    primary: {
      background: "var(--accent-grad)",
      color: "var(--accent-ink)",
      borderColor: "transparent",
      fontWeight: 700,
      boxShadow:
        (hover && !disabled
          ? "0 1px 2px rgba(20,23,28,.18), 0 10px 22px rgba(59,130,246,.32), "
          : "0 1px 2px rgba(20,23,28,.18), 0 6px 16px rgba(59,130,246,.24), ") +
        "inset 0 1px 0 rgba(255,255,255,.22)",
    },
    glass: {
      background: hover && !disabled ? "var(--bg-2)" : "var(--glass)",
      color: "var(--text)",
      borderColor: hover && !disabled ? "var(--line-2)" : "var(--line)",
      boxShadow: "0 1px 2px rgba(20,23,28,.05)",
    },
    ghost: {
      background: hover && !disabled ? "var(--panel-3)" : "var(--panel-2)",
      color: "var(--text)",
      borderColor: hover && !disabled ? "var(--line-2)" : "var(--line)",
    },
    tiny: {
      background: hover && !disabled ? "var(--panel-3)" : "var(--field)",
      color: "var(--text-2)",
      borderColor: "var(--line)",
      padding: "4px 9px",
      fontSize: 11,
      borderRadius: 7,
      transform: "none",
    },
    danger: {
      background: hover && !disabled ? "rgba(192,26,43,.08)" : "var(--field)",
      color: hover && !disabled ? "var(--neg)" : "var(--muted)",
      borderColor: hover && !disabled ? "rgba(192,26,43,.4)" : "var(--line)",
      padding: "4px 9px",
      fontSize: 11,
      borderRadius: 8,
      transform: "none",
    },
  };
  return (
    <button
      title={title}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ ...base, ...kinds[kind] }}
    >
      {icon}
      {children}
    </button>
  );
};

/* -------------------------------------------------------------------- chip / stat */
export const Pill = ({ children, tone = "neutral", title }) => {
  const tones = {
    neutral: { color: "var(--muted)", border: "var(--line)", bg: "var(--field)" },
    accent: { color: "var(--accent)", border: "var(--accent-line)", bg: "var(--accent-tint)" },
    live: { color: "var(--accent)", border: "var(--accent-line)", bg: "var(--accent-tint)" },
  };
  const t = tones[tone] || tones.neutral;
  return (
    <span
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: 0.5,
        color: t.color,
        background: t.bg,
        border: "1px solid " + t.border,
        borderRadius: 999,
        padding: "3px 9px",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {tone === "live" ? (
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--accent)", animation: "ws-pulse 1.6s var(--ease) infinite" }} />
      ) : null}
      {children}
    </span>
  );
};
