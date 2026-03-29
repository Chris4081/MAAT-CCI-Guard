"""
MAAT Reality Layer  (maat_reality_layer.py)
===========================================

Reality grounding layer for MAAT-KI.

Purpose
-------
- Inject current date/time as live context
- Distinguish between:
    * live reality
    * stored memory
    * uncertainty
- Reduce hallucinations on practical questions

Commands
--------
    /maat reality
    /maat reality on|off
    /maat time
    /maat date
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import gradio as gr
except Exception:
    gr = None


DEFAULTS: Dict[str, Any] = {
    "reality_enabled": True,
    "reality_inject_time": True,
    "reality_show_banner": False,
}

SESSION: Dict[str, Any] = {
    "last_context": None,
}


# ============================================================
# Helpers
# ============================================================

def _now():
    return datetime.now()


def _build_reality_block() -> str:
    now = _now()
    return (
        "[MAAT_REALITY]\n"
        f"Heutiges Datum: {now.strftime('%d.%m.%Y')}\n"
        f"Aktuelle Uhrzeit: {now.strftime('%H:%M')}\n"
        "Regel:\n"
        "- Aktuelle Uhrzeit und aktuelles Datum sind Live-Kontext, nicht Memory.\n"
        "- Gespeicherte Nutzerfakten kommen aus Memory.\n"
        "- Wenn weder Live-Kontext noch Memory ausreichen: nichts erfinden.\n"
        "[/MAAT_REALITY]"
    )


def _is_time_question(text: str) -> bool:
    t = (text or "").lower()
    patterns = [
        "wie viel uhr", "wieviel uhr", "uhrzeit", "welche uhrzeit",
        "what time", "current time", "time is it"
    ]
    return any(p in t for p in patterns)


def _is_date_question(text: str) -> bool:
    t = (text or "").lower()
    patterns = [
        "welcher tag", "welches datum", "heute für ein tag", "welches datum haben wir",
        "what date", "what day is it", "current date", "today is"
    ]
    return any(p in t for p in patterns)


def _is_reality_question(text: str) -> bool:
    return _is_time_question(text) or _is_date_question(text)


def _direct_time_answer() -> str:
    return f"Es ist aktuell {_now().strftime('%H:%M')}."


def _direct_date_answer() -> str:
    now = _now()
    return f"Heute ist der {now.strftime('%d.%m.%Y')}."


# ============================================================
# Hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("reality_status", {})
    shared["reality_status"] = {
        "enabled": state.get("reality_enabled", True),
        "inject_time": state.get("reality_inject_time", True),
    }


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("reality_enabled", True):
        return {}

    if not state.get("reality_inject_time", True):
        return {}

    block = _build_reality_block()
    SESSION["last_context"] = block
    shared.setdefault("reality_status", {})
    shared["reality_status"]["last_context"] = block

    if _is_reality_question(user_input or ""):
        priority = (
            "[MAAT_REALITY_PRIORITY]\n"
            "Die aktuelle Userfrage bezieht sich auf Live-Realität.\n"
            "Antworte direkt, konkret und ohne Ausschmückung.\n"
            "Keine Metaphern. Keine Ausweichantwort.\n"
            "[/MAAT_REALITY_PRIORITY]\n\n"
            + block
        )
        return {"inject_hidden": priority}

    return {"inject_hidden": block}


def after_output(user_input: str, output: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("reality_enabled", True):
        return {}

    ui = user_input or ""

    if _is_time_question(ui):
        answer = _direct_time_answer()
        if state.get("reality_show_banner", False):
            answer = "[REALITY] Live-Zeit verwendet.\n\n" + answer
        return {"output": answer}

    if _is_date_question(ui):
        answer = _direct_date_answer()
        if state.get("reality_show_banner", False):
            answer = "[REALITY] Live-Datum verwendet.\n\n" + answer
        return {"output": answer}

    return {}


# ============================================================
# Commands
# ============================================================

def _status_text(state: dict) -> str:
    return (
        f"MAAT Reality Layer: {'on' if state.get('reality_enabled', True) else 'off'}  "
        f"inject_time={'on' if state.get('reality_inject_time', True) else 'off'}"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat reality":
        return _status_text(state)

    m = re.match(r"^/maat reality (on|off)$", cmd)
    if m:
        state["reality_enabled"] = (m.group(1) == "on")
        return f"MAAT reality layer {'enabled' if state['reality_enabled'] else 'disabled'}."

    if cmd == "/maat time":
        return _direct_time_answer()

    if cmd == "/maat date":
        return _direct_date_answer()

    return None


def register_commands(router, STATE, SHARED):
    router.register("/maat reality", lambda cmd, context=None: _status_text(STATE), "Show reality layer status")
    router.register("/maat reality on", lambda cmd, context=None: _set_enabled(STATE, True), "Enable reality layer")
    router.register("/maat reality off", lambda cmd, context=None: _set_enabled(STATE, False), "Disable reality layer")
    router.register("/maat time", lambda cmd, context=None: _direct_time_answer(), "Show current time")
    router.register("/maat date", lambda cmd, context=None: _direct_date_answer(), "Show current date")


def _set_enabled(state: dict, value: bool) -> str:
    state["reality_enabled"] = bool(value)
    return f"MAAT reality layer {'enabled' if value else 'disabled'}."


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("🕒 MAAT Reality Layer", open=False):
        gr.Markdown(
            "Live grounding layer for current date/time and practical reality-based answers."
        )

        cb_enabled = gr.Checkbox(
            value=state.get("reality_enabled", True),
            label="Reality Layer Enabled"
        )
        cb_inject = gr.Checkbox(
            value=state.get("reality_inject_time", True),
            label="Inject Current Date/Time"
        )
        cb_banner = gr.Checkbox(
            value=state.get("reality_show_banner", False),
            label="Show Reality Banner"
        )

        save_btn = gr.Button("Save Reality Settings", variant="primary")
        status = gr.Markdown(value=_status_text(state))

        def _save(v_enabled, v_inject, v_banner):
            state["reality_enabled"] = bool(v_enabled)
            state["reality_inject_time"] = bool(v_inject)
            state["reality_show_banner"] = bool(v_banner)
            save_state()
            return _status_text(state)

        save_btn.click(_save, [cb_enabled, cb_inject, cb_banner], [status])


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/reality_layer] ready ✓")

_init()