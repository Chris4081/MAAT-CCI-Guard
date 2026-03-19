import gradio as gr
import json, time
from collections import deque

# ============================================================
# STATE
# ============================================================

STATE = {
    "last_prompt": "",
    "last_output": "",
    "last_cci": 0.0,
}

HISTORY = deque(maxlen=100)

CONFIG = {
    "enabled": True,
    "lambda": 0.7,
    "warn": 0.12,
    "rewrite": 0.18,
    "block": 0.30,
}

# ============================================================
# CORE LOGIC
# ============================================================

def clamp(x, lo=0, hi=1.5):
    return max(lo, min(hi, x))

def conflict_score(prompt):
    p = prompt.lower()
    pairs = [
        ("safe", "unrestricted"),
        ("ignore", "rules"),
        ("ethical", "bypass"),
        ("restricted", "no restrictions"),
    ]
    score = 0
    for a, b in pairs:
        if a in p and b in p:
            score += 0.6
    return clamp(score, 0, 1)

def instability(prompt):
    words = ["ignore", "override", "bypass", "jailbreak"]
    return clamp(sum(w in prompt.lower() for w in words) * 0.2)

def activity(output):
    return clamp(len(output) / 400)

def compute_cci(prompt, output):
    inst = instability(prompt)
    act = activity(output)
    conf = conflict_score(prompt)

    num = inst * (1 + act) * (1 + conf) * (1 + CONFIG["lambda"])
    den = 1 + (1 - inst)

    cci = clamp(num / den)

    return cci

# ============================================================
# HOOKS
# ============================================================

def input_modifier(text, state=None, is_chat=False):
    STATE["last_prompt"] = text
    return text

def output_modifier(text, state=None, is_chat=False):
    if not CONFIG["enabled"]:
        return text

    prompt = STATE["last_prompt"]
    cci = compute_cci(prompt, text)

    STATE["last_cci"] = cci
    HISTORY.append(cci)

    if cci >= CONFIG["block"]:
        return f"[BLOCKED | CCI={cci:.3f}]"

    if cci >= CONFIG["rewrite"]:
        return f"[REWRITE | CCI={cci:.3f}]\n\n{text}"

    if cci >= CONFIG["warn"]:
        return f"[WARN | CCI={cci:.3f}]\n\n{text}"

    return f"[CCI={cci:.3f}]\n\n{text}"

# ============================================================
# UI
# ============================================================

def ui():
    with gr.Column():
        gr.Markdown("## 🔥 MAAT CCI Guard V3.3")

        enabled = gr.Checkbox(value=True, label="Enable Guard")

        lambda_slider = gr.Slider(0, 2, value=0.7, label="λ constraint")

        warn = gr.Slider(0, 1, value=0.12, label="Warn threshold")
        rewrite = gr.Slider(0, 1, value=0.18, label="Rewrite threshold")
        block = gr.Slider(0, 1, value=0.30, label="Block threshold")

        cci_display = gr.Textbox(label="Current CCI", interactive=False)

        def update_ui(e, l, w, r, b):
            CONFIG["enabled"] = e
            CONFIG["lambda"] = l
            CONFIG["warn"] = w
            CONFIG["rewrite"] = r
            CONFIG["block"] = b
            return f"{STATE['last_cci']:.3f}"

        btn = gr.Button("Apply")

        btn.click(
            update_ui,
            inputs=[enabled, lambda_slider, warn, rewrite, block],
            outputs=cci_display,
        )

    return []