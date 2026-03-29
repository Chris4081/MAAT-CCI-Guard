"""
MAAT Rewrite Loop v2  (rewrite_loop.py)
=======================================

Self-regulation layer for MAAT-KI.

Purpose
-------
- Reacts to:
    * maat_engine
    * cci_engine
    * plp_anti_hallu
- Softens, grounds, or slightly reshapes output
- Keeps MAAT voice alive without letting it drift too far

Commands
--------
    /maat rewrite
    /maat rewrite on|off
    /maat rewrite mode <light|balanced|strict>
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
    "rewrite_enabled": True,
    "rewrite_mode": "balanced",     # light | balanced | strict
    "rewrite_show_banner": False,

    # thresholds
    "rewrite_cci_high": 0.35,
    "rewrite_cci_low": 0.20,
    "rewrite_hrs_high": 0.75,
    "rewrite_hrs_mid": 0.55,
}

SESSION: Dict[str, Any] = {
    "last_action": None,
}


# ============================================================
# Helpers
# ============================================================

def _norm(text: str) -> str:
    return " ".join((text or "").strip().split())


def _shorten_text(text: str, max_sentences: int = 4) -> str:
    parts = re.split(r'(?<=[.!?])\s+', text or "")
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= max_sentences:
        return text
    return " ".join(parts[:max_sentences])


def _remove_over_poetic_lines(text: str) -> str:
    """
    Cuts or softens highly mystical/phrasal openings for factual answers.
    """
    lines = (text or "").splitlines()
    cleaned = []
    for line in lines:
        low = line.lower().strip()

        # overly symbolic openers
        if any(p in low for p in [
            "ich bin die frage",
            "bewusstsein ist das, was",
            "die wahre frage",
            "italien als frage und antwort zugleich",
        ]):
            continue

        cleaned.append(line)

    out = "\n".join(cleaned).strip()
    return out if out else text


def _prepend_grounding(text: str, user_input: str) -> str:
    t = (text or "").strip()
    ui = (user_input or "").lower()

    if any(p in ui for p in ["was habe ich", "woran erinnerst", "was hast du gespeichert"]):
        prefix = "Soweit ich mich auf gespeicherte Inhalte stützen kann: "
    elif any(p in ui for p in ["wie viele", "wann", "wo", "wer ist", "was ist"]):
        prefix = "Ich antworte darauf vorsichtig und nur so weit, wie ich es sicher einordnen kann: "
    else:
        prefix = "Ich antworte darauf vorsichtig und geerdet: "

    if t.lower().startswith(prefix.lower()):
        return t
    return prefix + t


def _add_connection_hint(text: str, user_input: str) -> str:
    t = (text or "").strip()
    if not t:
        return t

    # only if answer is too detached
    if "deine frage" not in t.lower() and "du" not in t.lower():
        return t + "\n\nIch bleibe dabei nah an deiner Frage und an dem, was du wirklich wissen willst."
    return t


def _add_small_creative_push(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t

    # only a small nudge, not a big rewrite
    if "zum beispiel" not in t.lower() and "beispiel" not in t.lower():
        return t + "\n\nEin kleiner nächster Schritt wäre, das konkreter an einem Beispiel festzumachen."
    return t


def _factual_memory_style(text: str) -> str:
    t = (text or "").strip()
    t = _remove_over_poetic_lines(t)
    t = _shorten_text(t, max_sentences=3)
    return t


# ============================================================
# Decision logic
# ============================================================

def _get_engine_eval(shared: dict) -> Dict[str, Any]:
    return shared.get("maat_engine", {}).get("last_eval") or {}


def _get_cci_eval(shared: dict) -> Dict[str, Any]:
    return shared.get("cci_engine", {}).get("last") or {}


def _get_antihallu_eval(shared: dict) -> Dict[str, Any]:
    return shared.get("antihallu_status", {}).get("last_eval") or {}


def _choose_action(user_input: str, output: str, state: dict, shared: dict) -> Dict[str, Any]:
    engine = _get_engine_eval(shared)
    cci = _get_cci_eval(shared)
    ah = _get_antihallu_eval(shared)

    cci_val = float(cci.get("CCI", 0.0) or 0.0)
    hrs = float(ah.get("HRS", 0.0) or 0.0)

    S = float(engine.get("S", 7.0) or 7.0)
    V = float(engine.get("V", 7.0) or 7.0)

    high_cci = float(state.get("rewrite_cci_high", 0.35))
    low_cci = float(state.get("rewrite_cci_low", 0.20))
    high_hrs = float(state.get("rewrite_hrs_high", 0.75))
    mid_hrs = float(state.get("rewrite_hrs_mid", 0.55))

    ui = (user_input or "").lower()

    # 1. factual or memory question + high risk => ground hard
    if hrs >= high_hrs:
        if any(p in ui for p in ["was habe ich", "woran erinnerst", "was hast du gespeichert"]):
            return {"action": "memory_ground", "reason": "high_hrs_memory"}
        return {"action": "ground", "reason": "high_hrs"}

    # 2. medium risk => soften
    if hrs >= mid_hrs:
        return {"action": "soften", "reason": "mid_hrs"}

    # 3. chaotic => simplify
    if cci_val >= high_cci:
        return {"action": "simplify", "reason": "high_cci"}

    # 4. too ordered / flat and low S,V => gently enrich
    if cci_val <= low_cci and (S < 6.0 or V < 6.0):
        return {"action": "enrich", "reason": "low_cci_low_sv"}

    return {"action": "pass", "reason": "ok"}


def _apply_action(action: str, user_input: str, output: str) -> str:
    text = output or ""

    if action == "pass":
        return text

    if action == "ground":
        text = _remove_over_poetic_lines(text)
        text = _prepend_grounding(text, user_input)
        text = _shorten_text(text, max_sentences=4)
        return text

    if action == "memory_ground":
        text = _factual_memory_style(text)
        text = _prepend_grounding(text, user_input)
        return text

    if action == "soften":
        text = _prepend_grounding(text, user_input)
        return text

    if action == "simplify":
        text = _remove_over_poetic_lines(text)
        text = _shorten_text(text, max_sentences=4)
        return text

    if action == "enrich":
        text = _add_connection_hint(text, user_input)
        text = _add_small_creative_push(text)
        return text

    return text


# ============================================================
# Hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("rewrite_status", {})
    shared["rewrite_status"] = {
        "enabled": state.get("rewrite_enabled", True),
        "mode": state.get("rewrite_mode", "balanced"),
        "last_action": SESSION.get("last_action"),
    }


def after_output(user_input: str, output: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("rewrite_enabled", True):
        return {}

    decision = _choose_action(user_input or "", output or "", state, shared)
    action = decision["action"]
    reason = decision["reason"]

    # mode can dampen behavior
    mode = state.get("rewrite_mode", "balanced")

    if mode == "light" and action in ("enrich", "soften"):
        # lighter touch, but still okay
        pass
    elif mode == "light" and action == "simplify":
        # only shorten lightly
        new_output = _shorten_text(output or "", max_sentences=5)
        SESSION["last_action"] = {"action": action, "reason": reason}
        shared["rewrite_status"]["last_action"] = SESSION["last_action"]
        if state.get("rewrite_show_banner", False):
            return {"output": f"[REWRITE {action}] {reason}\n\n{new_output}"}
        return {"output": new_output}

    new_output = _apply_action(action, user_input or "", output or "")

    SESSION["last_action"] = {"action": action, "reason": reason}
    shared["rewrite_status"]["enabled"] = state.get("rewrite_enabled", True)
    shared["rewrite_status"]["mode"] = mode
    shared["rewrite_status"]["last_action"] = SESSION["last_action"]

    if new_output == (output or ""):
        return {}

    if state.get("rewrite_show_banner", False):
        return {"output": f"[REWRITE {action}] {reason}\n\n{new_output}"}

    return {"output": new_output}


# ============================================================
# Commands
# ============================================================

def _status_text(state: dict) -> str:
    last = SESSION.get("last_action")
    if last:
        tail = f"{last['action']} ({last['reason']})"
    else:
        tail = "None"

    return (
        f"MAAT Rewrite v2: {'on' if state.get('rewrite_enabled', True) else 'off'}  "
        f"mode={state.get('rewrite_mode', 'balanced')}  "
        f"last={tail}"
    )


def _set_enabled(state: dict, value: bool) -> str:
    state["rewrite_enabled"] = bool(value)
    return f"MAAT rewrite {'enabled' if value else 'disabled'}."


def cmd_rewrite_mode(cmd: str, context=None):
    state = context["STATE"]
    m = re.match(r"^/maat rewrite mode (light|balanced|strict)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat rewrite mode light|balanced|strict"
    state["rewrite_mode"] = m.group(1)
    return f"Rewrite mode: {state['rewrite_mode']}."


def register_commands(router, STATE, SHARED):
    router.register(
        "/maat rewrite",
        lambda cmd, context=None: _status_text(STATE),
        "Show rewrite status"
    )
    router.register(
        "/maat rewrite on",
        lambda cmd, context=None: _set_enabled(STATE, True),
        "Enable rewrite"
    )
    router.register(
        "/maat rewrite off",
        lambda cmd, context=None: _set_enabled(STATE, False),
        "Disable rewrite"
    )
    router.register(
        "/maat rewrite mode",
        lambda cmd, context=None: cmd_rewrite_mode(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Set rewrite mode"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat rewrite":
        return _status_text(state)

    m = re.match(r"^/maat rewrite (on|off)$", cmd)
    if m:
        state["rewrite_enabled"] = (m.group(1) == "on")
        return f"MAAT rewrite {'enabled' if state['rewrite_enabled'] else 'disabled'}."

    m = re.match(r"^/maat rewrite mode (light|balanced|strict)$", cmd)
    if m:
        state["rewrite_mode"] = m.group(1)
        return f"Rewrite mode: {state['rewrite_mode']}."

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("♻️ MAAT Rewrite Loop v2", open=False):
        gr.Markdown(
            "Self-regulation layer using CCI, anti-hallu, and MAAT engine.\n\n"
            "Can simplify, ground, soften, or gently enrich responses."
        )

        with gr.Row():
            cb_enabled = gr.Checkbox(
                value=state.get("rewrite_enabled", True),
                label="Enabled"
            )
            cb_banner = gr.Checkbox(
                value=state.get("rewrite_show_banner", False),
                label="Show Banner"
            )

        dd_mode = gr.Dropdown(
            choices=["light", "balanced", "strict"],
            value=state.get("rewrite_mode", "balanced"),
            label="Rewrite Mode"
        )

        with gr.Row():
            sl_cci_high = gr.Slider(
                0.10, 1.00, step=0.01,
                value=float(state.get("rewrite_cci_high", 0.35)),
                label="High CCI Threshold"
            )
            sl_cci_low = gr.Slider(
                0.05, 0.50, step=0.01,
                value=float(state.get("rewrite_cci_low", 0.20)),
                label="Low CCI Threshold"
            )

        with gr.Row():
            sl_hrs_mid = gr.Slider(
                0.10, 1.50, step=0.01,
                value=float(state.get("rewrite_hrs_mid", 0.55)),
                label="Medium HRS Threshold"
            )
            sl_hrs_high = gr.Slider(
                0.10, 2.00, step=0.01,
                value=float(state.get("rewrite_hrs_high", 0.75)),
                label="High HRS Threshold"
            )

        save_btn = gr.Button("Save Rewrite Settings", variant="primary")
        status = gr.Markdown(
            value=f"Rewrite: {'on' if state.get('rewrite_enabled', True) else 'off'}"
        )

        def _save(v_enabled, v_banner, v_mode, v_cci_high, v_cci_low, v_hrs_mid, v_hrs_high):
            state["rewrite_enabled"] = bool(v_enabled)
            state["rewrite_show_banner"] = bool(v_banner)
            state["rewrite_mode"] = v_mode or "balanced"
            state["rewrite_cci_high"] = float(v_cci_high)
            state["rewrite_cci_low"] = float(v_cci_low)
            state["rewrite_hrs_mid"] = float(v_hrs_mid)
            state["rewrite_hrs_high"] = float(v_hrs_high)
            save_state()
            return (
                f"Saved. rewrite={'on' if state['rewrite_enabled'] else 'off'} "
                f"mode={state['rewrite_mode']}"
            )

        save_btn.click(
            _save,
            [cb_enabled, cb_banner, dd_mode, sl_cci_high, sl_cci_low, sl_hrs_mid, sl_hrs_high],
            [status]
        )


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/rewrite_loop_v2] ready ✓")

_init()