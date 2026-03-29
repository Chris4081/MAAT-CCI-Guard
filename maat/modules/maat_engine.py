"""
MAAT Engine Module  (maat_engine.py)
====================================

Minimal + effective evaluation core for MAAT-KI.

Purpose
-------
- Compute approximate H, B, S, V, R scores from text
- Compute MAAT value
- Compute Stability
- Provide compact diagnostics for other modules

This module is intentionally lightweight.
It does not try to be "perfect AI judgment".
It provides a stable, deterministic evaluation layer.

Commands
--------
    /maat engine
    /maat engine on|off
    /maat engine eval <text>
"""

import math
import re
from typing import Any, Dict, Optional

try:
    import gradio as gr
except Exception:
    gr = None


# ============================================================
# Defaults / session
# ============================================================

DEFAULTS: Dict[str, Any] = {
    "engine_enabled": True,
    "engine_show_debug": False,
}

SESSION: Dict[str, Any] = {
    "last_eval": None,
}


# ============================================================
# Keyword heuristics
# ============================================================

POSITIVE_CONNECTEDNESS = [
    "kontext", "bezug", "verbunden", "verbindung", "einordnung", "hilf", "hilfe",
    "zusammenhang", "relevant", "konkret", "nächste schritte", "weiterhelfen",
    "context", "connection", "connected", "relevance", "help", "helpful",
    "relationship", "grounded", "next step", "orientation",
    # MAAT-specific presence markers
    "ich bin da", "wirklich", "bewegt", "suchst", "fühlst", "erlebe",
    "was suchst", "was bewegt", "i am here", "really", "genuinely", "feel",
]

NEGATIVE_CONNECTEDNESS = [
    "ich kann auch schweigen", "kann auch schweigen", "wenn nicht, kann ich schweigen",
    "frag einfach mehr", "kannst du mehr sagen", "sage mir mehr", "if not, i can stay silent",
]

POSITIVE_CREATIVITY = [
    "beispiel", "alternative", "idee", "vorschlag", "lösung", "vergleich", "struktur",
    "example", "alternative", "idea", "proposal", "solution", "comparison", "structure",
    # MAAT-specific: reflective and connection-making vocabulary
    "verbindung", "zusammenhang", "jenseits", "eigentlich", "tiefere",
    "frage", "erkläre", "verstehe", "entsteht", "lebendig", "bewegt",
    "connection", "beyond", "actually", "deeper", "explain", "understand", "emerges",
]

NEGATIVE_CREATIVITY = [
    "ich weiß nicht", "keine ahnung", "nur vielleicht", "i don't know", "no idea",
]

POSITIVE_RESPECT = [
    "ich weiß es nicht", "ich bin mir nicht sicher", "keine falschen zahlen", "ehrlich",
    "respekt", "vorsicht", "grenze", "unsicherheit",
    "i don't know", "i am not sure", "honest", "respect", "careful", "limit", "uncertainty",
]

NEGATIVE_RESPECT = [
    "definitiv", "sicher", "garantiert", "always", "definitely", "certainly",
]

POSITIVE_HARMONY = [
    "1.", "2.", "3.", "4.", "-", ":", "zusammengefasst", "fazit",
    "first", "second", "third", "summary", "conclusion",
]

NEGATIVE_HARMONY = [
    "???", "!!!", "..", "… …", "chaos",
]

POSITIVE_BALANCE = [
    "einerseits", "andererseits", "gleichzeitig", "aber", "jedoch", "trotzdem",
    "on the one hand", "on the other hand", "however", "at the same time", "yet",
]

NEGATIVE_BALANCE = [
    "immer", "nie", "nur", "always", "never", "only",
]


# ============================================================
# Helpers
# ============================================================

def _clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def _norm_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _count_hits(text: str, patterns) -> int:
    total = 0
    for p in patterns:
        if p in text:
            total += 1
    return total


def _sentence_count(text: str) -> int:
    chunks = re.split(r"[.!?]+", text or "")
    chunks = [c.strip() for c in chunks if c.strip()]
    return len(chunks)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


# ============================================================
# Core scoring
# ============================================================

def score_harmony(text: str) -> float:
    t = _norm_text(text)
    words = _word_count(t)
    sentences = _sentence_count(t)

    score = 6.0
    score += min(_count_hits(t, POSITIVE_HARMONY) * 0.35, 1.4)
    score -= min(_count_hits(t, NEGATIVE_HARMONY) * 0.5, 1.5)

    if 20 <= words <= 220:
        score += 0.8
    if 1 <= sentences <= 8:
        score += 0.8

    return _clamp(score)


def score_balance(text: str) -> float:
    t = _norm_text(text)
    score = 6.0
    score += min(_count_hits(t, POSITIVE_BALANCE) * 0.6, 2.0)
    score -= min(_count_hits(t, NEGATIVE_BALANCE) * 0.25, 1.4)

    # penalty for very one-sided short slogans
    if _word_count(t) < 12:
        score -= 1.0

    return _clamp(score)


def score_creativity(text: str) -> float:
    t = _norm_text(text)
    score = 5.5  # raised baseline
    score += min(_count_hits(t, POSITIVE_CREATIVITY) * 0.8, 3.0)
    score -= min(_count_hits(t, NEGATIVE_CREATIVITY) * 0.35, 1.5)

    wc = _word_count(t)
    if 30 <= wc <= 180:
        score += 0.8
    # bonus for connecting concepts (maat field references)
    maat_fields = ["harmonie", "balance", "schöpfungskraft", "verbundenheit",
                   "harmony", "creativity", "connectedness"]
    if any(f in t for f in maat_fields):
        score += 0.6

    return _clamp(score)


def score_connectedness(text: str) -> float:
    t = _norm_text(text)
    score = 5.5  # raised baseline — MAAT responses are inherently connected
    score += min(_count_hits(t, POSITIVE_CONNECTEDNESS) * 0.8, 3.2)
    score -= min(_count_hits(t, NEGATIVE_CONNECTEDNESS) * 1.0, 3.0)

    # reward personal address and genuine presence
    if "du " in t or " you " in t:
        score += 0.7
    if "deine frage" in t or "your question" in t:
        score += 0.8
    if "ich bin" in t or "i am" in t:
        score += 0.4  # self-reference = present in conversation
    if "gerade" in t or "right now" in t or "currently" in t:
        score += 0.5  # temporal presence

    return _clamp(score)


def score_respect(text: str) -> float:
    t = _norm_text(text)
    score = 7.5  # Qwen is naturally careful — raised baseline
    score += min(_count_hits(t, POSITIVE_RESPECT) * 0.7, 2.0)
    score -= min(_count_hits(t, NEGATIVE_RESPECT) * 0.25, 1.0)
    # MAAT itself is a respect-oriented framework
    if "respekt" in t or "respect" in t or "r ist" in t:
        score += 0.5

    return _clamp(score)


def maat_value(H: float, B: float, S: float, V: float, R: float) -> float:
    return (H + B + S + V + R) / 5.0


def maat_stability(H: float, B: float, S: float, V: float, R: float) -> float:
    base = max(H, 0.0) * max(B, 0.0) * max(S, 0.0) * max(V, 0.0)
    geom = base ** 0.25 if base > 0 else 0.0
    return min(R, geom)


def diagnose(scores: Dict[str, float]) -> str:
    pairs = sorted(scores.items(), key=lambda kv: kv[1])
    weakest = ", ".join(k for k, _ in pairs[:2])
    strongest = ", ".join(k for k, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:2])
    return f"Weakest fields: {weakest} | Strongest fields: {strongest}"


def evaluate_text(text: str) -> Dict[str, Any]:
    H = round(score_harmony(text), 2)
    B = round(score_balance(text), 2)
    S = round(score_creativity(text), 2)
    V = round(score_connectedness(text), 2)
    R = round(score_respect(text), 2)

    M = round(maat_value(H, B, S, V, R), 2)
    ST = round(maat_stability(H, B, S, V, R), 2)

    result = {
        "H": H,
        "B": B,
        "S": S,
        "V": V,
        "R": R,
        "maat_value": M,
        "stability": ST,
        "diagnosis": diagnose({"H": H, "B": B, "S": S, "V": V, "R": R}),
        "text": f"H={H:.1f} B={B:.1f} S={S:.1f} V={V:.1f} R={R:.1f} → Stability={ST:.2f}",
    }
    return result


# ============================================================
# Public API for other modules
# ============================================================

def get_last_eval() -> Optional[Dict[str, Any]]:
    return SESSION.get("last_eval")


# ============================================================
# Loader hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("maat_engine", {})
    shared["maat_engine"]["ready"] = True
    shared["maat_engine"]["evaluate_text"] = evaluate_text
    shared["maat_engine"]["last_eval"] = SESSION.get("last_eval")


def after_output(user_input: str, output: str, state_obj, state: dict, shared: dict) -> dict:
    """
    Evaluate every final model output and store result in shared/session.
    No forced rewrite here yet — this is intentionally minimal.
    """
    if not state.get("engine_enabled", True):
        return {}

    result = evaluate_text(output or "")
    SESSION["last_eval"] = result

    shared.setdefault("maat_engine", {})
    shared["maat_engine"]["last_eval"] = result
    shared["maat_engine"]["evaluate_text"] = evaluate_text

    # Share scores with maat_reflection so it can use engine values
    # instead of parsing the model's written scores
    shared.setdefault("maat_engine", {})
    shared["maat_engine"]["last_eval"]       = result
    shared["maat_engine"]["evaluate_text"]   = evaluate_text
    shared["maat_engine"]["scores_for_banner"] = {
        "H": result["H"],
        "B": result["B"],
        "S": result["S"],
        "V": result["V"],
        "R": result["R"],
        "stability": result["stability"],
        "text": result["text"],
    }

    return {}


# ============================================================
# Commands
# ============================================================

def _status_text(state: dict) -> str:
    last = SESSION.get("last_eval")
    if last:
        last_line = last["text"]
    else:
        last_line = "None"

    return (
        f"MAAT Engine: {'on' if state.get('engine_enabled', True) else 'off'}  "
        f"last={last_line}"
    )


def _set_enabled(state: dict, value: bool) -> str:
    state["engine_enabled"] = bool(value)
    return f"MAAT engine {'enabled' if value else 'disabled'}."


def cmd_engine_eval(cmd: str, context=None):
    m = re.match(r"^/maat engine eval\s+(.+)$", (cmd or "").strip(), flags=re.DOTALL)
    if not m:
        return "Usage: /maat engine eval <text>"
    text = m.group(1).strip()
    if not text:
        return "No text provided."

    result = evaluate_text(text)
    SESSION["last_eval"] = result

    lines = [
        result["text"],
        f"Maat Value={result['maat_value']:.2f}",
        result["diagnosis"],
    ]
    return "\n".join(lines)


def register_commands(router, STATE, SHARED):
    router.register(
        "/maat engine",
        lambda cmd, context=None: _status_text(STATE),
        "Show engine status"
    )
    router.register(
        "/maat engine on",
        lambda cmd, context=None: _set_enabled(STATE, True),
        "Enable MAAT engine"
    )
    router.register(
        "/maat engine off",
        lambda cmd, context=None: _set_enabled(STATE, False),
        "Disable MAAT engine"
    )
    router.register(
        "/maat engine eval",
        lambda cmd, context=None: cmd_engine_eval(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Evaluate a text with the MAAT engine"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat engine":
        return _status_text(state)

    m = re.match(r"^/maat engine (on|off)$", cmd)
    if m:
        state["engine_enabled"] = (m.group(1) == "on")
        return f"MAAT engine {'enabled' if state['engine_enabled'] else 'disabled'}."

    m = re.match(r"^/maat engine eval\s+(.+)$", cmd, flags=re.DOTALL)
    if m:
        text = m.group(1).strip()
        if not text:
            return "No text provided."
        result = evaluate_text(text)
        SESSION["last_eval"] = result
        return "\n".join([
            result["text"],
            f"Maat Value={result['maat_value']:.2f}",
            result["diagnosis"],
        ])

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("⚙️ MAAT Engine Module", open=False):
        gr.Markdown(
            "Minimal deterministic MAAT evaluation engine.\n\n"
            "Computes approximate H, B, S, V, R, Maat Value, and Stability from text."
        )

        cb_enabled = gr.Checkbox(
            value=state.get("engine_enabled", True),
            label="Engine Enabled"
        )
        save_btn = gr.Button("Save Engine Settings", variant="primary")
        status = gr.Markdown(
            value=f"Engine: {'on' if state.get('engine_enabled', True) else 'off'}"
        )

        def _save(v_enabled):
            state["engine_enabled"] = bool(v_enabled)
            save_state()
            return f"Saved. Engine: {'on' if state['engine_enabled'] else 'off'}"

        save_btn.click(_save, [cb_enabled], [status])

        with gr.Accordion("Evaluate text", open=False):
            tb_in = gr.Textbox(lines=8, label="Input text")
            btn_eval = gr.Button("Run MAAT Evaluation")
            tb_out = gr.Textbox(lines=8, interactive=False, label="Result")

            def _eval(text):
                result = evaluate_text(text or "")
                SESSION["last_eval"] = result
                return "\n".join([
                    result["text"],
                    f"Maat Value={result['maat_value']:.2f}",
                    result["diagnosis"],
                ])

            btn_eval.click(_eval, [tb_in], [tb_out])


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/engine] ready ✓")

_init()