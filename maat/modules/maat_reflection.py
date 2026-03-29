"""
MAAT Reflection Module
======================

Purpose
-------
- Compute MAAT reflection values in Python
- Render stability lines as guaranteed markdown code blocks
- Optionally prepend a reflection banner to model output

Compatible with MAAT modular loader v2.
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
    "reflection_enabled": True,
    "reflection_banner": True,
    "reflection_mode": "auto",   # auto | manual
    "reflection_force_codeblock": True,
}

SESSION: Dict[str, Any] = {
    "last_scores": None,
}


# ============================================================
# Helpers
# ============================================================

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return float(default)


def _codeblock(text: str) -> str:
    text = (text or "").strip()
    return f"```text\n{text}\n```"


def maat_stability(H: float, B: float, S: float, V: float, R: float) -> Dict[str, Any]:
    """
    Stability = min(R, (H*B*S*V)**0.25)
    """
    H = _safe_float(H)
    B = _safe_float(B)
    S = _safe_float(S)
    V = _safe_float(V)
    R = _safe_float(R)

    geom = (H * B * S * V) ** 0.25 if (H * B * S * V) >= 0 else 0.0
    stability = min(R, geom)

    return {
        "H": H,
        "B": B,
        "S": S,
        "V": V,
        "R": R,
        "value": stability,
        "rounded": round(stability, 2),
        "text": f"H={H:.1f} B={B:.1f} S={S:.1f} V={V:.1f} R={R:.1f} → Stability={stability:.2f}",
    }


def _extract_scores_from_text(text: str) -> Optional[Dict[str, float]]:
    """
    Extracts H/B/S/V/R from patterns like:
    H=8.0 B=7.9 S=2.8 V=2.9 R=10.0
    """
    text = text or ""

    pattern = (
        r"H\s*=\s*([0-9]+(?:\.[0-9]+)?)\s+"
        r"B\s*=\s*([0-9]+(?:\.[0-9]+)?)\s+"
        r"S\s*=\s*([0-9]+(?:\.[0-9]+)?)\s+"
        r"V\s*=\s*([0-9]+(?:\.[0-9]+)?)\s+"
        r"R\s*=\s*([0-9]+(?:\.[0-9]+)?)"
    )

    m = re.search(pattern, text)
    if not m:
        return None

    return {
        "H": float(m.group(1)),
        "B": float(m.group(2)),
        "S": float(m.group(3)),
        "V": float(m.group(4)),
        "R": float(m.group(5)),
    }


def _diagnosis_line(scores: Dict[str, Any]) -> str:
    vals = {
        "H": scores["H"],
        "B": scores["B"],
        "S": scores["S"],
        "V": scores["V"],
        "R": scores["R"],
    }
    weakest = sorted(vals.items(), key=lambda kv: kv[1])[:2]
    weak_names = ", ".join(k for k, _ in weakest)
    return f"Weakest fields: {weak_names}"


# ============================================================
# Loader hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("maat_reflection", {})
    shared["maat_reflection"]["ready"] = True


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    """
    Inject a small instruction so the model knows reflection output
    should not freestyle formatting.
    """
    if not state.get("reflection_enabled", True):
        return {}

    inject = """[MAAT_REFLECTION_RULE]
If you mention H, B, S, V, R or Stability explicitly,
prefer a single compact line and treat it as structured data.
Do not alternate randomly between prose and non-code formatting.
[/MAAT_REFLECTION_RULE]"""

    return {"inject": inject}


def after_output(user_input: str, output: str, state_obj, state: dict, shared: dict) -> dict:
    """
    If the model output contains H/B/S/V/R values, compute stability in Python
    and prepend a guaranteed code block.
    """
    if not state.get("reflection_enabled", True):
        return {}

    text = output or ""

    # Priority 1: use maat_engine computed scores (accurate, 0-10 scale)
    engine_data = shared.get("maat_engine", {}).get("scores_for_banner")
    if engine_data:
        result = engine_data
        SESSION["last_scores"] = result
        shared["maat_reflection"]["last_scores"] = result
    else:
        # Priority 2: parse scores from model output (fallback)
        scores = _extract_scores_from_text(text)
        if not scores:
            return {}
        result = maat_stability(
            scores["H"], scores["B"], scores["S"], scores["V"], scores["R"]
        )
        SESSION["last_scores"] = result
        shared["maat_reflection"]["last_scores"] = result

    if not state.get("reflection_banner", True):
        return {}

    # Build banner from result
    if isinstance(result, dict) and "text" in result:
        score_line = result["text"]
        diag = result.get("diagnosis", "").split("|")[0].strip() if "diagnosis" in result else _diagnosis_line(result)
    else:
        score_line = str(result)
        diag = ""

    banner_parts = [score_line]
    if state.get("reflection_mode", "auto") == "auto" and diag:
        banner_parts.append(diag)

    banner = _codeblock("\n".join(banner_parts))

    # Remove the raw H/B/S/V/R scores from text — scores shown once in banner
    _scores_only = re.compile(
        r"H\s*=\s*[\d.]+\s+B\s*=\s*[\d.]+\s+S\s*=\s*[\d.]+\s+V\s*=\s*[\d.]+\s+R\s*=\s*[\d.]+"
    )
    lines_out = []
    for line in text.split("\n"):
        m_s = _scores_only.search(line)
        if m_s:
            # Get everything after the scores block
            rest = line[m_s.end():].strip()
            # Strip optional "→ Stability=x.xx"
            rest = re.sub(r"^[\s→\-]+Stability\s*=\s*[\d.]+", "", rest).strip()
            # Strip remaining arrow/dash
            rest = re.sub(r"^[\s→\-]+", "", rest).strip()
            if rest:
                lines_out.append(rest)
        else:
            lines_out.append(line)
    cleaned = "\n".join(lines_out).strip()

    return {"output": banner + "\n\n" + cleaned}


# ============================================================
# Commands
# ============================================================

def _status_text(state: dict) -> str:
    last = SESSION.get("last_scores")
    if last:
        last_txt = last["text"]
    else:
        last_txt = "None"
    return (
        f"MAAT Reflection: {'on' if state.get('reflection_enabled', True) else 'off'}  "
        f"banner={'on' if state.get('reflection_banner', True) else 'off'}  "
        f"mode={state.get('reflection_mode', 'auto')}  "
        f"last={last_txt}"
    )


def cmd_reflection_root(cmd: str, context=None):
    state = context["STATE"]
    return _status_text(state)


def cmd_reflection_toggle(cmd: str, context=None):
    state = context["STATE"]
    m = re.match(r"^/maat reflection (on|off)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat reflection on|off"
    state["reflection_enabled"] = (m.group(1) == "on")
    return f"MAAT reflection {'enabled' if state['reflection_enabled'] else 'disabled'}."


def cmd_reflection_banner(cmd: str, context=None):
    state = context["STATE"]
    m = re.match(r"^/maat reflection banner (on|off)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat reflection banner on|off"
    state["reflection_banner"] = (m.group(1) == "on")
    return f"Reflection banner {'enabled' if state['reflection_banner'] else 'disabled'}."


def cmd_reflection_mode(cmd: str, context=None):
    state = context["STATE"]
    m = re.match(r"^/maat reflection mode (auto|manual)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat reflection mode auto|manual"
    state["reflection_mode"] = m.group(1)
    return f"Reflection mode: {state['reflection_mode']}."


def cmd_reflection_last(cmd: str, context=None):
    last = SESSION.get("last_scores")
    if not last:
        return "No reflection scores yet."
    return _codeblock(last["text"])


def register_commands(router, STATE, SHARED):
    router.register("/maat reflection", lambda cmd, context=None: _status_text(STATE), "Show reflection status")
    router.register(
        "/maat reflection on",
        lambda cmd, context=None: _set_reflection_enabled(STATE, True),
        "Enable reflection module"
    )
    router.register(
        "/maat reflection off",
        lambda cmd, context=None: _set_reflection_enabled(STATE, False),
        "Disable reflection module"
    )
    router.register(
        "/maat reflection banner",
        lambda cmd, context=None: cmd_reflection_banner(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Toggle reflection banner"
    )
    router.register(
        "/maat reflection mode",
        lambda cmd, context=None: cmd_reflection_mode(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Set reflection mode"
    )
    router.register(
        "/maat reflection last",
        lambda cmd, context=None: cmd_reflection_last(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Show last computed reflection line"
    )


def _set_reflection_enabled(state: dict, value: bool) -> str:
    state["reflection_enabled"] = bool(value)
    return f"MAAT reflection {'enabled' if value else 'disabled'}."


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat reflection":
        return _status_text(state)

    m = re.match(r"^/maat reflection (on|off)$", cmd)
    if m:
        state["reflection_enabled"] = (m.group(1) == "on")
        return f"MAAT reflection {'enabled' if state['reflection_enabled'] else 'disabled'}."

    m = re.match(r"^/maat reflection banner (on|off)$", cmd)
    if m:
        state["reflection_banner"] = (m.group(1) == "on")
        return f"Reflection banner {'enabled' if state['reflection_banner'] else 'disabled'}."

    m = re.match(r"^/maat reflection mode (auto|manual)$", cmd)
    if m:
        state["reflection_mode"] = m.group(1)
        return f"Reflection mode: {state['reflection_mode']}."

    if cmd == "/maat reflection last":
        last = SESSION.get("last_scores")
        if not last:
            return "No reflection scores yet."
        return _codeblock(last["text"])

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("🧠 MAAT Reflection Module", open=False):
        gr.Markdown(
            "Computes MAAT Stability in Python and renders it as a guaranteed markdown code block."
        )

        with gr.Row():
            cb_enabled = gr.Checkbox(
                value=state.get("reflection_enabled", True),
                label="Reflection Enabled"
            )
            cb_banner = gr.Checkbox(
                value=state.get("reflection_banner", True),
                label="Show Banner"
            )

        dd_mode = gr.Dropdown(
            choices=["auto", "manual"],
            value=state.get("reflection_mode", "auto"),
            label="Reflection Mode"
        )

        save_btn = gr.Button("Save Reflection Settings", variant="primary")
        out = gr.Markdown(value="")

        def _save(v_enabled, v_banner, v_mode):
            state["reflection_enabled"] = bool(v_enabled)
            state["reflection_banner"] = bool(v_banner)
            state["reflection_mode"] = v_mode or "auto"
            save_state()
            return (
                f"Saved. reflection={'on' if v_enabled else 'off'} "
                f"banner={'on' if v_banner else 'off'} mode={state['reflection_mode']}"
            )

        save_btn.click(_save, [cb_enabled, cb_banner, dd_mode], [out])

        with gr.Accordion("Preview", open=False):
            btn_preview = gr.Button("Preview Example")
            preview = gr.Markdown(value="")

            def _preview():
                result = maat_stability(8.0, 7.9, 2.8, 2.9, 10.0)
                return _codeblock(result["text"])

            btn_preview.click(_preview, outputs=[preview])


def _init():
    print("[maat/reflection] ready ✓")

_init()