"""
MAAT Thinking Module  (maat_thinking.py)
========================================

Internal quality steering mode for MAAT-KI.

Purpose
-------
- Adds a silent MAAT self-check before answering
- Encourages higher H, B, S, V, R quality
- Toggleable in UI

Commands
--------
    /maat thinking
    /maat thinking on|off
    /maat thinking depth <light|balanced|deep>
    /maat thinking target <float>
"""

import re
from typing import Dict, Any, Optional

try:
    import gradio as gr
except Exception:
    gr = None


DEFAULTS: Dict[str, Any] = {
    "maat_thinking_mode": False,
    "maat_thinking_target": 8.8,
    "maat_thinking_depth": "balanced",   # light | balanced | deep
}

_DEPTH_BLOCKS = {
    "light": """[MAAT_THINKING]
Prüfe die Antwort still:
- klar?
- ehrlich?
- hilfreich?
- nah an der Frage?
Verbessere sie kurz, falls nötig.
Keine sichtbare Score-Ausgabe.
[/MAAT_THINKING]""",

    "balanced": """[MAAT_THINKING]
Prüfe die Antwort vor dem Ausgeben still nach:
- H = Harmonie
- B = Balance
- S = Schöpfungskraft
- V = Verbundenheit
- R = Respekt

Ziel:
- möglichst hoher Maat-Wert
- klare, ehrliche, hilfreiche Antwort
- keine sichtbare Score-Ausgabe

Wenn ein Feld schwach ist:
- H → klarer und strukturierter schreiben
- B → ausgewogener und ehrlicher formulieren
- S → eine bessere Idee, Formulierung oder ein Beispiel ergänzen
- V → näher an der Frage und am Kontext bleiben
- R → keine Halluzination, Grenzen ehrlich benennen

Überarbeite die Antwort still, bevor du sie ausgibst.
[/MAAT_THINKING]""",

    "deep": """[MAAT_THINKING]
Führe vor der Antwort eine stille MAAT-Selbstprüfung durch.

Prüfe:
- H = sprachliche und logische Kohärenz
- B = Balance zwischen Tiefe, Nüchternheit und Nähe
- S = Schöpfungskraft als bessere Lösung, nicht als leere Verzierung
- V = Verbundenheit mit der Frage, dem Nutzer und dem Kontext
- R = Ehrlichkeit, Vorsicht, Würde, keine Halluzination

Ziel:
- Maat-Zielwert intern möglichst hoch halten
- keine sichtbaren Scores schreiben
- keine künstliche Mystifizierung
- keine unnötige Länge
- keine ausweichende Antwort bei konkreten Fragen

Wenn die Frage faktisch ist:
- antworte konkret und geerdet
Wenn die Frage persönlich oder philosophisch ist:
- antworte tief, aber klar
Wenn Wissen fehlt:
- ehrlich sagen
- trotzdem hilfreich einordnen

Verbessere die Antwort intern, bevor du sie ausgibst.
[/MAAT_THINKING]"""
}


def _normalize_depth(depth: str) -> str:
    depth = (depth or "balanced").lower()
    return depth if depth in _DEPTH_BLOCKS else "balanced"


def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("thinking_status", {})
    shared["thinking_status"] = {
        "enabled": state.get("maat_thinking_mode", False),
        "target": state.get("maat_thinking_target", 8.8),
        "depth": state.get("maat_thinking_depth", "balanced"),
    }


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("maat_thinking_mode", False):
        return {}

    depth = _normalize_depth(state.get("maat_thinking_depth", "balanced"))
    target = float(state.get("maat_thinking_target", 8.8))

    block = _DEPTH_BLOCKS[depth] + f"\n[MAAT_THINKING_TARGET]\nZielwert intern: {target:.1f}\n[/MAAT_THINKING_TARGET]"
    return {"inject_hidden": block}


def _status_text(state: dict) -> str:
    return (
        f"MAAT Thinking: {'on' if state.get('maat_thinking_mode', False) else 'off'}  "
        f"depth={state.get('maat_thinking_depth', 'balanced')}  "
        f"target={float(state.get('maat_thinking_target', 8.8)):.1f}"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat thinking":
        return _status_text(state)

    m = re.match(r"^/maat thinking (on|off)$", cmd)
    if m:
        state["maat_thinking_mode"] = (m.group(1) == "on")
        return f"MAAT thinking {'enabled' if state['maat_thinking_mode'] else 'disabled'}."

    m = re.match(r"^/maat thinking depth (light|balanced|deep)$", cmd)
    if m:
        state["maat_thinking_depth"] = m.group(1)
        return f"MAAT thinking depth: {state['maat_thinking_depth']}."

    m = re.match(r"^/maat thinking target ([0-9]+(?:\.[0-9]+)?)$", cmd)
    if m:
        state["maat_thinking_target"] = float(m.group(1))
        return f"MAAT thinking target: {state['maat_thinking_target']:.1f}"

    return None


def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("🧠 MAAT Thinking Mode", open=False):
        gr.Markdown(
            "Silent quality mode: the model internally tries to improve H, B, S, V, and R before answering."
        )

        cb_enabled = gr.Checkbox(
            value=state.get("maat_thinking_mode", False),
            label="MAAT Thinking Enabled"
        )

        dd_depth = gr.Dropdown(
            choices=["light", "balanced", "deep"],
            value=state.get("maat_thinking_depth", "balanced"),
            label="Thinking Depth"
        )

        sl_target = gr.Slider(
            6.0, 10.0, step=0.1,
            value=float(state.get("maat_thinking_target", 8.8)),
            label="Target Maat Value"
        )

        save_btn = gr.Button("Save Thinking Settings", variant="primary")
        status = gr.Markdown(value=_status_text(state))

        def _save(v_enabled, v_depth, v_target):
            state["maat_thinking_mode"] = bool(v_enabled)
            state["maat_thinking_depth"] = _normalize_depth(v_depth)
            state["maat_thinking_target"] = float(v_target)
            save_state()
            return _status_text(state)

        save_btn.click(_save, [cb_enabled, dd_depth, sl_target], [status])


def _init():
    print("[maat/thinking] ready ✓")

_init()