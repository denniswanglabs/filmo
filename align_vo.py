#!/usr/bin/env python3
"""align_vo.py -- Phase 1 module 1: VOICE ALIGNMENT.

Turns a VO script (per-scene beats from the plan) into one audio file PLUS
word-level timestamps, with every word mapped back to the scene that owns it.
The rest of the pivot pipeline (build_timeline.py + the Remotion <Timeline>
composition) builds the picture FROM this voice, so the picture can never drift.

ElevenLabs is the DEFAULT VO engine for EVERY video. We try ElevenLabs first (its
with-timestamps endpoint gives word alignment directly); on ANY failure -- missing
key, HTTP 401, quota_exceeded, network/timeout, any exception -- we AUTOMATICALLY
FALL BACK to the FREE path (edge-tts synth + local whisper-cli word timing) so a
render NEVER fails on VO. The `tier` arg is threaded by the cost-plus menu but no
longer GATES ElevenLabs; the only opt-out is WS_VO_PROVIDER in {"edge","free"}.
The run artifact records which engine actually ran (vo_engine) and whether it fell
back (vo_fallback) so an out-of-credits ElevenLabs is visible/diagnosable.

CLI:
  python3 align_vo.py --beats-file beats.json \\
      --out runs/<id>/vo_alignment.json [--tier free|premium] \\
      [--lang en] [--voice <name>]

beats.json: ordered per-scene VO segments -- [{scene_id, text}, ...] -- the same
shape the planner already emits under voiceover.beats (see plan_schema.resolve_vo_beats).

Output contract (vo_alignment.json):
  {
    "audio_path": "runs/<id>/voiceover.mp3",
    "lang": "en",
    "voice": "<resolved voice>",
    "tier": "free",
    "vo_engine": "edge-tts",       # which engine actually ran ("elevenlabs"|"edge-tts")
    "vo_fallback": true,           # true when ElevenLabs was tried but failed/keyless
    "vo_fallback_reason": "...",   # WHY it fell back (null when ElevenLabs ran)
    "total_duration_s": 3.21,
    "words": [{"word": "Stripe", "start_s": 0.24, "end_s": 0.39,
               "beat_scene_id": "title-open"}, ...],
    "beats": [{"scene_id": "title-open", "start_s": 0.24, "end_s": 2.9,
               "text": "..."}, ...]
  }
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# whisper-cli + model locations (audit-confirmed installed on this machine).
WHISPER_BIN = "/opt/homebrew/bin/whisper-cli"
WHISPER_MODEL = os.path.expanduser("~/.cache/whisper/ggml-base.en.bin")

# ElevenLabs premium VO config. Default voice = "Rachel" (a clear neutral
# narrator, ElevenLabs' canonical stock voice). model_id = eleven_multilingual_v2
# (high-quality, supports the with-timestamps endpoint). Override the voice id via
# the plan's voiceover.voice (a raw ElevenLabs voice id) or the WS_VO_VOICE_ID env.
ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — neutral narrator
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
# Map friendly names (the planner emits names like "Adam"/"Rachel") to stock ids,
# so a non-id voice still resolves to a real ElevenLabs voice.
ELEVENLABS_VOICE_IDS = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "antoni": "ErXwobaYiN019PkySvjV",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "josh": "TxGEqnHWrfWFTfGW9XjX",
    "sam": "yoZ06aMxZJJ28mfd3POQ",
}

_WORD_RE = re.compile(r"\w+(?:'\w+)?", re.UNICODE)


class AlignError(Exception):
    pass


def _norm(token):
    """Lowercase + strip non-alphanumerics for sequence comparison only.

    Robust to whisper mishears (Stripe->Strike) -- we DO NOT rely on exact text
    match for mapping; the sequence position carries the scene ownership.
    """
    return re.sub(r"[^a-z0-9]", "", (token or "").lower())


def tokenize(text):
    """Split a beat's text into comparable word tokens (script side)."""
    return _WORD_RE.findall(text or "")


def build_word_index(beats):
    """Concatenate beat texts and record the cumulative WORD-INDEX range each
    beat owns, so every script word knows its scene.

    Returns (owners, script_tokens) where owners is a list parallel to
    script_tokens giving each token's beat_scene_id, and `beats` are the
    cleaned beats (blank-text dropped).
    """
    owners = []
    script_tokens = []
    clean = []
    for b in beats or []:
        sid = b.get("scene_id")
        text = (b.get("text") or "").strip()
        if not sid or not text:
            continue
        toks = tokenize(text)
        if not toks:
            continue
        clean.append({"scene_id": sid, "text": text})
        for _ in toks:
            owners.append(sid)
        script_tokens.extend(toks)
    return owners, script_tokens, clean


def _resolve_voice_for_synth(voice):
    """Default voice name passed through to adapters.synthesize_voiceover."""
    return voice or "Adam"


# --------------------------------------------------------------------------- #
# 2. SYNTH -- one audio file of the FULL script                               #
# --------------------------------------------------------------------------- #
def synth_full_script(script, voice, out_path, tier, *, synth_fn=None,
                      elevenlabs_key=None):
    """Render the whole concatenated script to ONE audio file.

    ElevenLabs is the DEFAULT VO engine for EVERY video (independent of tier):
    whenever an API key is present we TRY ElevenLabs FIRST (its with-timestamps
    endpoint yields word alignment directly, so whisper is skipped). On ANY
    ElevenLabs failure -- missing key, HTTP 401, quota_exceeded, network/timeout,
    or any other exception -- we AUTOMATICALLY FALL BACK to the FREE path
    (edge-tts synth + local whisper-cli alignment) so the render NEVER fails on
    VO. ElevenLabs is currently out of credits, so in practice the fallback fires;
    the returned `vo_engine`/`vo_fallback`/`fallback_reason` make that visible.

    `tier` is kept (the cost-plus menu threads it from style_fill) but it no
    longer GATES ElevenLabs -- ElevenLabs is tried by default at any tier. The
    only opt-out is an explicit WS_VO_PROVIDER in {"edge", "free"}, which forces
    the $0 edge-tts + whisper path (used for debugging / a deliberate free build).

    Returns a dict:
      {"audio_path", "voice", "tier", "alignment" (None unless ElevenLabs ran),
       "vo_engine" ("elevenlabs" | "edge-tts"), "vo_fallback" (bool),
       "fallback_reason" (str | None)}.

    `synth_fn` is injectable for tests (defaults to adapters.synthesize_voiceover).
    """
    voice = _resolve_voice_for_synth(voice)
    key = elevenlabs_key
    if key is None:
        key = os.environ.get("ELEVENLABS_API_KEY")

    # PROVIDER DECISION: ElevenLabs is the DEFAULT for every video. An explicit
    # WS_VO_PROVIDER in {"edge","free"} is the ONLY opt-out (forces $0 edge-tts +
    # whisper). Any other value (including unset/empty/"elevenlabs") keeps the
    # ElevenLabs-first default. We do NOT gate on `tier` -- ElevenLabs is tried
    # regardless of free/premium so EVERY video defaults to the premium voice.
    provider = (os.environ.get("WS_VO_PROVIDER") or "").strip().lower()
    # `want_elevenlabs` = "ElevenLabs is the default AND was not explicitly opted
    # out". It drives vo_fallback: a free render is a FALLBACK only when ElevenLabs
    # WAS the intended engine. WS_VO_PROVIDER in {"edge","free"} is the only opt-out.
    want_elevenlabs = provider not in ("edge", "free")
    # TEST SEAM: an explicitly-injected synth_fn (deterministic $0 unit tests) must
    # never make a real ElevenLabs HTTP call, even if a real ELEVENLABS_API_KEY is
    # in the ambient env. We still treat ElevenLabs as the intended default (so the
    # recorded vo_fallback semantics are honest); we just skip the network attempt
    # and record the no-key/seam reason. A test that DOES want to drive the
    # ElevenLabs branch passes elevenlabs_key explicitly.
    skip_real_call = synth_fn is not None and elevenlabs_key is None

    fallback_reason = None
    if want_elevenlabs:
        # ElevenLabs-first. On ANY failure we fall through to the free path below
        # (a render NEVER blocks on a VO-provider outage / out-of-credits / no key).
        if not key or skip_real_call:
            fallback_reason = (
                "no ELEVENLABS_API_KEY (set it in ~/.hermes/.env or env)" if not key
                else "test seam: synth_fn injected, skipping ElevenLabs HTTP call")
            sys.stderr.write(
                "align_vo: WARNING ElevenLabs is the default VO but unavailable "
                "(%s); falling back to FREE (edge-tts + whisper).\n" % fallback_reason)
        else:
            try:
                info = _elevenlabs_synth_with_timestamps(script, voice, out_path, key)
                return {
                    "audio_path": out_path,
                    "voice": info.get("voice", voice),
                    "tier": tier,
                    "alignment": info.get("alignment"),
                    "vo_engine": "elevenlabs",
                    "vo_fallback": False,
                    "fallback_reason": None,
                }
            except Exception as e:
                # 401, quota_exceeded, network/timeout, decode, missing-audio, etc.
                fallback_reason = "ElevenLabs failed: %s" % e
                sys.stderr.write(
                    "align_vo: WARNING ElevenLabs synth failed (%s); "
                    "falling back to FREE (edge-tts + whisper).\n" % e)

    # FREE fallback path: edge-tts synth (whisper-cli does the alignment in align()).
    fn = synth_fn
    if fn is None:
        import adapters
        fn = adapters.synthesize_voiceover
    info = fn(script, voice, out_path, "edge")
    return {
        "audio_path": out_path,
        "voice": info.get("voice", voice),
        "tier": tier,
        "alignment": None,
        "vo_engine": "edge-tts",
        # vo_fallback is True only when ElevenLabs was attempted-and-failed (or
        # had no key). A deliberate WS_VO_PROVIDER=edge/free build is NOT a
        # fallback -- it's the explicitly requested free engine.
        "vo_fallback": want_elevenlabs,
        "fallback_reason": fallback_reason,
    }


def _resolve_elevenlabs_voice_id(voice):
    """Resolve a plan voice (a friendly name like "Adam"/"Rachel" OR a raw
    ElevenLabs voice id) to a real ElevenLabs voice id. WS_VO_VOICE_ID overrides
    everything; an unknown 20-char-ish token is assumed to already be a voice id;
    otherwise we fall back to Rachel (clear neutral narrator)."""
    env_id = (os.environ.get("WS_VO_VOICE_ID") or "").strip()
    if env_id:
        return env_id
    v = (voice or "").strip()
    if not v:
        return ELEVENLABS_DEFAULT_VOICE_ID
    if v.lower() in ELEVENLABS_VOICE_IDS:
        return ELEVENLABS_VOICE_IDS[v.lower()]
    # Heuristic: ElevenLabs voice ids are ~20 alnum chars. If it looks like one,
    # pass it through; otherwise use the default narrator.
    if re.fullmatch(r"[A-Za-z0-9]{18,24}", v):
        return v
    return ELEVENLABS_DEFAULT_VOICE_ID


def _elevenlabs_synth_with_timestamps(script, voice, out_path, key,
                                      *, opener=None):
    """PREMIUM synth: POST to the ElevenLabs with-timestamps endpoint, write the
    decoded mp3 to `out_path`, and return {"voice": <voice_id>, "alignment": ...}.

    Endpoint (REST): POST {ELEVENLABS_BASE}/text-to-speech/<voice_id>/with-timestamps
      Auth header:  xi-api-key: <key>
      Body (JSON):  {"text": <full script>, "model_id": <model>,
                     "voice_settings": {"stability", "similarity_boost", "style",
                                        "use_speaker_boost"}}
      Response JSON: {"audio_base64": <mp3 base64>,
                      "alignment": {"characters": [...],
                                    "character_start_times_seconds": [...],
                                    "character_end_times_seconds": [...]},
                      "normalized_alignment": {...}}
    The returned `alignment` object is already in the EXACT shape
    parse_elevenlabs_alignment consumes, so it is returned untouched.

    `opener` is injectable for tests (defaults to urllib.request.urlopen).
    Raises AlignError on any HTTP/decode failure so synth_full_script can fall
    back to the free path without spending again.
    """
    if not key:
        raise AlignError("ElevenLabs synth requires an API key")
    if not (script or "").strip():
        raise AlignError("ElevenLabs synth requires non-empty script text")

    voice_id = _resolve_elevenlabs_voice_id(voice)
    url = "%s/text-to-speech/%s/with-timestamps?output_format=mp3_44100_128" % (
        ELEVENLABS_BASE, voice_id)
    body = json.dumps({
        "text": script,
        "model_id": ELEVENLABS_MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"xi-api-key": key,
                 "Content-Type": "application/json",
                 "Accept": "application/json"})

    do_open = opener or urllib.request.urlopen
    try:
        with do_open(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            pass
        raise AlignError("ElevenLabs HTTP %s: %s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise AlignError("ElevenLabs network error: %s" % e.reason)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise AlignError("ElevenLabs returned non-JSON response: %s" % e)

    audio_b64 = payload.get("audio_base64") or payload.get("audio")
    if not audio_b64:
        raise AlignError("ElevenLabs response missing audio_base64")
    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as e:
        raise AlignError("ElevenLabs audio_base64 decode failed: %s" % e)
    if not audio_bytes:
        raise AlignError("ElevenLabs returned empty audio")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(audio_bytes)

    alignment = payload.get("alignment") or payload.get("normalized_alignment")
    if not alignment or not alignment.get("characters"):
        raise AlignError("ElevenLabs response missing character alignment")
    return {"voice": voice_id, "alignment": alignment}


# --------------------------------------------------------------------------- #
# 3. WORD TIMESTAMPS                                                           #
# --------------------------------------------------------------------------- #
def whisper_words(audio_path, *, whisper_bin=WHISPER_BIN, model=WHISPER_MODEL,
                  runner=None):
    """Run local whisper-cli on the audio and parse per-word timestamps.

    Uses `-ml 1 -sow` (split on word) + `-oj` (JSON) so each transcription
    segment is one word with millisecond offsets. Returns
    [{word, start_s, end_s}] in spoken order (empty-text segments dropped).
    `runner` is injectable for tests (defaults to a real subprocess call).
    """
    if not os.path.exists(whisper_bin):
        raise AlignError("whisper-cli not found at %s (install whisper-cpp)" % whisper_bin)
    if not os.path.exists(model):
        raise AlignError(
            "whisper model not found at %s -- download ggml-base.en.bin there" % model)

    base = audio_path.rsplit(".", 1)[0]
    json_path = base + ".json"
    cmd = [whisper_bin, "-m", model, "-f", audio_path,
           "-ml", "1", "-sow", "-oj", "-of", base]
    if runner is None:
        runner = _default_whisper_runner
    runner(cmd)
    if not os.path.exists(json_path):
        raise AlignError("whisper produced no JSON at %s" % json_path)
    with open(json_path) as f:
        data = json.load(f)
    return parse_whisper_json(data)


def _default_whisper_runner(cmd):  # pragma: no cover - real subprocess
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=300)


def parse_whisper_json(data):
    """Parse whisper-cli -oj output into [{word, start_s, end_s}].

    Each `transcription` item has `text` (leading-space, sometimes empty) and
    `offsets: {from, to}` in milliseconds.
    """
    out = []
    for seg in (data.get("transcription") or []):
        word = (seg.get("text") or "").strip()
        if not word:
            continue
        off = seg.get("offsets") or {}
        try:
            start_s = round(float(off.get("from", 0)) / 1000.0, 3)
            end_s = round(float(off.get("to", 0)) / 1000.0, 3)
        except (TypeError, ValueError):
            continue
        out.append({"word": word, "start_s": start_s, "end_s": end_s})
    return out


def parse_elevenlabs_alignment(alignment):
    """PREMIUM parser: group ElevenLabs per-CHARACTER timestamps into words.

    ElevenLabs returns parallel arrays:
      characters, character_start_times_seconds, character_end_times_seconds.
    A word boundary is any run of non-whitespace characters. Each word's
    start = first char start, end = last char end. Returns [{word,start_s,end_s}].
    (Not called in this build -- premium synth is shape-only -- but fully
    implemented + unit-tested so wiring the API later is a one-line swap.)
    """
    chars = (alignment or {}).get("characters") or []
    starts = (alignment or {}).get("character_start_times_seconds") or []
    ends = (alignment or {}).get("character_end_times_seconds") or []
    words = []
    cur, cur_start, cur_end = [], None, None
    for i, ch in enumerate(chars):
        if ch is not None and not str(ch).isspace():
            if not cur:
                cur_start = starts[i] if i < len(starts) else cur_start
            cur.append(ch)
            if i < len(ends):
                cur_end = ends[i]
        else:
            if cur:
                words.append({"word": "".join(cur),
                              "start_s": round(float(cur_start or 0), 3),
                              "end_s": round(float(cur_end or 0), 3)})
                cur, cur_start, cur_end = [], None, None
    if cur:
        words.append({"word": "".join(cur),
                      "start_s": round(float(cur_start or 0), 3),
                      "end_s": round(float(cur_end or 0), 3)})
    return words


# --------------------------------------------------------------------------- #
# 4. MAP each transcribed word to its beat/scene by SEQUENCE                   #
# --------------------------------------------------------------------------- #
def map_words_to_beats(hyp_words, owners, script_tokens):
    """Assign each transcribed (hypothesis) word an owning beat_scene_id by
    SEQUENCE alignment against the script tokens -- robust to tokenization drift
    (whisper mishears, merges, or splits words, so counts/strings rarely match
    exactly).

    Algorithm: a monotonic two-pointer walk. We advance a cursor through the
    script tokens as we consume hypothesis words. When the next script token
    matches (normalized) within a small look-ahead window we snap the cursor to
    it; otherwise the hypothesis word takes the current cursor's owner and the
    cursor advances by one. This keeps each hypothesis word attributed to a
    plausible script position even when boundaries drift, and never runs off the
    end (it clamps to the last token's owner). Returns a list of beat_scene_id
    parallel to hyp_words.

    `owners` and `script_tokens` are parallel (owners[i] owns script_tokens[i]).
    """
    out = []
    if not owners:
        return [None] * len(hyp_words)
    n = len(script_tokens)
    cursor = 0
    LOOKAHEAD = 4
    norm_tokens = [_norm(t) for t in script_tokens]
    for hw in hyp_words:
        hn = _norm(hw.get("word"))
        # Try to snap the cursor forward to a matching script token nearby.
        snapped = None
        for j in range(cursor, min(cursor + 1 + LOOKAHEAD, n)):
            if hn and norm_tokens[j] == hn:
                snapped = j
                break
        if snapped is not None:
            # Real match: attribute to this token, then consume it.
            cursor = snapped
            out.append(owners[min(cursor, n - 1)])
            if cursor < n - 1:
                cursor += 1
        else:
            # No match nearby -> this hypothesis word is a SPLIT/insertion (e.g.
            # 'checkout' heard as 'check'+'out') or a mishear of the current
            # token. Attribute it to the CURRENT cursor's owner WITHOUT consuming
            # a script token, so an extra hypothesis word can't push the cursor
            # past the beat boundary prematurely.
            out.append(owners[min(cursor, n - 1)])
    return out


def _beats_from_words(words, clean_beats):
    """Roll word timings up into per-beat spans: each beat's start_s = first
    owned word start, end_s = last owned word end. A beat that got NO words
    (e.g. fully misaligned/dropped) is still emitted with null spans so the
    downstream timeline can fall back to a minimum hold for it.
    """
    by_scene = {}
    for w in words:
        sid = w.get("beat_scene_id")
        if sid is None:
            continue
        slot = by_scene.setdefault(sid, [w["start_s"], w["end_s"]])
        slot[0] = min(slot[0], w["start_s"])
        slot[1] = max(slot[1], w["end_s"])
    out = []
    for b in clean_beats:
        sid = b["scene_id"]
        span = by_scene.get(sid)
        out.append({
            "scene_id": sid,
            "start_s": span[0] if span else None,
            "end_s": span[1] if span else None,
            "text": b["text"],
        })
    return out


# --------------------------------------------------------------------------- #
# 5. TOP-LEVEL ORCHESTRATOR                                                    #
# --------------------------------------------------------------------------- #
def align(beats, out_path, *, tier="free", lang="en", voice=None,
          synth_fn=None, whisper_fn=None, elevenlabs_key=None):
    """Full alignment: beats -> audio + word timings -> vo_alignment.json dict.

    Injectable seams for deterministic tests:
      synth_fn(script, voice, out, provider) -> {"voice": ...}
      whisper_fn(audio_path) -> [{word, start_s, end_s}]  (replaces whisper-cli)
    """
    owners, script_tokens, clean_beats = build_word_index(beats)
    if not clean_beats:
        raise AlignError("no usable beats (every beat had empty scene_id/text)")
    script = " ".join(b["text"] for b in clean_beats).strip()

    synth = synth_full_script(
        script, voice, out_path.rsplit(".", 1)[0] + ".audio.mp3"
        if out_path.endswith(".json") else out_path,
        tier, synth_fn=synth_fn, elevenlabs_key=elevenlabs_key)
    audio_path = synth["audio_path"]
    resolved_voice = synth["voice"]
    real_tier = synth["tier"]
    el_alignment = synth["alignment"]
    vo_engine = synth["vo_engine"]
    vo_fallback = synth["vo_fallback"]
    vo_fallback_reason = synth["fallback_reason"]
    # Normalize: audio sits beside the alignment json as voiceover.mp3.
    audio_final = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                               "voiceover.mp3")
    if os.path.abspath(audio_path) != os.path.abspath(audio_final) \
            and os.path.exists(audio_path):
        os.replace(audio_path, audio_final)
        audio_path = audio_final
    elif os.path.exists(audio_path):
        audio_path = audio_final

    # Word timestamps: if ElevenLabs ran it returned char/word alignment directly
    # (no whisper needed); on the free fallback (the common case while ElevenLabs
    # is out of credits) whisper-cli derives the timings from the edge-tts audio.
    if vo_engine == "elevenlabs" and el_alignment is not None:
        hyp_words = parse_elevenlabs_alignment(el_alignment)
    else:
        wfn = whisper_fn or whisper_words
        hyp_words = wfn(audio_path)

    scene_for = map_words_to_beats(hyp_words, owners, script_tokens)
    words = []
    for hw, sid in zip(hyp_words, scene_for):
        words.append({"word": hw["word"], "start_s": hw["start_s"],
                      "end_s": hw["end_s"], "beat_scene_id": sid})

    total = round(max((w["end_s"] for w in words), default=0.0), 3)
    out_beats = _beats_from_words(words, clean_beats)
    return {
        "audio_path": audio_path,
        "lang": lang,
        "voice": resolved_voice,
        "tier": real_tier,
        # VO ENGINE PROVENANCE (run artifact, NOT a plan key): which engine
        # actually produced this audio and whether it FELL BACK from the default
        # ElevenLabs to free edge-tts. These live on vo_alignment.json — a per-run
        # artifact written beside the audio — so they are 100% safe re:
        # plan_schema.allowed_top (they never touch the plan top level).
        "vo_engine": vo_engine,            # "elevenlabs" | "edge-tts"
        "vo_fallback": vo_fallback,        # True when ElevenLabs was tried but failed
        "vo_fallback_reason": vo_fallback_reason,  # WHY it fell back (for diagnosis)
        "total_duration_s": total,
        "words": words,
        "beats": out_beats,
    }


def main(argv=None):
    import argparse

    p = argparse.ArgumentParser(description="VO word-alignment (align_vo)")
    p.add_argument("--beats-file", required=True, help="JSON: [{scene_id, text}]")
    p.add_argument("--out", required=True, help="output vo_alignment.json path")
    p.add_argument("--tier", default="free", choices=["free", "premium"])
    p.add_argument("--lang", default="en")
    p.add_argument("--voice", default=None)
    args = p.parse_args(argv)

    with open(args.beats_file) as f:
        beats = json.load(f)
    if not isinstance(beats, list):
        raise AlignError("beats-file must be a JSON array of {scene_id, text}")

    result = align(beats, out_path=args.out, tier=args.tier, lang=args.lang,
                   voice=args.voice)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print("align_vo: wrote %s (%d words, %d beats, %.2fs)"
          % (args.out, len(result["words"]), len(result["beats"]),
             result["total_duration_s"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
