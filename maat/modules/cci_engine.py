"""
CCI Engine Module  (cci_engine.py)
=================================

Critical Coherence Index runtime evaluation for MAAT-KI.

Purpose
-------
- Compute structural regime of responses:
    ordered / critical / chaotic
- Based on MAAT diagnostics (H, B, S, V, R)
- Provide signal for:
    - rewrite_loop
    - anti_hallu
    - reflection

Commands
--------
    /maat cci
    /maat cci on|off
    /maat cci eval <text>
"""

import math
import re
from typing import Dict, Any, Optional

try:
    import gradio as gr
except:
    gr = None


# ============================================================
# Defaults
# ============================================================

DEFAULTS = {
    "cci_enabled": True,
    "cci_kappa": 0.5,
    "cci_show_banner": False,
}

SESSION = {
    "last": None
}


# ============================================================
# Helpers
# ============================================================

def _clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


def _norm(text):
    return " ".join((text or "").lower().split())


def _word_count(text):
    return len(re.findall(r"\b\w+\b", text or ""))


def _sentence_count(text):
    return len([s for s in re.split(r"[.!?]+", text) if s.strip()])


# ============================================================
# Core components
# ============================================================

def _instability(text):
    wc = _word_count(text)
    sc = _sentence_count(text)

    val = 3.0

    if wc > 120:
        val += 2.0
    if sc > 6:
        val += 1.5

    if "!!!" in text or "???" in text:
        val += 1.5

    return _clamp(val)


def _production(text):
    t = _norm(text)

    keywords = [
        "idee", "beispiel", "struktur", "modell",
        "idea", "example", "structure", "model"
    ]

    val = 3.0 + sum(0.8 for k in keywords if k in t)

    return _clamp(val)


def _coherence(text):
    wc = _word_count(text)
    sc = _sentence_count(text)

    val = 5.0

    if 20 <= wc <= 180:
        val += 1.5
    if 1 <= sc <= 6:
        val += 1.5

    if "1." in text or "-" in text:
        val += 1.0

    return _clamp(val)


def _consistency(text):
    t = _norm(text)

    val = 6.0

    if "aber" in t or "jedoch" in t:
        val += 1.0

    if "immer" in t and "nie" in t:
        val -= 2.0

    return _clamp(val)


def _correctness(text):
    t = _norm(text)

    val = 6.5

    if "ich weiß nicht" in t or "nicht sicher" in t:
        val += 1.5

    if "definitiv" in t:
        val -= 1.5

    return _clamp(val)


def _integration(user_input, text):
    overlap = len(set(_norm(user_input).split()) & set(_norm(text).split()))
    val = 3.0 + overlap * 0.3
    return _clamp(val)


# ============================================================
# Main CCI
# ============================================================

def compute_cci(user_input: str, output: str, shared: dict, state: dict):
    eps = 0.01
    kappa = state.get("cci_kappa", 0.5)

    Γ_inst = _instability(output)
    Γ_prod = _production(output)
    Γ_coh  = _coherence(output)
    Γ_cons = _consistency(output)
    Γ_corr = _correctness(output)
    Γ_int  = _integration(user_input, output)

    # U_struct from MAAT engine
    try:
        m = shared.get("maat_engine", {}).get("last_eval")
        if m:
            vals = [m["H"], m["B"], m["S"], m["V"], m["R"]]
            mean = sum(vals)/5
            U_struct = sum((v-mean)**2 for v in vals)/5
        else:
            U_struct = 1.0
    except:
        U_struct = 1.0

    cci = (Γ_inst * Γ_prod * (1 + kappa * U_struct)) / (
        Γ_coh + Γ_cons + Γ_corr + Γ_int + eps
    )

    # regime classification
    if cci < 0.28:
        regime = "ordered"
    elif cci < 0.35:
        regime = "critical"
    else:
        regime = "chaotic"

    return {
        "CCI": round(cci, 4),
        "regime": regime,
        "components": {
            "inst": round(Γ_inst,2),
            "prod": round(Γ_prod,2),
            "coh": round(Γ_coh,2),
            "cons": round(Γ_cons,2),
            "corr": round(Γ_corr,2),
            "int": round(Γ_int,2),
            "U_struct": round(U_struct,3),
        },
        "text": f"CCI={cci:.4f} → {regime}"
    }


# ============================================================
# Hooks
# ============================================================

def on_load(state, shared, ext_dir):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)


def after_output(user_input, output, state_obj, state, shared):
    if not state.get("cci_enabled", True):
        return {}

    result = compute_cci(user_input, output, shared, state)
    SESSION["last"] = result

    shared.setdefault("cci_engine", {})
    shared["cci_engine"]["last"] = result

    # optional banner
    if state.get("cci_show_banner", False):
        return {"output": result["text"] + "\n\n" + output}

    return {}


# ============================================================
# Commands
# ============================================================

def handle_command(cmd, state, shared):
    cmd = (cmd or "").strip()

    if cmd == "/maat cci":
        last = SESSION.get("last")
        return last["text"] if last else "No CCI yet."

    if cmd == "/maat cci on":
        state["cci_enabled"] = True
        return "CCI enabled."

    if cmd == "/maat cci off":
        state["cci_enabled"] = False
        return "CCI disabled."

    m = re.match(r"^/maat cci eval\s+(.+)$", cmd)
    if m:
        result = compute_cci("", m.group(1), shared, state)
        return result["text"]

    return None


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/cci_engine] ready ✓")

_init()