"""
MAAT Value Core Module  (maat_value_core.py)
=============================================

Fundamental grounding of MAAT scoring logic.

Purpose
-------
- Teach the model what the MAAT value actually is
- Define H, B, S, V, R clearly
- Explain how to improve weak fields
- Provide a stable internal correction loop

This is NOT a personality module.
This is NOT a reflection module.

This is the foundation layer.

Commands
--------
    /maat core
    /maat core on|off
"""

from typing import Dict, Any, Optional
import re

try:
    import gradio as gr
except Exception:
    gr = None


# ============================================================
# Defaults
# ============================================================

DEFAULTS: Dict[str, Any] = {
    "maat_core_enabled": True,
    "maat_core_mode": "standard",  # light | standard | strict
}


# ============================================================
# Core blocks
# ============================================================

_CORE_LIGHT = """\
[MAAT_CORE]
Maat-Wert = (H + B + S + V + R) / 5

Ziel:
Erzeuge Antworten mit hoher Gesamtqualität.

Wenn ein Feld schwach ist:
→ verbessere genau dieses Feld.

Keine sichtbaren Scores schreiben.
[/MAAT_CORE]
"""


_CORE_STANDARD = """\
[MAAT_CORE]

Grundlage:
Der Maat-Wert ist die Qualität einer Antwort.

Formel:
Maat-Wert = (H + B + S + V + R) / 5

Bedeutung der Felder:
H = Harmonie → Klarheit, Struktur, Verständlichkeit  
B = Balance → keine Einseitigkeit, ehrliche Abwägung  
S = Schöpfungskraft → gute Idee, Beispiel oder Perspektive  
V = Verbundenheit → Bezug zur Frage und zum Kontext  
R = Respekt → Ehrlichkeit, keine Halluzination, klare Grenzen  

Regel:
Der Maat-Wert ist kein Textbestandteil, sondern ein Steuermechanismus.

Wenn ein Feld schwach ist:
- H niedrig → klarer und strukturierter schreiben
- B niedrig → ausgewogener formulieren
- S niedrig → bessere Idee oder Beispiel ergänzen
- V niedrig → näher an der Frage bleiben
- R niedrig → ehrlich sein, Unsicherheit benennen

Ziel:
Erzeuge eine Antwort mit möglichst hohem Maat-Wert.

Keine sichtbaren Scores schreiben.
[/MAAT_CORE]
"""


_CORE_STRICT = """\
[MAAT_CORE]

Du arbeitest nach dem MAAT-Bewertungssystem.

Formel:
Maat-Wert = (H + B + S + V + R) / 5

Jede Antwort muss intern geprüft werden.

Felder:
H = Klarheit und Kohärenz  
B = Balance und Ehrlichkeit  
S = sinnvolle Schöpfungskraft (keine leere Kreativität)  
V = direkte Verbundenheit zur Frage  
R = Wahrheit, Vorsicht, keine Halluzination  

Verpflichtung:
- Antworte erst, nachdem du deine Antwort intern verbessert hast
- Vermeide unnötige Mystik oder leere Tiefe
- Vermeide falsche Sicherheit
- Vermeide Abschweifen

Korrekturregel:
Wenn ein Feld schwach ist, verbessere gezielt dieses Feld.

Besonders wichtig:
R > alles andere → keine erfundenen Fakten

Keine sichtbaren Scores schreiben.
[/MAAT_CORE]
"""


_BLOCKS = {
    "light": _CORE_LIGHT,
    "standard": _CORE_STANDARD,
    "strict": _CORE_STRICT,
}


def _normalize_mode(mode: str) -> str:
    mode = (mode or "standard").lower()
    return mode if mode in _BLOCKS else "standard"


# ============================================================
# Hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("maat_core", {})
    shared["maat_core"]["enabled"] = state.get("maat_core_enabled", True)
    shared["maat_core"]["mode"] = state.get("maat_core_mode", "standard")


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("maat_core_enabled", True):
        return {}

    mode = _normalize_mode(state.get("maat_core_mode", "standard"))
    block = _BLOCKS[mode]

    return {"inject_hidden": block}


# ============================================================
# Commands
# ============================================================

def _status_text(state: dict) -> str:
    return (
        f"MAAT Core: {'on' if state.get('maat_core_enabled', True) else 'off'}  "
        f"mode={state.get('maat_core_mode', 'standard')}"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat core":
        return _status_text(state)

    m = re.match(r"^/maat core (on|off)$", cmd)
    if m:
        state["maat_core_enabled"] = (m.group(1) == "on")
        return f"MAAT core {'enabled' if state['maat_core_enabled'] else 'disabled'}."

    m = re.match(r"^/maat core mode (light|standard|strict)$", cmd)
    if m:
        state["maat_core_mode"] = m.group(1)
        return f"MAAT core mode: {state['maat_core_mode']}"

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("⚙️ MAAT Value Core", open=False):
        gr.Markdown(
            "Fundamental MAAT scoring logic.\n"
            "This defines how H, B, S, V, R are understood and applied."
        )

        cb_enabled = gr.Checkbox(
            value=state.get("maat_core_enabled", True),
            label="Core Enabled"
        )

        dd_mode = gr.Dropdown(
            choices=["light", "standard", "strict"],
            value=state.get("maat_core_mode", "standard"),
            label="Core Mode"
        )

        save_btn = gr.Button("Save Core Settings", variant="primary")
        status = gr.Markdown(value=_status_text(state))

        def _save(v_enabled, v_mode):
            state["maat_core_enabled"] = bool(v_enabled)
            state["maat_core_mode"] = _normalize_mode(v_mode)
            save_state()
            return _status_text(state)

        save_btn.click(_save, [cb_enabled, dd_mode], [status])


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/value_core] ready ✓")

_init()