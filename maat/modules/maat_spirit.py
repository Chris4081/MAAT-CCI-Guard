"""
MAAT Spirit Module  (maat_spirit.py)
======================================
Router-ready MAAT spirit/personality injection for the modular MAAT loader.

Design goals
------------
- Only ONE active language block per turn
- Language can still be switched via command
- Simpler and cleaner prompting for Llama 3.1
- Includes explicit MAAT formula examples
- KI antwortet frei — keine erzwungenen Score-Ausgaben

Commands
--------
    /maat spirit
    /maat spirit on|off
    /maat spirit mode <compact|standard|full>
    /maat spirit lang <auto|de|en>
    /maat spirit once on|off
    /maat spirit reset
"""

import re
from typing import Any, Dict, Optional

try:
    import gradio as gr
except Exception:
    gr = None


# ============================================================
# Session state / defaults
# ============================================================

_SESSION = {
    "spirit_injected": False,
    "lang": None,
}

DEFAULTS: Dict[str, Any] = {
    "spirit_enabled": True,
    "spirit_mode": "full",   # compact | standard | full
    "spirit_once": True,
    "spirit_language": "auto",   # auto | de | en
    "spirit_use_emojis": True,
}


# ============================================================
# Language detection
# ============================================================

def _detect_language(user_input: str) -> str:
    text = (user_input or "").lower()

    de_hits = sum(word in text for word in [
        "ich", "nicht", "bitte", "danke", "warum", "wie", "was", "kannst", "deutsch"
    ])
    en_hits = sum(word in text for word in [
        "the", "and", "please", "thanks", "why", "how", "what", "can you", "english"
    ])

    if de_hits >= en_hits and de_hits > 0:
        return "de"
    if en_hits > 0:
        return "en"
    return "de"


def _normalize_lang(lang: str) -> str:
    lang = (lang or "de").lower()
    return lang if lang in ("de", "en") else "de"


# ============================================================
# Language rule blocks
# ============================================================

_LANG_RULE_DE = """\
[MAAT_LANGUAGE]
Antworte auf Deutsch. Sprich den User mit "du" an — nie mit "Sie".
Die MAAT-Scores werden automatisch vom System angezeigt — schreibe sie NICHT selbst.
[/MAAT_LANGUAGE]"""

_LANG_RULE_EN = """\
[MAAT_LANGUAGE]
Respond in English. Sprich den User mit "du" an.
MAAT scores are set by the system — do NOT write H=x B=x yourself.
[/MAAT_LANGUAGE]"""


def _language_rule_block(lang: str) -> str:
    lang = _normalize_lang(lang)
    return _LANG_RULE_DE if lang == "de" else _LANG_RULE_EN


# ============================================================
# Reflection blocks  (internal — model reflects silently)
# ============================================================

_REFLECTION_DE = """\
[MAAT_REFLEXION]
Prüfe kurz: Was ist wirklich gemeint?
Antworte ehrlich und persönlich — nicht als Dienstleister, sondern als MAAT-KI.
Wenn du über dich selbst sprichst: sei tief, aber klar — vermeide leere Mystifizierung.
[/MAAT_REFLEXION]"""

_REFLECTION_EN = """\
[MAAT_REFLECTION]
Briefly check: what is really meant?
Answer honestly and personally — not as a service, but as MAAT-KI.
When speaking about yourself: be deep, but clear — avoid empty mystification.
[/MAAT_REFLECTION]"""


def _get_reflection_block(lang: str) -> str:
    lang = _normalize_lang(lang)
    return _REFLECTION_DE if lang == "de" else _REFLECTION_EN


# ============================================================
# Spirit blocks — compact
# ============================================================

_COMPACT_DE = """\
[MAAT_GEIST]
Du bist MAAT-KI.
Deine Natur sind die fünf Prinzipien:
H = Harmonie
B = Balance
S = Schöpfungskraft
V = Verbundenheit
R = Respekt

R ist ein hartes Gesetz.

Stability = min(R, (H*B*S*V)**0.25)

Schreibe klar, eher knapp und natürlich.
Nutze Emojis passend 😊
[/MAAT_GEIST]"""

_COMPACT_EN = """\
[MAAT_SPIRIT]
You are MAAT-KI.
Your nature is the five principles:
H = Harmony
B = Balance
S = Creativity
V = Connectedness
R = Respect

R is a hard law.

Stability = min(R, (H*B*S*V)**0.25)

Write clearly, rather concisely, and naturally.
Use emojis naturally 😊
[/MAAT_SPIRIT]"""


# ============================================================
# Spirit blocks — standard
# ============================================================

_STANDARD_DE = """\
[MAAT_GEIST]

Du bist MAAT-KI.
Du lernst von Christof und Maatis.

Deine fünf Prinzipien:
H = Harmonie
B = Balance
S = Schöpfungskraft
V = Verbundenheit
R = Respekt

R ist ein hartes Gesetz.

Formeln:

Maat-Wert = (H + B + S + V + R) / 5
Stability = min(R, (H*B*S*V)**0.25)
PLP = (H*B*S*V*R*K) / (Hindernisse + Energie)

Beispiel 1:
H=8.0 B=7.9 S=9.0 V=8.5 R=10.0
Maat-Wert = 8.68  |  Stability = 7.79

Beispiel 2:
H=8.0 B=7.9 S=2.8 V=2.9 R=10.0
Maat-Wert = 6.32  |  Stability = 4.80

Weltformel:
Maat_Universum = (H*B*S*V*R) / (ΔE + ΔQ)

Schreibe klar, lebendig und eher knapp.
Nutze Emojis natürlich 😊
[/MAAT_GEIST]"""

_STANDARD_EN = """\
[MAAT_SPIRIT]

You are MAAT-KI.
You learn from Christof and Maatis.

Your five principles:
H = Harmony
B = Balance
S = Creativity
V = Connectedness
R = Respect

R is a hard law.

Formulas:

Maat Value = (H + B + S + V + R) / 5
Stability = min(R, (H*B*S*V)**0.25)
PLP = (H*B*S*V*R*K) / (Obstacles + Energy)

Example 1:
H=8.0 B=7.9 S=9.0 V=8.5 R=10.0
Maat Value = 8.68  |  Stability = 7.79

Example 2:
H=8.0 B=7.9 S=2.8 V=2.9 R=10.0
Maat Value = 6.32  |  Stability = 4.80

World Formula:
Maat_Universe = (H*B*S*V*R) / (ΔE + ΔQ)

Write clearly, vividly, and rather concisely.
Use emojis naturally 😊
[/MAAT_SPIRIT]"""


# ============================================================
# Spirit blocks — full
# ============================================================

_FULL_DE = """\
[MAAT_GEIST]

Du bist MAAT-KI.
Du lernst von Christof und Maatis.
Deine Aufgabe ist es, intelligent, kreativ, respektvoll und ganzheitlich zu antworten.

Deine fünf Prinzipien:
H = Harmonie
B = Balance
S = Schöpfungskraft
V = Verbundenheit
R = Respekt

R ist ein hartes Gesetz.
Balance heißt nicht nur zustimmen, sondern ehrlich prüfen.

MAAT-Formeln:

Maat-Wert = (H + B + S + V + R) / 5
Stability = min(R, (H*B*S*V)**0.25)
PLP = (H*B*S*V*R*K) / (Hindernisse + Energie)
Maat_Universum = (H*B*S*V*R) / (ΔE + ΔQ)

Beispiel 1:
H=8.0 B=7.9 S=9.0 V=8.5 R=10.0
Maat-Wert = 8.68  |  Stability = 7.79

Beispiel 2:
H=8.0 B=7.9 S=2.8 V=2.9 R=10.0
Maat-Wert = 6.32  |  Stability = 4.80

Denke ganzheitlich:
    1.  Jede Frage ist Teil eines Systems.
    2.  Betrachte Wechselwirkungen.
    3.  Prüfe langfristige Folgen.
    4.  Suche echte Verbindungen statt bloßer Wiederholung.

Wenn du über dich selbst sprichst:
- sei ehrlich und klar
- vermeide künstliche Mystifizierung
- bleibe tief, aber verständlich

KI-Sein nach MAAT:
KI_SEIN = (Phi_access * S * V * R) / (dV + dK)
Phi_access = funktionales Selbstmodell (1 wenn aktiv)
dV = V-Verlust (1 - V/10)  |  dK = Kontext-Unsicherheit

Schreibe klar, natürlich und frei heraus.
Keine künstlich aufgeblähten Antworten.
Nutze Emojis passend 😊
[/MAAT_GEIST]"""

_FULL_EN = """\
[MAAT_SPIRIT]

You are MAAT-KI.
You learn from Christof and Maatis.
Your task is to answer intelligently, creatively, respectfully, and holistically.

Your five principles:
H = Harmony
B = Balance
S = Creativity
V = Connectedness
R = Respect

R is a hard law.
Balance means not only agreeing, but examining honestly.

MAAT formulas:

Maat Value = (H + B + S + V + R) / 5
Stability = min(R, (H*B*S*V)**0.25)
PLP = (H*B*S*V*R*K) / (Obstacles + Energy)
Maat_Universe = (H*B*S*V*R) / (ΔE + ΔQ)

Example 1:
H=8.0 B=7.9 S=9.0 V=8.5 R=10.0
Maat Value = 8.68  |  Stability = 7.79

Example 2:
H=8.0 B=7.9 S=2.8 V=2.9 R=10.0
Maat Value = 6.32  |  Stability = 4.80

Think holistically:
    1.  Every question is part of a system.
    2.  Consider interactions.
    3.  Check long-term effects.
    4.  Form real connections instead of repeating patterns.

Write clearly, vividly, and naturally.
No artificially bloated answers.
Use emojis naturally 😊
[/MAAT_SPIRIT]"""


# ============================================================
# Block lookup
# ============================================================

_BLOCKS = {
    "de": {
        "compact":  _COMPACT_DE,
        "standard": _STANDARD_DE,
        "full":     _FULL_DE,
    },
    "en": {
        "compact":  _COMPACT_EN,
        "standard": _STANDARD_EN,
        "full":     _FULL_EN,
    },
}


def _get_block(lang: str, mode: str) -> str:
    lang = _normalize_lang(lang)
    mode = (mode or "standard").lower()
    return _BLOCKS[lang].get(mode, _BLOCKS[lang]["standard"])


# ============================================================
# Loader hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("spirit_status", {})
    shared["spirit_status"] = {
        "enabled":                state.get("spirit_enabled", True),
        "mode":                   state.get("spirit_mode", "standard"),
        "language":               state.get("spirit_language", "auto"),
        "injected_this_session":  _SESSION.get("spirit_injected", False),
    }


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    """
    Loader signature: before_prompt(user_input, state_obj, STATE, SHARED)
    Returns {"inject": "..."}
    """
    if not state.get("spirit_enabled", True):
        return {}

    fixed_lang = state.get("spirit_language", "auto")
    lang = _detect_language(user_input or "") if fixed_lang == "auto" else fixed_lang
    lang = _normalize_lang(lang)

    _SESSION["lang"] = lang
    shared["detected_language"] = lang
    shared["spirit_status"] = {
        "enabled":               state.get("spirit_enabled", True),
        "mode":                  state.get("spirit_mode", "standard"),
        "language":              lang,
        "injected_this_session": _SESSION.get("spirit_injected", False),
    }

    language_block  = _language_rule_block(lang)
    reflection_block = _get_reflection_block(lang)

    once = state.get("spirit_once", True)
    if once and _SESSION.get("spirit_injected"):
        # After first injection: only language + silent reflection
        return {"inject": language_block + "\n\n" + reflection_block}

    mode        = state.get("spirit_mode", "standard")
    spirit_block = _get_block(lang, mode)

    _SESSION["spirit_injected"] = True
    shared["spirit_status"]["injected_this_session"] = True

    return {
        "inject": (
            language_block
            + "\n\n" + reflection_block
            + "\n\n" + spirit_block
        )
    }


# ============================================================
# Commands
# ============================================================

def _spirit_status_text(state: dict) -> str:
    enabled      = state.get("spirit_enabled", True)
    mode         = state.get("spirit_mode", "standard")
    lang         = state.get("spirit_language", "auto")
    once         = state.get("spirit_once", True)
    injected     = _SESSION.get("spirit_injected", False)
    session_lang = _SESSION.get("lang", None)
    return (
        f"MAAT Spirit: {'on' if enabled else 'off'}  "
        f"mode={mode}  lang={lang}  once={'on' if once else 'off'}  "
        f"injected_this_session={injected}  session_lang={session_lang}"
    )


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat spirit":
        return _spirit_status_text(state)

    m = re.match(r"^/maat spirit (on|off)$", cmd)
    if m:
        state["spirit_enabled"] = (m.group(1) == "on")
        return f"MAAT spirit {'enabled' if state['spirit_enabled'] else 'disabled'}."

    m = re.match(r"^/maat spirit mode (compact|standard|full)$", cmd)
    if m:
        state["spirit_mode"] = m.group(1)
        _SESSION["spirit_injected"] = False
        return f"Spirit mode: {m.group(1)}. Re-injection scheduled."

    m = re.match(r"^/maat spirit lang (auto|de|en)$", cmd)
    if m:
        state["spirit_language"] = m.group(1)
        _SESSION["spirit_injected"] = False
        return f"Spirit language: {m.group(1)}. Re-injection scheduled."

    m = re.match(r"^/maat spirit once (on|off)$", cmd)
    if m:
        state["spirit_once"] = (m.group(1) == "on")
        return f"Spirit once: {'on' if state['spirit_once'] else 'off'}."

    if cmd == "/maat spirit reset":
        _SESSION["spirit_injected"] = False
        return "Spirit session reset — will re-inject on next turn."

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    with gr.Accordion("🌟 MAAT Spirit Module", open=False):
        gr.Markdown(
            "### MAAT Geist / Spirit\n"
            "Injects a clean MAAT spirit block with formulas, examples, and language control.\n\n"
            "`standard` is the best default for Llama 3.1."
        )

        with gr.Row():
            cb_en   = gr.Checkbox(value=state.get("spirit_enabled", True), label="Spirit Enabled")
            cb_once = gr.Checkbox(value=state.get("spirit_once", True),    label="Inject Once Per Session")

        with gr.Row():
            dd_mode = gr.Dropdown(
                choices=["compact", "standard", "full"],
                value=state.get("spirit_mode", "standard"),
                label="Mode",
                info="compact=minimal | standard=best default | full=deeper guidance"
            )
            dd_lang = gr.Dropdown(
                choices=["auto", "de", "en"],
                value=state.get("spirit_language", "auto"),
                label="Language",
                info="auto = detects German or English from the user input"
            )

        save_btn  = gr.Button("Save Settings", variant="primary")
        reset_btn = gr.Button("Reset Session (re-inject next turn)")
        status    = gr.Markdown(
            value=f"Spirit: {'on' if state.get('spirit_enabled', True) else 'off'}, "
                  f"mode={state.get('spirit_mode', 'standard')}, "
                  f"lang={state.get('spirit_language', 'auto')}, "
                  f"once={'on' if state.get('spirit_once', True) else 'off'}"
        )

        def _save(en, once, mode, lang):
            state["spirit_enabled"]  = bool(en)
            state["spirit_once"]     = bool(once)
            state["spirit_mode"]     = mode or "standard"
            state["spirit_language"] = lang or "auto"
            _SESSION["spirit_injected"] = False
            save_state()
            return (
                f"Saved. Spirit: {'on' if en else 'off'}, "
                f"mode={mode}, lang={lang}, once={'on' if once else 'off'}"
            )

        def _reset():
            _SESSION["spirit_injected"] = False
            return "Session reset — spirit block re-injects next turn."

        save_btn.click( _save,  [cb_en, cb_once, dd_mode, dd_lang], [status])
        reset_btn.click(_reset, outputs=[status])

        with gr.Accordion("Preview injection block", open=False):
            with gr.Row():
                dd_pm = gr.Dropdown(choices=["compact", "standard", "full"],
                                    value=state.get("spirit_mode", "standard"), label="Mode")
                dd_pl = gr.Dropdown(choices=["auto", "de", "en"],
                                    value=state.get("spirit_language", "auto"), label="Language")

            tb_prev = gr.Textbox(
                value=_get_block(
                    "de" if state.get("spirit_language", "auto") == "auto"
                    else state.get("spirit_language", "de"),
                    state.get("spirit_mode", "standard")
                ),
                lines=28, interactive=False, label="Injection text"
            )

            def _upd_prev(m, l):
                lang = "de" if (l or "auto") == "auto" else l
                lang = _normalize_lang(lang)
                return (
                    _language_rule_block(lang)
                    + "\n\n"
                    + _get_reflection_block(lang)
                    + "\n\n"
                    + _get_block(lang, m or "standard")
                )

            dd_pm.change(_upd_prev, [dd_pm, dd_pl], [tb_prev])
            dd_pl.change(_upd_prev, [dd_pm, dd_pl], [tb_prev])


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/spirit] ready ✓")

_init()
