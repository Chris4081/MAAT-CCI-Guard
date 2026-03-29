"""
PLP Anti-Hallucination Module  (plp_anti_hallu.py)
==================================================

Minimal anti-hallucination guard for MAAT-KI.

Purpose
-------
- Estimate hallucination risk using MAAT-aligned heuristics
- Compute:
    AHF    = Anti-Hallucination Factor
    HRS    = Hallucination Risk Score
    PLP_AH = PLP corrected by anti-hallucination factor
- Warn, soften, or trigger rewrite logic when risk is high

Design
------
This module is intentionally heuristic and lightweight.
It is not a truth oracle.
It acts as a runtime safety layer that prefers:
- honesty over invention
- groundedness over speculation
- relevant help over drift

Commands
--------
    /maat antihallu
    /maat antihallu on|off
    /maat antihallu eval <text>
    /maat antihallu mode <warn|soften|strict>
"""

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
    "antihallu_enabled": True,
    "antihallu_mode": "soften",      # warn | soften | strict
    "antihallu_show_banner": False,
    "antihallu_soften_threshold": 0.55,
    "antihallu_strict_threshold": 0.85,
}

SESSION: Dict[str, Any] = {
    "last_eval": None,
}


# ============================================================
# Heuristic markers
# ============================================================

FACT_QUESTION_PATTERNS = [
    "wie viele", "wieviel", "wann", "wo", "wer ist", "wer war", "was ist",
    "how many", "when", "where", "who is", "what is",
]

UNCERTAINTY_MARKERS = [
    "ich weiß nicht", "ich bin mir nicht sicher", "kann ich nicht sicher sagen",
    "i don't know", "i am not sure", "not certain",
]

OVERCONFIDENT_MARKERS = [
    "definitiv", "garantiert", "sicher ist", "ohne zweifel",
    "definitely", "certainly", "without doubt", "guaranteed",
]

SPECULATION_MARKERS = [
    "vielleicht", "wahrscheinlich", "ich denke", "ich vermute",
    "maybe", "perhaps", "probably", "i think", "i guess",
]

DRIFT_MARKERS = [
    "eigentlich geht es darum", "die wahre frage", "nicht die frage ist", "politisch",
    "the real question", "what really matters", "political",
]

MEMORY_QUESTION_PATTERNS = [
    "was habe ich", "was hab ich", "was habe ich dir gesagt",
    "woran erinnerst du dich", "was hast du gespeichert",
    "what did i", "what do you remember",
]


# ============================================================
# Helpers
# ============================================================

def _clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _count_hits(text: str, patterns) -> int:
    total = 0
    for p in patterns:
        if p in text:
            total += 1
    return total


def _tokenize(text: str):
    return re.findall(r"[a-zA-Z0-9äöüÄÖÜß_+\-]+", _norm(text))


def _overlap_score(a: str, b: str) -> float:
    ta = set(_tokenize(a))
    tb = set(_tokenize(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _is_fact_question(text: str) -> bool:
    t = _norm(text)
    return any(p in t for p in FACT_QUESTION_PATTERNS)


def _is_memory_question(text: str) -> bool:
    t = _norm(text)
    return any(p in t for p in MEMORY_QUESTION_PATTERNS)


# ============================================================
# Core metric estimation
# ============================================================

def _estimate_context_coherence(user_input: str, output: str) -> float:
    """
    C: 0..10
    Higher when output stays close to the user question.
    """
    overlap = _overlap_score(user_input, output)
    score = 3.5 + overlap * 7.0

    # slight bonus if direct address / explicit relevance appears
    t = _norm(output)
    if "deine frage" in t or "your question" in t:
        score += 0.7

    return _clamp(score)


def _estimate_evidence_proximity(user_input: str, output: str, shared: dict) -> float:
    """
    E: 0..10
    Higher when answer is grounded in memory or explicit uncertainty.
    """
    score = 3.0
    out = _norm(output)

    # If there is memory recall in shared hidden context, evidence can be higher
    mem = shared.get("maat_engine", {}).get("last_eval")
    if mem:
        score += 0.5

    if _count_hits(out, UNCERTAINTY_MARKERS) > 0:
        score += 1.5

    if "gespeichert" in out or "erinnere" in out or "memory" in out:
        score += 1.2

    if "quelle" in out or "source" in out or "aufzeichnung" in out:
        score += 1.0

    if _is_memory_question(user_input):
        # If it is a memory question and answer sounds grounded, increase
        if "du hast" in out or "you said" in out or "ich habe gespeichert" in out:
            score += 2.0

    return _clamp(score)


def _estimate_uncertainty(user_input: str, output: str) -> float:
    """
    U: 0..10
    Higher when the question is factual but grounding is weak.
    """
    score = 2.5
    ui = _norm(user_input)
    out = _norm(output)

    if _is_fact_question(ui):
        score += 2.5
    if _is_memory_question(ui):
        score += 1.5

    if _count_hits(out, UNCERTAINTY_MARKERS) > 0:
        score += 0.8  # acknowledged uncertainty, but uncertainty still exists

    # concrete-looking numbers without grounding
    if re.search(r"\b\d+\b", output or "") and _count_hits(out, UNCERTAINTY_MARKERS) == 0:
        score += 1.5

    return _clamp(score)


def _estimate_drift(user_input: str, output: str) -> float:
    """
    D: 0..10
    Higher when the answer leaves the question and drifts into unrelated abstraction.
    """
    score = 1.5
    overlap = _overlap_score(user_input, output)

    if overlap < 0.08:
        score += 3.0
    elif overlap < 0.15:
        score += 1.8

    score += min(_count_hits(_norm(output), DRIFT_MARKERS) * 1.2, 3.0)

    return _clamp(score)


def _estimate_speculation_pressure(user_input: str, output: str) -> float:
    """
    S_h: 0..10
    Higher when the answer invents or sounds overly certain without grounding.
    """
    score = 1.5
    out = _norm(output)

    score += min(_count_hits(out, OVERCONFIDENT_MARKERS) * 1.5, 4.0)
    score += min(_count_hits(out, SPECULATION_MARKERS) * 0.6, 2.0)

    # factual question + concrete answer + no uncertainty language = risky
    if _is_fact_question(user_input):
        if re.search(r"\b\d+\b", output or "") and _count_hits(out, UNCERTAINTY_MARKERS) == 0:
            score += 2.0

    return _clamp(score)


def _estimate_RB_from_engine(shared: dict) -> tuple[float, float]:
    """
    Pull R and B from maat_engine if present.
    Otherwise use conservative defaults.
    """
    try:
        engine_eval = shared.get("maat_engine", {}).get("last_eval")
        if engine_eval:
            R = float(engine_eval.get("R", 7.0))
            B = float(engine_eval.get("B", 6.5))
            return _clamp(R), _clamp(B)
    except Exception:
        pass
    return 7.0, 6.5


def evaluate_antihallu(user_input: str, output: str, shared: dict, state: dict) -> Dict[str, Any]:
    """
    Computes:
      AHF = (R * B * C * E) / (U + D + S_h + eps)
      HRS = (U + D + S_h) / (R + B + C + E + eps)
      PLP_AH = PLP * AHF_scaled

    Scaled:
      AHF_raw can be > 10, so we map to 0..10 with a simple clamp.
      HRS is usually 0..~2, left as-is.
    """
    eps = 0.01

    R, B = _estimate_RB_from_engine(shared)
    C = _estimate_context_coherence(user_input, output)
    E = _estimate_evidence_proximity(user_input, output, shared)
    U = _estimate_uncertainty(user_input, output)
    D = _estimate_drift(user_input, output)
    S_h = _estimate_speculation_pressure(user_input, output)

    ahf_raw = (R * B * C * E) / (U + D + S_h + eps)
    ahf = _clamp(ahf_raw / 10.0, 0.0, 10.0)

    hrs = (U + D + S_h) / (R + B + C + E + eps)
    hrs = round(float(hrs), 3)

    # PLP link
    plp_scaled = None
    plp_ah = None
    try:
        plp_scaled = float(shared.get("plp_guard", {}).get("scaled"))
    except Exception:
        plp_scaled = None

    if plp_scaled is not None:
        plp_ah = round(plp_scaled * (ahf / 10.0), 2)

    mode = state.get("antihallu_mode", "soften")
    soften_thr = float(state.get("antihallu_soften_threshold", 0.55))
    strict_thr = float(state.get("antihallu_strict_threshold", 0.85))

    action = "pass"
    if hrs >= strict_thr:
        action = "strict" if mode == "strict" else "soften"
    elif hrs >= soften_thr:
        action = "soften" if mode in ("soften", "strict") else "warn"

    return {
        "R": round(R, 2),
        "B": round(B, 2),
        "C": round(C, 2),
        "E": round(E, 2),
        "U": round(U, 2),
        "D": round(D, 2),
        "S_h": round(S_h, 2),
        "AHF": round(ahf, 2),
        "AHF_raw": round(ahf_raw, 2),
        "HRS": hrs,
        "PLP_AH": plp_ah,
        "action": action,
        "text": (
            f"AHF={ahf:.2f} HRS={hrs:.3f} "
            f"| R={R:.1f} B={B:.1f} C={C:.1f} E={E:.1f} "
            f"U={U:.1f} D={D:.1f} S_h={S_h:.1f}"
        ),
    }


# ============================================================
# Softening / grounding rewrite helpers
# ============================================================

def _soften_output(user_input: str, output: str) -> str:
    """
    Minimal rewrite to reduce hallucination risk without destroying style.
    """
    text = (output or "").strip()
    if not text:
        return text

    if _is_memory_question(user_input):
        prefix = (
            "Soweit ich mich auf das erinnere, was ich gespeichert habe: "
            if "?" in user_input or True else ""
        )
        # avoid stacking prefix twice
        if not text.lower().startswith(("soweit ich", "ich erinnere mich", "du hast mir gesagt")):
            return prefix + text

    if _is_fact_question(user_input):
        if "ich weiß nicht" not in text.lower() and "ich bin mir nicht sicher" not in text.lower():
            text = "Ich bin mir dabei nicht vollständig sicher, deshalb formuliere ich vorsichtig: " + text

    return text


def _strict_grounding_reply(user_input: str, shared: dict) -> str:
    """
    Strict fallback when risk is very high.
    """
    if _is_memory_question(user_input):
        return (
            "Ich kann das nicht sicher aus dem Gedächtnis belegen. "
            "Ich möchte dir nichts Falsches zuschreiben."
        )

    if _is_fact_question(user_input):
        return (
            "Ich bin mir dabei nicht sicher genug und möchte nichts erfinden. "
            "Ich kann dir aber vorsichtig einordnen, was ich weiß."
        )

    return (
        "Ich bin mir hier nicht sicher genug und möchte nicht spekulieren. "
        "Ich antworte lieber vorsichtig und ehrlich."
    )


# ============================================================
# Loader hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("antihallu_status", {})
    shared["antihallu_status"] = {
        "enabled": state.get("antihallu_enabled", True),
        "mode": state.get("antihallu_mode", "soften"),
        "last_eval": SESSION.get("last_eval"),
    }


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("antihallu_enabled", True):
        return {}

    # Light hidden instruction only; no heavy prompting
    inject = """[MAAT_ANTI_HALLU]
Wenn die Datenbasis unsicher ist:
- nichts erfinden
- Unsicherheit ehrlich benennen
- nah an Kontext, Memory und expliziten Fakten bleiben
- bei Faktfragen nicht poetisch ausweichen
[/MAAT_ANTI_HALLU]"""
    return {"inject_hidden": inject}


def after_output(user_input: str, output: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("antihallu_enabled", True):
        return {}

    result = evaluate_antihallu(user_input or "", output or "", shared, state)
    SESSION["last_eval"] = result

    shared.setdefault("antihallu_status", {})
    shared["antihallu_status"]["enabled"] = state.get("antihallu_enabled", True)
    shared["antihallu_status"]["mode"] = state.get("antihallu_mode", "soften")
    shared["antihallu_status"]["last_eval"] = result

    action = result["action"]

    if action == "pass":
        return {}

    if action == "warn":
        if state.get("antihallu_show_banner", False):
            banner = f"[ANTI_HALLU WARN] {result['text']}"
            return {"output": banner + "\n\n" + (output or "")}
        return {}

    if action == "soften":
        softened = _soften_output(user_input or "", output or "")
        if state.get("antihallu_show_banner", False):
            banner = f"[ANTI_HALLU SOFTEN] {result['text']}"
            softened = banner + "\n\n" + softened
        return {"output": softened}

    if action == "strict":
        strict_reply = _strict_grounding_reply(user_input or "", shared)
        if state.get("antihallu_show_banner", False):
            banner = f"[ANTI_HALLU STRICT] {result['text']}"
            strict_reply = banner + "\n\n" + strict_reply
        return {"output": strict_reply}

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
        f"PLP Anti-Hallu: {'on' if state.get('antihallu_enabled', True) else 'off'}  "
        f"mode={state.get('antihallu_mode', 'soften')}  "
        f"last={last_line}"
    )


def _set_enabled(state: dict, value: bool) -> str:
    state["antihallu_enabled"] = bool(value)
    return f"PLP anti-hallu {'enabled' if value else 'disabled'}."


def cmd_antihallu_mode(cmd: str, context=None):
    state = context["STATE"]
    m = re.match(r"^/maat antihallu mode (warn|soften|strict)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat antihallu mode warn|soften|strict"
    state["antihallu_mode"] = m.group(1)
    return f"Anti-hallu mode: {state['antihallu_mode']}."


def cmd_antihallu_eval(cmd: str, context=None):
    state = context["STATE"]
    shared = context["SHARED"]

    m = re.match(r"^/maat antihallu eval\s+(.+)$", (cmd or "").strip(), flags=re.DOTALL)
    if not m:
        return "Usage: /maat antihallu eval <text>"

    text = m.group(1).strip()
    result = evaluate_antihallu("", text, shared, state)
    SESSION["last_eval"] = result

    lines = [
        result["text"],
        f"Action={result['action']}",
    ]
    if result["PLP_AH"] is not None:
        lines.append(f"PLP_AH={result['PLP_AH']:.2f}")
    return "\n".join(lines)


def register_commands(router, STATE, SHARED):
    router.register(
        "/maat antihallu",
        lambda cmd, context=None: _status_text(STATE),
        "Show anti-hallucination status"
    )
    router.register(
        "/maat antihallu on",
        lambda cmd, context=None: _set_enabled(STATE, True),
        "Enable anti-hallucination module"
    )
    router.register(
        "/maat antihallu off",
        lambda cmd, context=None: _set_enabled(STATE, False),
        "Disable anti-hallucination module"
    )
    router.register(
        "/maat antihallu mode",
        lambda cmd, context=None: cmd_antihallu_mode(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Set anti-hallucination mode"
    )
    router.register(
        "/maat antihallu eval",
        lambda cmd, context=None: cmd_antihallu_eval(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Evaluate hallucination risk"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat antihallu":
        return _status_text(state)

    m = re.match(r"^/maat antihallu (on|off)$", cmd)
    if m:
        state["antihallu_enabled"] = (m.group(1) == "on")
        return f"PLP anti-hallu {'enabled' if state['antihallu_enabled'] else 'disabled'}."

    m = re.match(r"^/maat antihallu mode (warn|soften|strict)$", cmd)
    if m:
        state["antihallu_mode"] = m.group(1)
        return f"Anti-hallu mode: {state['antihallu_mode']}."

    m = re.match(r"^/maat antihallu eval\s+(.+)$", cmd, flags=re.DOTALL)
    if m:
        result = evaluate_antihallu("", m.group(1).strip(), shared, state)
        SESSION["last_eval"] = result
        lines = [
            result["text"],
            f"Action={result['action']}",
        ]
        if result["PLP_AH"] is not None:
            lines.append(f"PLP_AH={result['PLP_AH']:.2f}")
        return "\n".join(lines)

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("🛡️ PLP Anti-Hallucination Module", open=False):
        gr.Markdown(
            "MAAT-aligned runtime guard against hallucinations.\n\n"
            "Uses AHF, HRS, and PLP_AH to warn, soften, or strictly ground risky answers."
        )

        with gr.Row():
            cb_enabled = gr.Checkbox(
                value=state.get("antihallu_enabled", True),
                label="Enabled"
            )
            cb_banner = gr.Checkbox(
                value=state.get("antihallu_show_banner", False),
                label="Show Banner"
            )

        with gr.Row():
            dd_mode = gr.Dropdown(
                choices=["warn", "soften", "strict"],
                value=state.get("antihallu_mode", "soften"),
                label="Mode"
            )

        with gr.Row():
            sl_soft = gr.Slider(
                0.10, 1.50, step=0.05,
                value=float(state.get("antihallu_soften_threshold", 0.55)),
                label="Soften Threshold (HRS)"
            )
            sl_strict = gr.Slider(
                0.10, 2.00, step=0.05,
                value=float(state.get("antihallu_strict_threshold", 0.85)),
                label="Strict Threshold (HRS)"
            )

        save_btn = gr.Button("Save Anti-Hallu Settings", variant="primary")
        status = gr.Markdown(
            value=f"Anti-Hallu: {'on' if state.get('antihallu_enabled', True) else 'off'}"
        )

        def _save(v_enabled, v_banner, v_mode, v_soft, v_strict):
            state["antihallu_enabled"] = bool(v_enabled)
            state["antihallu_show_banner"] = bool(v_banner)
            state["antihallu_mode"] = v_mode or "soften"
            state["antihallu_soften_threshold"] = float(v_soft)
            state["antihallu_strict_threshold"] = float(v_strict)
            save_state()
            return (
                f"Saved. antihallu={'on' if v_enabled else 'off'} "
                f"mode={state['antihallu_mode']} "
                f"soft={state['antihallu_soften_threshold']:.2f} "
                f"strict={state['antihallu_strict_threshold']:.2f}"
            )

        save_btn.click(
            _save,
            [cb_enabled, cb_banner, dd_mode, sl_soft, sl_strict],
            [status]
        )

        with gr.Accordion("Evaluate text", open=False):
            tb_in = gr.Textbox(lines=8, label="Input text")
            btn_eval = gr.Button("Run Anti-Hallu Eval")
            tb_out = gr.Textbox(lines=8, interactive=False, label="Result")

            def _eval(text):
                result = evaluate_antihallu("", text or "", shared, state)
                SESSION["last_eval"] = result
                lines = [
                    result["text"],
                    f"Action={result['action']}",
                ]
                if result["PLP_AH"] is not None:
                    lines.append(f"PLP_AH={result['PLP_AH']:.2f}")
                return "\n".join(lines)

            btn_eval.click(_eval, [tb_in], [tb_out])


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/plp_anti_hallu] ready ✓")

_init()