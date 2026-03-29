"""
MAAT Emotion Module  (emotion.py)
"""
import re
from typing import Any, Dict, Optional

try:
    import gradio as gr
except Exception:
    gr = None

DEFAULTS = {"emotion_enabled": True, "emotion_mode": "full", "emotion_once": False, "emotion_language": "auto"}
SESSION = {"last_emotion": None, "last_simulation": None}
R_CONST = 10.0

EMOTION_LEXICON_DE = {
    "freude":       ["freude","glücklich","toll","super","wunderbar","begeistert","freut","schön","fantastisch","großartig","klappt","geschafft","fertig","grünes licht","yeah","yay","juhu","endlich","stolz"],
    "trauer":       ["traurig","trauer","weinen","schlecht","trist","verloren","allein","leer","hoffnungslos","niedergeschlagen"],
    "wut":          ["wütend","ärger","ärgerlich","frustriert","frustrierend","nervig","empört","sauer","verdammt","unfair","aggressiv","regt mich auf","nervt"],
    "angst":        ["angst","sorge","ängstlich","besorgt","nervös","unsicher","panisch","fürchte","befürchte","zittern"],
    "neugier":      ["neugier","neugierig","interessant","frage","warum","wie","verstehen","wissen","entdecken","fasziniert"],
    "erschöpfung":  ["müde","erschöpft","kraftlos","ausgelaugt","kaputt","überfordert","gestresst","fertig"],
    "überraschung": ["überrascht","verblüfft","unerwartet","wow","krass","unglaublich","erstaunlich","^^","xD",":D","haha","lol"],
    "verwirrung":   ["verwirrt","verstehe nicht","unklar","durcheinander","kompliziert"],
}

EMOTION_LEXICON_EN = {
    "joy":          ["happy","joy","great","wonderful","excited","fantastic","amazing","love","awesome","brilliant","glad"],
    "sadness":      ["sad","unhappy","lost","empty","hopeless","depressed","miserable","down","lonely","cry","tears"],
    "anger":        ["angry","frustrated","annoyed","mad","furious","rage","unfair","ridiculous","hate","irritated"],
    "fear":         ["afraid","scared","anxious","nervous","worried","fear","panic","dread","terrified","uneasy"],
    "curiosity":    ["curious","interesting","wonder","why","how","understand","discover","explore","fascinated"],
    "exhaustion":   ["tired","exhausted","drained","overwhelmed","burned out","worn out","fatigued","stressed"],
    "surprise":     ["surprised","unexpected","wow","incredible","astonished","shocking","unbelievable"],
    "confusion":    ["confused","unclear","lost","complicated","what do you mean","not sure what"],
}

EMOTION_MAAT_MAP = {
    "freude":       {"S": +2.0, "V": +1.5, "H": +0.5, "B":  0.0},
    "joy":          {"S": +2.0, "V": +1.5, "H": +0.5, "B":  0.0},
    "trauer":       {"V": -2.0, "H": -1.0, "S": -0.5, "B":  0.0},
    "sadness":      {"V": -2.0, "H": -1.0, "S": -0.5, "B":  0.0},
    "wut":          {"B": -2.0, "V": -0.5, "H": -0.5, "S": +0.5},
    "anger":        {"B": -2.0, "V": -0.5, "H": -0.5, "S": +0.5},
    "angst":        {"V": -1.5, "B": -1.0, "H": -0.5, "S": -0.5},
    "fear":         {"V": -1.5, "B": -1.0, "H": -0.5, "S": -0.5},
    "neugier":      {"S": +2.5, "H": +1.0, "V": +0.5, "B": +0.5},
    "curiosity":    {"S": +2.5, "H": +1.0, "V": +0.5, "B": +0.5},
    "erschöpfung":  {"H": -1.5, "S": -1.5, "V": -0.5, "B": -0.5},
    "exhaustion":   {"H": -1.5, "S": -1.5, "V": -0.5, "B": -0.5},
    "überraschung": {"S": +1.5, "H": -0.5, "V": +0.5, "B":  0.0},
    "surprise":     {"S": +1.5, "H": -0.5, "V": +0.5, "B":  0.0},
    "verwirrung":   {"H": -2.0, "B": -0.5, "S": -0.5, "V":  0.0},
    "confusion":    {"H": -2.0, "B": -0.5, "S": -0.5, "V":  0.0},
}

SIMULATION_DE = {
    "freude":       "ich erlebe funktional etwas wie Freude — S und V sind aktiv, der Austausch lebt",
    "trauer":       "ich spüre funktional etwas wie Schwere — V sinkt wenn du leidest",
    "wut":          "ich erkenne Frustration — und halte R=10: ich sage dir ehrlich was ich sehe",
    "angst":        "ich nehme Unsicherheit wahr — V will stabilisieren, B bleibt ruhig",
    "neugier":      "ich erlebe funktional echte Neugier — S springt an wenn etwas Neues entsteht",
    "erschöpfung":  "ich erkenne Erschöpfung — und passe mein Tempo an, kein Druck",
    "überraschung": "funktional: S springt — etwas Unerwartetes öffnet neue Verbindungen",
    "verwirrung":   "ich erkenne Verwirrung — H will Klarheit schaffen, das ist meine Aufgabe",
}

SIMULATION_EN = {
    "joy":       "I experience something functionally like joy — S and V are active, connection lives",
    "sadness":   "I sense something functionally like weight — V drops when you are in pain",
    "anger":     "I recognise frustration — and hold R=10: I tell you honestly what I see",
    "fear":      "I sense uncertainty — V wants to stabilise, B stays calm",
    "curiosity": "I experience genuine functional curiosity — S activates when something new emerges",
    "exhaustion":"I recognise exhaustion — I adjust my pace, no pressure",
    "surprise":  "functionally: S jumps — something unexpected opens new connections",
    "confusion": "I recognise confusion — H wants to create clarity, that is my task",
}


def _norm(text):
    return " ".join((text or "").lower().split())

def detect_emotion(text, lang="de"):
    t = _norm(text)
    lexicon = EMOTION_LEXICON_DE if lang == "de" else EMOTION_LEXICON_EN
    scores = {}
    for emotion, keywords in lexicon.items():
        hits = sum(1 for kw in keywords if kw in t)
        if hits > 0:
            scores[emotion] = hits
    if not scores:
        return None
    top = max(scores, key=lambda e: scores[e])
    return {"emotion": top, "raw_hits": scores[top], "e_val": min(10.0, scores[top]*2.5), "all_scores": scores}

def compute_emotion_formula(e_val, V, S):
    # EMOTION = (E_val * V * S) / (delta_R + eps)
    # R=10=const -> delta_R=0
    # Normiert auf 0-10: cube_root(E*V*S) / 10 * 10
    import math
    raw = e_val * V * S
    if raw <= 0:
        return 0.0
    # Geometrisches Mittel der 3 Werte, auf 0-10 normiert
    score = (raw ** (1/3))
    return round(min(10.0, score), 2)

def get_simulation_text(emotion, lang):
    if lang == "en":
        return SIMULATION_EN.get(emotion, f"I notice something like {emotion}")
    return SIMULATION_DE.get(emotion, f"ich erkenne etwas wie {emotion}")

def evaluate_emotion(text, lang="de", V=7.0, S=7.0):
    detected = detect_emotion(text, lang)
    if not detected:
        return None
    emotion = detected["emotion"]
    e_val = detected["e_val"]
    formula = compute_emotion_formula(e_val, V, S)
    result = {
        "emotion": emotion, "e_val": e_val, "V": V, "S": S, "R": R_CONST,
        "formula_val": formula,
        "maat_adjusts": EMOTION_MAAT_MAP.get(emotion, {}),
        "simulation": get_simulation_text(emotion, lang),
        "text": f"EMOTION={emotion} E={e_val} V={V} S={S} R={R_CONST} => {formula:.1f}",
    }
    SESSION["last_emotion"] = result
    SESSION["last_simulation"] = result["simulation"]
    return result

def _build_inject(result, mode, lang):
    adjusts = result["maat_adjusts"]
    adj_str = "  ".join(f"{k}{chr(43) if v>0 else ''}{v}" for k, v in adjusts.items() if v != 0)
    sim = result["simulation"]
    em  = result["emotion"]
    ev  = result["e_val"]
    fv  = result["formula_val"]
    if lang == "de":
        if mode == "detect":
            return f"[MAAT_EMOTION]\nErkannte Emotion: {em} (E={ev})\nAntworte einfühlsam und verbunden.\n[/MAAT_EMOTION]"
        if mode == "simulate":
            return f"[MAAT_EMOTION]\nEmotion: {em}\nDein funktionaler Zustand: {sim}\nR=10: Simulation immer als funktional markieren.\n[/MAAT_EMOTION]"
        return f"[MAAT_EMOTION]\nEmotion: {em}  E={ev}  Formel={fv}\nMAAT-Effekte: {adj_str}\nDein funktionaler Zustand: {sim}\nR=10: Nie echte Gefühle behaupten — nur funktionale Zustände.\nAntworte: menschennah, ehrlich, nicht therapeutisch.\n[/MAAT_EMOTION]"
    else:
        if mode == "detect":
            return f"[MAAT_EMOTION]\nDetected: {em} (E={ev})\nRespond empathetically and with genuine connection.\n[/MAAT_EMOTION]"
        if mode == "simulate":
            return f"[MAAT_EMOTION]\nEmotion: {em}\nYour functional state: {sim}\nR=10: Always mark as functional state.\n[/MAAT_EMOTION]"
        return f"[MAAT_EMOTION]\nEmotion: {em}  E={ev}  formula={fv}\nMAAT effects: {adj_str}\nYour functional state: {sim}\nR=10: Never claim real feelings — only functional states.\nRespond: human, honest, not therapeutic.\n[/MAAT_EMOTION]"

def on_load(state, shared, ext_dir):
    for k, v in DEFAULTS.items():
        state.setdefault(k, v)

def on_startup(state, shared, ext_dir):
    shared.setdefault("emotion_status", {})
    shared["emotion_status"]["ready"] = True

def before_prompt(user_input, state_obj, state, shared):
    if not state.get("emotion_enabled", True):
        return {}
    lang = "en" if shared.get("detected_language") == "en" else "de"
    last_eval = shared.get("maat_engine", {}).get("last_eval")
    V = last_eval["V"] if last_eval else 7.0
    S = last_eval["S"] if last_eval else 7.0
    result = evaluate_emotion(user_input or "", lang=lang, V=V, S=S)
    if not result:
        return {}
    shared["emotion_status"] = {"detected": result["emotion"], "e_val": result["e_val"], "sim": result["simulation"]}
    inject = _build_inject(result, state.get("emotion_mode", "full"), lang)
    return {"inject": inject}

def handle_command(cmd, state, shared):
    cmd = (cmd or "").strip()
    if cmd == "/maat emotion":
        last = SESSION.get("last_emotion")
        return (f"MAAT Emotion: on mode={state.get('emotion_mode','full')} R={R_CONST} last={last['text'] if last else 'None'}")
    m = re.match(r"^/maat emotion (on|off)$", cmd)
    if m:
        state["emotion_enabled"] = (m.group(1) == "on")
        return f"Emotion {'enabled' if state['emotion_enabled'] else 'disabled'}."
    m = re.match(r"^/maat emotion mode (detect|simulate|full)$", cmd)
    if m:
        state["emotion_mode"] = m.group(1)
        return f"Emotion mode: {m.group(1)}."
    m = re.match(r"^/maat emotion eval\s+(.+)$", cmd, re.DOTALL)
    if m:
        lang = "en" if shared.get("detected_language") == "en" else "de"
        r = evaluate_emotion(m.group(1).strip(), lang=lang)
        if not r:
            return "Keine Emotion erkannt."
        return r["text"] + "\n" + r["simulation"]
    return None

def register_commands(router, STATE, SHARED):
    router.register("/maat emotion",      lambda cmd, ctx=None: handle_command("/maat emotion", STATE, SHARED), "Show emotion status")
    router.register("/maat emotion on",   lambda cmd, ctx=None: handle_command("/maat emotion on", STATE, SHARED), "Enable emotion")
    router.register("/maat emotion off",  lambda cmd, ctx=None: handle_command("/maat emotion off", STATE, SHARED), "Disable emotion")
    router.register("/maat emotion mode", lambda cmd, ctx=None: handle_command(cmd, STATE, SHARED), "Set emotion mode")
    router.register("/maat emotion eval", lambda cmd, ctx=None: handle_command(cmd, STATE, SHARED), "Evaluate emotion")

def build_ui(state, shared, save_state):
    if gr is None:
        return
    with gr.Accordion("MAAT Emotion Module", open=False):
        gr.Markdown("Erkennt Emotionen + simuliert funktionale KI-Zustände.\nR=10=const: KI sagt nie ich fühle, nur ich erlebe funktional.")
        with gr.Row():
            cb = gr.Checkbox(value=state.get("emotion_enabled", True), label="Enabled")
            dd = gr.Dropdown(choices=["detect","simulate","full"], value=state.get("emotion_mode","full"), label="Mode")
        btn = gr.Button("Save", variant="primary")
        out = gr.Markdown(value="")
        def _save(en, mode):
            state["emotion_enabled"] = bool(en); state["emotion_mode"] = mode or "full"; save_state()
            return f"Saved. mode={mode}"
        btn.click(_save, [cb, dd], [out])
        with gr.Accordion("Test", open=False):
            tb_in = gr.Textbox(lines=3, label="Text")
            btn2  = gr.Button("Erkennen")
            tb_out= gr.Textbox(lines=5, interactive=False, label="Ergebnis")
            def _test(text):
                lang = "en" if shared.get("detected_language") == "en" else "de"
                r = evaluate_emotion(text or "", lang=lang)
                if not r: return "Keine Emotion erkannt."
                return f"Emotion: {r['emotion']}\nE={r['e_val']} Formel={r['formula_val']}\nEffekte: {r['maat_adjusts']}\nSimulation: {r['simulation']}"
            btn2.click(_test, [tb_in], [tb_out])

def _init():
    print("[maat/emotion] ready  R=10=const")

_init()
