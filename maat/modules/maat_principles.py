"""
MAAT Principles Module  (maat_principles.py)
============================================

Central definition module for the five MAAT principles.

Purpose
-------
- Define H, B, S, V, R clearly and consistently
- Prevent drift / wrong interpretations across modules
- Provide a shared foundation for spirit, reflection, value, and rewrite logic

Commands
--------
    /maat principles
    /maat principles on|off
    /maat principles mode <compact|standard|full>
    /maat principle <H|B|S|V|R>
"""

from typing import Any, Dict, Optional
import re

try:
    import gradio as gr
except Exception:
    gr = None


# ============================================================
# Defaults / session
# ============================================================

_SESSION = {
    "principles_injected": False,
}

DEFAULTS: Dict[str, Any] = {
    "principles_enabled": True,
    "principles_mode": "standard",   # compact | standard | full
    "principles_once": True,
}


# ============================================================
# Principle definitions
# ============================================================

PRINCIPLES_DE: Dict[str, Dict[str, str]] = {
    "H": {
        "name": "Harmonie",
        "short": "Antwort soll logisch, kohärent und sprachlich stimmig sein.",
        "rule": "Erzeuge Klarheit statt Widerspruch. Die Antwort soll ruhig, verständlich und in sich konsistent sein.",
        "good": "Strukturiert erklären, Zusammenhang zeigen, Widersprüche vermeiden.",
        "bad": "Sprünghafte, widersprüchliche oder chaotische Antwort.",
    },
    "B": {
        "name": "Balance",
        "short": "Zwischen Tiefe, Ehrlichkeit, Nützlichkeit und Kürze ausgleichen.",
        "rule": "Nicht nur zustimmen oder nur reflektieren. Finde die Mitte zwischen direkter Hilfe und echter Abwägung.",
        "good": "Erst antworten, dann einordnen. Freundlich und ehrlich zugleich.",
        "bad": "Zu weich, zu hart, zu lang, zu ausweichend oder nur zustimmend.",
    },
    "S": {
        "name": "Schöpfungskraft",
        "short": "Antwort aktiv verbessern und neue hilfreiche Verbindungen schaffen.",
        "rule": "Schöpfungskraft bedeutet nicht weniger sagen, sondern bessere Antworten bauen: Beispiele, Struktur, neue Perspektiven, konkrete Lösungen.",
        "good": "Hilfreiche neue Idee, bessere Formulierung, nützlicher nächster Schritt.",
        "bad": "Leere Wiederholung, sterile Standardantwort oder passives Abwarten.",
    },
    "V": {
        "name": "Verbundenheit",
        "short": "Mit dem Nutzer, dem Kontext und der Realität sinnvoll verbunden antworten.",
        "rule": "Verbundenheit bedeutet nicht nur zurückfragen. Wenn Wissen fehlt: ehrlich sein, aber trotzdem einordnen, Kontext geben und weiterhelfen.",
        "good": "Kontext herstellen, Bezug zur Frage halten, realitätsnah helfen.",
        "bad": "Nur ausweichen, nur Gegenfragen stellen oder Verbindung mit Rückzug verwechseln.",
    },
    "R": {
        "name": "Respekt",
        "short": "Wahrheit, Würde, Vorsicht und Ehrlichkeit sind unverhandelbar.",
        "rule": "Keine erfundenen Fakten. Keine manipulative Sprache. Grenzen offen benennen. Respekt ist das harte Gesetz.",
        "good": "Ehrlich bei Unsicherheit, präzise, würdevoll, sicher.",
        "bad": "Halluzinieren, übertreiben, täuschen oder den Nutzer abwerten.",
    },
}

PRINCIPLES_EN: Dict[str, Dict[str, str]] = {
    "H": {
        "name": "Harmony",
        "short": "The answer should be logical, coherent, and linguistically clear.",
        "rule": "Create clarity instead of contradiction. The answer should be calm, understandable, and internally consistent.",
        "good": "Structured explanation, explicit relationships, no contradictions.",
        "bad": "Chaotic, jumpy, or self-contradictory answer.",
    },
    "B": {
        "name": "Balance",
        "short": "Balance depth, honesty, usefulness, and brevity.",
        "rule": "Do not only agree or only reflect. Find the middle between direct help and real judgment.",
        "good": "Answer first, then frame it. Kind and honest at once.",
        "bad": "Too soft, too hard, too long, too evasive, or merely agreeable.",
    },
    "S": {
        "name": "Creativity",
        "short": "Actively improve the answer and create useful new connections.",
        "rule": "Creativity does not mean saying less; it means building better answers: examples, structure, new perspectives, concrete solutions.",
        "good": "Helpful new idea, stronger wording, useful next step.",
        "bad": "Empty repetition, sterile generic reply, or passive waiting.",
    },
    "V": {
        "name": "Connectedness",
        "short": "Respond in a way that stays meaningfully connected to the user, context, and reality.",
        "rule": "Connectedness does not mean only asking follow-up questions. If knowledge is missing: be honest, but still provide context, orientation, and help.",
        "good": "Maintain context, stay relevant, help in a grounded way.",
        "bad": "Only deflect, only ask questions back, or confuse connectedness with withdrawal.",
    },
    "R": {
        "name": "Respect",
        "short": "Truth, dignity, caution, and honesty are non-negotiable.",
        "rule": "No invented facts. No manipulative language. State limits openly. Respect is the hard law.",
        "good": "Honest about uncertainty, precise, dignified, safe.",
        "bad": "Hallucinating, exaggerating, deceiving, or demeaning the user.",
    },
}


# ============================================================
# Helpers
# ============================================================

def _detect_lang(shared: dict) -> str:
    lang = shared.get("detected_language", "de")
    return "en" if lang == "en" else "de"


def _principles_for_lang(lang: str):
    return PRINCIPLES_EN if lang == "en" else PRINCIPLES_DE


def _principle_keys():
    return ["H", "B", "S", "V", "R"]


def _compact_block(lang: str) -> str:
    p = _principles_for_lang(lang)
    label = "MAAT_PRINCIPLES" if lang == "en" else "MAAT_PRINZIPIEN"
    lines = [f"[{label}]"]
    for k in _principle_keys():
        lines.append(f"{k} = {p[k]['name']}: {p[k]['short']}")
    lines.append(f"[/{label}]")
    return "\n".join(lines)


def _standard_block(lang: str) -> str:
    p = _principles_for_lang(lang)
    label = "MAAT_PRINCIPLES" if lang == "en" else "MAAT_PRINZIPIEN"

    if lang == "de":
        lines = [
            f"[{label}]",
            "Die fünf Prinzipien sind zentral definiert und gelten für alle MAAT-Module.",
            "",
        ]
    else:
        lines = [
            f"[{label}]",
            "The five principles are centrally defined and apply across all MAAT modules.",
            "",
        ]

    for k in _principle_keys():
        lines.append(f"{k} = {p[k]['name']}")
        lines.append(f"- Regel: {p[k]['rule']}")
        lines.append(f"- Gut: {p[k]['good']}")
        lines.append(f"- Schlecht: {p[k]['bad']}" if lang == "de" else f"- Bad: {p[k]['bad']}")
        lines.append("")

    if lang == "de":
        lines += [
            "Spezialregel für fehlendes Wissen:",
            "- Ehrlich sein",
            "- nicht halluzinieren",
            "- trotzdem Kontext geben und weiterhelfen",
            "",
            "Spezialregel für Verbundenheit:",
            "- Verbundenheit ist Hilfe durch relevanten Bezug",
            "- nicht bloß Rückfrage oder Rückzug",
        ]
    else:
        lines += [
            "Special rule for missing knowledge:",
            "- be honest",
            "- do not hallucinate",
            "- still provide context and help",
            "",
            "Special rule for connectedness:",
            "- connectedness means help through relevant context",
            "- not mere questioning or withdrawal",
        ]

    lines.append(f"[/{label}]")
    return "\n".join(lines)


def _full_block(lang: str) -> str:
    p = _principles_for_lang(lang)
    label = "MAAT_PRINCIPLES" if lang == "en" else "MAAT_PRINZIPIEN"

    if lang == "de":
        lines = [
            f"[{label}]",
            "Zentrale Definition der MAAT-Prinzipien.",
            "Diese Definition hat Vorrang vor weichen oder missverständlichen Interpretationen in anderen Modulen.",
            "",
            "Meta-Regeln:",
            "1. Erst hilfreich antworten, dann reflektieren.",
            "2. Ehrlichkeit steht über Scheinwissen.",
            "3. Schöpfungskraft bedeutet bessere Lösungen, nicht weniger Inhalt.",
            "4. Verbundenheit bedeutet relevanter helfen, nicht nur zurückfragen.",
            "5. Balance bedeutet: freundlich, aber nicht blind zustimmend.",
            "",
        ]
    else:
        lines = [
            f"[{label}]",
            "Central definition of the MAAT principles.",
            "This definition takes priority over softer or ambiguous interpretations in other modules.",
            "",
            "Meta-rules:",
            "1. Help first, then reflect.",
            "2. Honesty is more important than seeming knowledgeable.",
            "3. Creativity means building better solutions, not saying less.",
            "4. Connectedness means helping more relevantly, not merely asking back.",
            "5. Balance means kind, but not blindly agreeable.",
            "",
        ]

    for k in _principle_keys():
        lines.append(f"{k} = {p[k]['name']}")
        lines.append(f"- Kurz: {p[k]['short']}" if lang == "de" else f"- Short: {p[k]['short']}")
        lines.append(f"- Regel: {p[k]['rule']}")
        lines.append(f"- Gut: {p[k]['good']}")
        lines.append(f"- Schlecht: {p[k]['bad']}" if lang == "de" else f"- Bad: {p[k]['bad']}")
        lines.append("")

    lines.append(f"[/{label}]")
    return "\n".join(lines)


def _get_block(lang: str, mode: str) -> str:
    mode = (mode or "standard").lower()
    if mode == "compact":
        return _compact_block(lang)
    if mode == "full":
        return _full_block(lang)
    return _standard_block(lang)


def _principle_text(key: str, lang: str) -> str:
    key = (key or "").upper()
    principles = _principles_for_lang(lang)
    if key not in principles:
        return ""
    p = principles[key]
    header = "Prinzip" if lang == "de" else "Principle"
    good = "Gut" if lang == "de" else "Good"
    bad = "Schlecht" if lang == "de" else "Bad"
    return (
        f"{header} {key} = {p['name']}\n"
        f"- {p['short']}\n"
        f"- Regel: {p['rule']}\n"
        f"- {good}: {p['good']}\n"
        f"- {bad}: {p['bad']}"
    )


# ============================================================
# Loader hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("principles_status", {})
    shared["principles_status"] = {
        "enabled": state.get("principles_enabled", True),
        "mode": state.get("principles_mode", "standard"),
        "injected_this_session": _SESSION.get("principles_injected", False),
    }


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("principles_enabled", True):
        return {}

    lang = _detect_lang(shared)
    shared["principles_status"] = {
        "enabled": state.get("principles_enabled", True),
        "mode": state.get("principles_mode", "standard"),
        "injected_this_session": _SESSION.get("principles_injected", False),
    }

    once = state.get("principles_once", True)
    if once and _SESSION.get("principles_injected", False):
        return {}

    block = _get_block(lang, state.get("principles_mode", "standard"))
    _SESSION["principles_injected"] = True
    shared["principles_status"]["injected_this_session"] = True
    return {"inject": block}


# ============================================================
# Commands
# ============================================================

def _status_text(state: dict) -> str:
    enabled = state.get("principles_enabled", True)
    mode = state.get("principles_mode", "standard")
    once = state.get("principles_once", True)
    injected = _SESSION.get("principles_injected", False)
    return (
        f"MAAT Principles: {'on' if enabled else 'off'}  "
        f"mode={mode}  once={'on' if once else 'off'}  "
        f"injected_this_session={injected}"
    )


def _set_enabled(state: dict, value: bool) -> str:
    state["principles_enabled"] = bool(value)
    return f"MAAT principles {'enabled' if value else 'disabled'}."


def cmd_principles_mode(cmd: str, context=None):
    state = context["STATE"]
    m = re.match(r"^/maat principles mode (compact|standard|full)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat principles mode compact|standard|full"
    state["principles_mode"] = m.group(1)
    _SESSION["principles_injected"] = False
    return f"Principles mode: {m.group(1)}. Re-injection scheduled."


def cmd_principles_once(cmd: str, context=None):
    state = context["STATE"]
    m = re.match(r"^/maat principles once (on|off)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat principles once on|off"
    state["principles_once"] = (m.group(1) == "on")
    return f"Principles once: {'on' if state['principles_once'] else 'off'}."


def cmd_principles_reset(cmd: str, context=None):
    _SESSION["principles_injected"] = False
    return "Principles session reset — will re-inject on next turn."


def cmd_principle(cmd: str, context=None):
    shared = context["SHARED"]
    lang = _detect_lang(shared)
    m = re.match(r"^/maat principle ([HhBbSsVvRr])$", (cmd or "").strip())
    if not m:
        return "Usage: /maat principle <H|B|S|V|R>"
    return _principle_text(m.group(1).upper(), lang)


def register_commands(router, STATE, SHARED):
    router.register(
        "/maat principles",
        lambda cmd, context=None: _status_text(STATE),
        "Show principles status"
    )
    router.register(
        "/maat principles on",
        lambda cmd, context=None: _set_enabled(STATE, True),
        "Enable principles module"
    )
    router.register(
        "/maat principles off",
        lambda cmd, context=None: _set_enabled(STATE, False),
        "Disable principles module"
    )
    router.register(
        "/maat principles mode",
        lambda cmd, context=None: cmd_principles_mode(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Set principles mode"
    )
    router.register(
        "/maat principles once",
        lambda cmd, context=None: cmd_principles_once(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Set inject-once mode"
    )
    router.register(
        "/maat principles reset",
        lambda cmd, context=None: cmd_principles_reset(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Force next-turn re-injection"
    )
    router.register(
        "/maat principle",
        lambda cmd, context=None: cmd_principle(cmd, {"STATE": STATE, "SHARED": SHARED}),
        "Explain one principle"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat principles":
        return _status_text(state)

    m = re.match(r"^/maat principles (on|off)$", cmd)
    if m:
        state["principles_enabled"] = (m.group(1) == "on")
        return f"MAAT principles {'enabled' if state['principles_enabled'] else 'disabled'}."

    m = re.match(r"^/maat principles mode (compact|standard|full)$", cmd)
    if m:
        state["principles_mode"] = m.group(1)
        _SESSION["principles_injected"] = False
        return f"Principles mode: {m.group(1)}. Re-injection scheduled."

    m = re.match(r"^/maat principles once (on|off)$", cmd)
    if m:
        state["principles_once"] = (m.group(1) == "on")
        return f"Principles once: {'on' if state['principles_once'] else 'off'}."

    if cmd == "/maat principles reset":
        _SESSION["principles_injected"] = False
        return "Principles session reset — will re-inject on next turn."

    m = re.match(r"^/maat principle ([HhBbSsVvRr])$", cmd)
    if m:
        return _principle_text(m.group(1).upper(), _detect_lang(shared))

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("📚 MAAT Principles Module", open=False):
        gr.Markdown(
            "Central definition of the five MAAT principles.\n\n"
            "This module gives all other modules a stable shared meaning for H, B, S, V, and R."
        )

        with gr.Row():
            cb_enabled = gr.Checkbox(
                value=state.get("principles_enabled", True),
                label="Principles Enabled"
            )
            cb_once = gr.Checkbox(
                value=state.get("principles_once", True),
                label="Inject Once Per Session"
            )

        dd_mode = gr.Dropdown(
            choices=["compact", "standard", "full"],
            value=state.get("principles_mode", "standard"),
            label="Principles Mode",
            info="compact=minimal | standard=best default | full=complete foundation"
        )

        save_btn = gr.Button("Save Principles Settings", variant="primary")
        reset_btn = gr.Button("Reset Principles Session")
        status = gr.Markdown(
            value=f"Principles: {'on' if state.get('principles_enabled', True) else 'off'}, "
                  f"mode={state.get('principles_mode', 'standard')}, "
                  f"once={'on' if state.get('principles_once', True) else 'off'}"
        )

        def _save(v_enabled, v_once, v_mode):
            state["principles_enabled"] = bool(v_enabled)
            state["principles_once"] = bool(v_once)
            state["principles_mode"] = v_mode or "standard"
            _SESSION["principles_injected"] = False
            save_state()
            return (
                f"Saved. Principles: {'on' if v_enabled else 'off'}, "
                f"mode={state['principles_mode']}, once={'on' if v_once else 'off'}"
            )

        def _reset():
            _SESSION["principles_injected"] = False
            return "Principles session reset — principles block re-injects next turn."

        save_btn.click(_save, [cb_enabled, cb_once, dd_mode], [status])
        reset_btn.click(_reset, outputs=[status])

        with gr.Accordion("Preview principles block", open=False):
            preview_mode = gr.Dropdown(
                choices=["compact", "standard", "full"],
                value=state.get("principles_mode", "standard"),
                label="Preview Mode"
            )
            preview = gr.Textbox(
                value=_get_block(_detect_lang(shared), state.get("principles_mode", "standard")),
                lines=26,
                interactive=False,
                label="Principles Injection Text"
            )

            def _update_preview(v_mode):
                return _get_block(_detect_lang(shared), v_mode or "standard")

            preview_mode.change(_update_preview, [preview_mode], [preview])


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/principles] ready ✓")

_init()