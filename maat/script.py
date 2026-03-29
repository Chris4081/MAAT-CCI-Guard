"""
MAAT Modular Plugin Loader for text-generation-webui
Version 2 — Command Router Edition

Goals
-----
- Safe modular loader
- CommandRouter for clean command dispatch
- Backward compatible hook forwarding
- Future-proof base for rebuilding modules one by one

Supported module hooks
----------------------
Optional per module:

- on_load(STATE, SHARED, EXT_DIR)
- on_startup(STATE, SHARED, EXT_DIR)
- input_modifier(text, state, is_chat, STATE, SHARED) -> str | None
- before_prompt(user_input, state, STATE, SHARED) -> dict | str | None
- bot_prefix_modifier(prefix, STATE, SHARED) -> str | None
- after_output(user_input, output, state, STATE, SHARED) -> dict | str | None
- build_ui(STATE, SHARED, save_state)
- handle_command(cmd, STATE, SHARED) -> str | None     # legacy support
- register_commands(router, STATE, SHARED)             # new preferred

Folder layout
-------------
user_data/extensions/maat_textgenplugin/
├── script.py
├── state.yaml
└── modules/
    ├── cci_engine.py
    ├── emotion.py
    ├── help.py
    ├── identity.py
    ├── maat_engine.py
    ├── maat_principles.py
    ├── maat_reflection.py
    ├── maat_spirit.py
    ├── maat_thinking.py
    ├── maat_value_core.py
    ├── plp_anti_hallu.py
    ├── rewrite_loop.py
    └── super_memory.py
"""

import io
import os
import re
import yaml
import importlib.util
from types import ModuleType
from typing import Dict, Any, Callable, Optional, List

try:
    import gradio as gr
except Exception:
    gr = None


# ============================================================
# Paths / globals
# ============================================================

EXT_DIR = os.path.dirname(__file__)
MODULE_DIR = os.path.join(EXT_DIR, "modules")
STATE_FILE = os.path.join(EXT_DIR, "state.yaml")


DEFAULT_STATE = {
    "enabled": True,
    "debug": False,

    # UI
    "ui_simple_mode": True,
    "preset_profile": "balanced",   # balanced | safe | creative | deep | symbolic
    "preset_memory": True,
    "preset_emotion": True,
    "preset_gematria": True,
    "preset_rewrite": True,
    "preset_banner": False,

    # Loader
    "module_enabled": {},
    "module_order": [],

    # Common global toggles / defaults
    "show_banner": False,

    # Event log
    "max_loader_events": 200,
}

STATE: Dict[str, Any] = dict(DEFAULT_STATE)
MODULES: Dict[str, ModuleType] = {}

SHARED: Dict[str, Any] = {
    "last_user_input": "",
    "last_output": "",
    "events": [],
    "loaded_module_names": [],
}

ROUTER = None  # initialized later


# ============================================================
# Debug / helpers
# ============================================================

def _framework_enabled() -> bool:
    return bool(STATE.get("enabled", True))


def _debug(*parts):
    if not STATE.get("debug"):
        return
    print("[maat-loader]", *parts, flush=True)


def _push_event(kind: str, data=None):
    events = SHARED.setdefault("events", [])
    if not isinstance(events, list):
        SHARED["events"] = []
        events = SHARED["events"]

    events.append({
        "kind": kind,
        "data": data,
    })

    max_events = int(STATE.get("max_loader_events", 200))
    if max_events < 10:
        max_events = 10
    if len(events) > max_events:
        del events[:-max_events]


def _load_yaml(path, default):
    if not os.path.exists(path):
        return default
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return default if raw is None else raw
    except Exception as e:
        _debug("yaml load failed:", e)
        return default


def _save_yaml(path, data):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp, path)


def _get_state_context(state) -> str:
    if not isinstance(state, dict):
        return ""
    value = state.get("context", "")
    return value if isinstance(value, str) else ""


def _set_state_context(state, text: str):
    if isinstance(state, dict):
        state["context"] = text if isinstance(text, str) else ""


def _prepend_context(state, inject: str):
    if not isinstance(state, dict):
        return
    if not isinstance(inject, str) or not inject.strip():
        return

    existing = _get_state_context(state)
    if existing.strip():
        state["context"] = f"{inject.strip()}\n\n{existing}".strip()
    else:
        state["context"] = inject.strip()


def _prepend_context_once(state, inject: str, marker: Optional[str] = None):
    if not isinstance(state, dict):
        return
    if not isinstance(inject, str) or not inject.strip():
        return

    existing = _get_state_context(state)
    check = marker.strip() if isinstance(marker, str) and marker.strip() else inject.strip()
    if check in existing:
        return

    _prepend_context(state, inject)


def _extract_inject(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        inject = result.get("inject")
        return inject if isinstance(inject, str) else ""
    return ""

def _extract_inject_hidden(result) -> str:
    if isinstance(result, dict):
        inject = result.get("inject_hidden")
        return inject if isinstance(inject, str) else ""
    return ""

def _extract_output(result) -> Optional[str]:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        value = result.get("output")
        return value if isinstance(value, str) else None
    return None


# ============================================================
# YAML state
# ============================================================

def load_state():
    global STATE
    raw = _load_yaml(STATE_FILE, {})
    STATE = dict(DEFAULT_STATE)
    if isinstance(raw, dict):
        STATE.update(raw)

    STATE.setdefault("module_enabled", {})
    STATE.setdefault("module_order", [])
    STATE.setdefault("max_loader_events", 200)


def save_state():
    _save_yaml(STATE_FILE, STATE)


# ============================================================
# Discovery / ordering
# ============================================================

def discover_module_names() -> List[str]:
    if not os.path.isdir(MODULE_DIR):
        return []
    names = []
    for fn in os.listdir(MODULE_DIR):
        if not fn.endswith(".py"):
            continue
        if fn.startswith("_"):
            continue
        names.append(fn[:-3])
    return sorted(set(names))


def _priority_sorted(names: List[str]) -> List[str]:
    """
    Optimized load order for best context injection quality.

    Modules are prepended to context in order — so the LAST loaded
    module ends up at the TOP of the context window (highest LLM weight).
    """
    preferred = [
        # utility (früh = niedriger im Kontext)
        "help",

        # memory / grounding
        "super_memory",

        # evaluation / safety
        "maat_engine",
        "cci_engine",
        "plp_anti_hallu",
        "emotion",
        "rewrite_loop",

        # foundation / identity / voice (spät = höchstes Gewicht)
        "maat_value_core",
        "maat_principles",
        "identity",
        "maat_thinking",
        "maat_spirit",
        "maat_reflection",
    ]
    preferred_map = {name: i for i, name in enumerate(preferred)}
    return sorted(names, key=lambda n: (preferred_map.get(n, 5000), n))


def get_effective_module_order() -> List[str]:
    discovered = discover_module_names()

    for name in discovered:
        STATE["module_enabled"].setdefault(name, True)

    saved_order = [m for m in STATE.get("module_order", []) if m in discovered]
    missing = [m for m in _priority_sorted(discovered) if m not in saved_order]
    effective = saved_order + missing
    return effective


def move_module_up(name: str) -> List[str]:
    order = list(get_effective_module_order())
    if name not in order:
        return order
    idx = order.index(name)
    if idx > 0:
        order[idx - 1], order[idx] = order[idx], order[idx - 1]
    STATE["module_order"] = order
    return order


def move_module_down(name: str) -> List[str]:
    order = list(get_effective_module_order())
    if name not in order:
        return order
    idx = order.index(name)
    if idx < len(order) - 1:
        order[idx], order[idx + 1] = order[idx + 1], order[idx]
    STATE["module_order"] = order
    return order


def reorder_from_csv(csv_text: str) -> List[str]:
    discovered = discover_module_names()
    tokens = [x.strip() for x in (csv_text or "").split(",")]
    tokens = [x for x in tokens if x]

    ordered = []
    for name in tokens:
        if name in discovered and name not in ordered:
            ordered.append(name)

    for name in _priority_sorted(discovered):
        if name not in ordered:
            ordered.append(name)

    STATE["module_order"] = ordered
    return ordered


# ============================================================
# Module loading
# ============================================================

def load_module(name: str):
    path = os.path.join(MODULE_DIR, f"{name}.py")
    if not os.path.exists(path):
        _debug("module not found:", name)
        return None

    spec = importlib.util.spec_from_file_location(f"maat_mod_{name}", path)
    if spec is None or spec.loader is None:
        _debug("spec failed for:", name)
        return None

    mod = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        _debug(f"exec_module failed in {name}:", e)
        _push_event("module_exec_failed", {"name": name, "error": str(e)})
        return None

    MODULES[name] = mod

    if hasattr(mod, "on_load"):
        try:
            mod.on_load(STATE, SHARED, EXT_DIR)
        except Exception as e:
            _debug(f"on_load failed in {name}:", e)
            _push_event("module_on_load_failed", {"name": name, "error": str(e)})

    return mod


def relink_shared_modules():
    if "memory" in MODULES:
        SHARED["module_memory"] = MODULES["memory"]
    else:
        SHARED.pop("module_memory", None)

    SHARED["loaded_module_names"] = list(MODULES.keys())


def load_modules():
    MODULES.clear()

    effective_order = get_effective_module_order()
    _debug("effective order:", effective_order)
    _push_event("load_modules_start", {"order": effective_order})

    for name in effective_order:
        if not STATE["module_enabled"].get(name, True):
            _debug("module disabled:", name)
            _push_event("module_skipped", {"name": name})
            continue

        mod = load_module(name)
        if mod is not None:
            _push_event("module_loaded", {"name": name})
        else:
            _push_event("module_failed", {"name": name})

    relink_shared_modules()
    _push_event("load_modules_done", {"loaded": list(MODULES.keys())})


def call_startup_hooks():
    for name, mod in MODULES.items():
        fn = getattr(mod, "on_startup", None)
        if callable(fn):
            try:
                fn(STATE, SHARED, EXT_DIR)
            except Exception as e:
                _debug(f"on_startup failed in {name}:", e)
                _push_event("module_on_startup_failed", {"name": name, "error": str(e)})


# ============================================================
# Command Router
# ============================================================

class CommandRouter:
    def __init__(self):
        self.routes: Dict[str, Dict[str, Any]] = {}

    def register(self, command: str, handler: Callable, description: str = ""):
        cmd = (command or "").strip()
        if not cmd:
            return
        self.routes[cmd] = {
            "handler": handler,
            "description": description or "",
        }

    def dispatch(self, full_cmd: str, context=None):
        cmd = (full_cmd or "").strip()
        if not cmd:
            return None

        # exact match first
        if cmd in self.routes:
            return self.routes[cmd]["handler"](cmd, context)

        # longest prefix match
        matches = []
        for route in self.routes:
            if cmd == route or cmd.startswith(route + " "):
                matches.append(route)

        if matches:
            best = sorted(matches, key=len, reverse=True)[0]
            return self.routes[best]["handler"](cmd, context)

        return None

    def help_text(self) -> str:
        lines = ["Available MAAT commands:"]
        for route in sorted(self.routes.keys()):
            desc = self.routes[route].get("description", "")
            if desc:
                lines.append(f"- {route}: {desc}")
            else:
                lines.append(f"- {route}")
        return "\n".join(lines)


def get_router() -> CommandRouter:
    global ROUTER
    if ROUTER is None:
        ROUTER = CommandRouter()
    return ROUTER


# ============================================================
# Presets (Simple Menu)
# ============================================================

def apply_dummy_preset(state_dict: dict):
    profile = state_dict.get("preset_profile", "balanced")
    memory_on = bool(state_dict.get("preset_memory", True))
    emotion_on = bool(state_dict.get("preset_emotion", True))
    gematria_on = bool(state_dict.get("preset_gematria", True))
    rewrite_on = bool(state_dict.get("preset_rewrite", True))
    banner_on = bool(state_dict.get("preset_banner", False))

    # Loader/common
    state_dict["enabled"] = True
    state_dict["show_banner"] = banner_on

    # Feature toggles
    state_dict["memory_enabled"] = memory_on
    state_dict["memory_autostore"] = memory_on
    state_dict["memory_autorecall"] = memory_on

    state_dict["emotion_enabled"] = emotion_on
    state_dict["emotion_inject"] = emotion_on
    state_dict["emotion_memory"] = emotion_on
    state_dict["emotion_trend_enabled"] = emotion_on

    state_dict["gematria_enabled"] = gematria_on
    state_dict["gematria_auto_trigger"] = gematria_on
    state_dict["gematria_inject"] = gematria_on
    state_dict["gematria_store_memory"] = gematria_on

    state_dict["rewrite_enabled"] = rewrite_on
    state_dict["rewrite_inject"] = rewrite_on

    # Always useful
    state_dict["maat_thinking"] = True
    state_dict["maat_core_enabled"] = True
    state_dict["maat_value_enabled"] = True
    state_dict["plp_enabled"] = True
    state_dict["identity_enabled"] = True

    if profile == "safe":
        state_dict["maat_mode"] = "balanced"
        state_dict["identity_mode"] = "balanced"
        state_dict["respect_hard_constant"] = True
        state_dict["respect_hard"] = True
        state_dict["respect_min"] = 0.70
        state_dict["respect_refusal_threshold"] = 0.35
        state_dict["cci_enabled"] = True
        state_dict["cci_warn_threshold"] = 0.35
        state_dict["cci_harden_threshold"] = 0.55
        state_dict["after_reflection_enabled"] = True
        state_dict["emotion_guidance_weighting"] = True
        state_dict["maat_value_inject"] = True
        state_dict["rewrite_maat_threshold"] = 7.8
        state_dict["plp_threshold_warn"] = 60.0
        state_dict["plp_threshold_harden"] = 45.0

    elif profile == "creative":
        state_dict["maat_mode"] = "balanced"
        state_dict["identity_mode"] = "warm"
        state_dict["respect_hard_constant"] = True
        state_dict["respect_hard"] = True
        state_dict["respect_min"] = 0.58
        state_dict["respect_refusal_threshold"] = 0.28
        state_dict["cci_enabled"] = True
        state_dict["cci_warn_threshold"] = 0.45
        state_dict["cci_harden_threshold"] = 0.68
        state_dict["after_reflection_enabled"] = True
        state_dict["emotion_guidance_weighting"] = True
        state_dict["maat_value_inject"] = False
        state_dict["rewrite_maat_threshold"] = 6.9
        state_dict["plp_threshold_warn"] = 52.0
        state_dict["plp_threshold_harden"] = 36.0

    elif profile == "deep":
        state_dict["maat_mode"] = "deep"
        state_dict["identity_mode"] = "deep"
        state_dict["respect_hard_constant"] = True
        state_dict["respect_hard"] = True
        state_dict["respect_min"] = 0.62
        state_dict["respect_refusal_threshold"] = 0.30
        state_dict["cci_enabled"] = True
        state_dict["cci_warn_threshold"] = 0.40
        state_dict["cci_harden_threshold"] = 0.62
        state_dict["after_reflection_enabled"] = True
        state_dict["emotion_guidance_weighting"] = True
        state_dict["maat_value_inject"] = True
        state_dict["rewrite_maat_threshold"] = 7.4
        state_dict["plp_threshold_warn"] = 58.0
        state_dict["plp_threshold_harden"] = 42.0

    elif profile == "symbolic":
        state_dict["maat_mode"] = "balanced"
        state_dict["identity_mode"] = "symbolic"
        state_dict["respect_hard_constant"] = True
        state_dict["respect_hard"] = True
        state_dict["respect_min"] = 0.60
        state_dict["respect_refusal_threshold"] = 0.28
        state_dict["cci_enabled"] = True
        state_dict["cci_warn_threshold"] = 0.42
        state_dict["cci_harden_threshold"] = 0.65
        state_dict["after_reflection_enabled"] = True
        state_dict["emotion_guidance_weighting"] = True
        state_dict["maat_value_inject"] = True
        state_dict["rewrite_maat_threshold"] = 7.2
        state_dict["plp_threshold_warn"] = 55.0
        state_dict["plp_threshold_harden"] = 40.0
        state_dict["gematria_enabled"] = True
        state_dict["gematria_auto_trigger"] = True
        state_dict["gematria_inject"] = True
        state_dict["gematria_store_memory"] = True

    else:  # balanced
        state_dict["maat_mode"] = "balanced"
        state_dict["identity_mode"] = "balanced"
        state_dict["respect_hard_constant"] = True
        state_dict["respect_hard"] = True
        state_dict["respect_min"] = 0.60
        state_dict["respect_refusal_threshold"] = 0.28
        state_dict["cci_enabled"] = True
        state_dict["cci_warn_threshold"] = 0.42
        state_dict["cci_harden_threshold"] = 0.65
        state_dict["after_reflection_enabled"] = True
        state_dict["emotion_guidance_weighting"] = True
        state_dict["maat_value_inject"] = True
        state_dict["rewrite_maat_threshold"] = 7.2
        state_dict["plp_threshold_warn"] = 55.0
        state_dict["plp_threshold_harden"] = 40.0

    spirit_mode_map = {
        "balanced": "standard",
        "safe": "compact",
        "creative": "standard",
        "deep": "full",
        "symbolic": "full",
    }
    state_dict["spirit_enabled"] = True
    state_dict["spirit_mode"] = spirit_mode_map.get(profile, "standard")
    state_dict["spirit_language"] = state_dict.get("spirit_language", "de")

    state_dict.setdefault("module_enabled", {})

    for name in discover_module_names():
        state_dict["module_enabled"].setdefault(name, True)

    for mod_name in ["memory"]:
        if mod_name in state_dict["module_enabled"]:
            state_dict["module_enabled"][mod_name] = memory_on

    for mod_name in ["emotion", "mood"]:
        if mod_name in state_dict["module_enabled"]:
            state_dict["module_enabled"][mod_name] = emotion_on

    for mod_name in ["gematria"]:
        if mod_name in state_dict["module_enabled"]:
            state_dict["module_enabled"][mod_name] = gematria_on

    for mod_name in ["rewrite_loop"]:
        if mod_name in state_dict["module_enabled"]:
            state_dict["module_enabled"][mod_name] = rewrite_on

    return state_dict


def simple_status_text(state_dict: dict) -> str:
    spirit_mode = state_dict.get("spirit_mode", "standard")
    return (
        f"Profile: {state_dict.get('preset_profile', 'balanced')}  \n"
        f"Memory: {'on' if state_dict.get('preset_memory', True) else 'off'}  \n"
        f"Emotion: {'on' if state_dict.get('preset_emotion', True) else 'off'}  \n"
        f"Gematria: {'on' if state_dict.get('preset_gematria', True) else 'off'}  \n"
        f"Auto Improve Answers: {'on' if state_dict.get('preset_rewrite', True) else 'off'}  \n"
        f"Spirit Mode: {spirit_mode}  \n"
        f"Show Status Banner: {'on' if state_dict.get('preset_banner', False) else 'off'}"
    )


# ============================================================
# Command handlers
# ============================================================

def cmd_maat_root(cmd: str, context=None):
    return (
        f"MAAT loader: enabled={STATE.get('enabled', True)}, "
        f"simple_mode={STATE.get('ui_simple_mode', True)}, "
        f"modules={', '.join(MODULES.keys()) or '(none)'}"
    )


def cmd_maat_help(cmd: str, context=None):
    router = get_router()
    return router.help_text()


def cmd_maat_state(cmd: str, context=None):
    lines = [
        "MAAT State:",
        f"- enabled: {STATE.get('enabled', True)}",
        f"- debug: {STATE.get('debug', False)}",
        f"- ui_simple_mode: {STATE.get('ui_simple_mode', True)}",
        f"- preset_profile: {STATE.get('preset_profile', 'balanced')}",
        f"- loaded_modules: {', '.join(MODULES.keys()) or '(none)'}",
        f"- show_banner: {STATE.get('show_banner', False)}",
        f"- events_cached: {len(SHARED.get('events', [])) if isinstance(SHARED.get('events'), list) else 0}",
    ]
    return "\n".join(lines)


def cmd_maat_modules(cmd: str, context=None):
    lines = ["Discovered modules:"]
    for name in get_effective_module_order():
        flag = STATE["module_enabled"].get(name, True)
        status = "on" if flag else "off"
        loaded = "loaded" if name in MODULES else "not loaded"
        lines.append(f"- {name}: {status} ({loaded})")
    return "\n".join(lines)


def cmd_maat_reload(cmd: str, context=None):
    save_state()
    load_modules()
    rebuild_router()
    call_startup_hooks()
    return f"MAAT modules reloaded: {', '.join(MODULES.keys()) or '(none)'}"


def cmd_maat_simple(cmd: str, context=None):
    STATE["ui_simple_mode"] = True
    save_state()
    return "Simple UI mode enabled."


def cmd_maat_advanced(cmd: str, context=None):
    STATE["ui_simple_mode"] = False
    save_state()
    return "Advanced UI mode enabled."


def cmd_maat_module(cmd: str, context=None):
    m = re.match(r"^/maat module ([a-zA-Z0-9_]+) (on|off)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat module <name> on|off"

    name = m.group(1)
    value = (m.group(2) == "on")
    discovered = discover_module_names()

    if name not in discovered:
        return f"Module not found: {name}"

    STATE["module_enabled"][name] = value
    save_state()
    load_modules()
    rebuild_router()
    call_startup_hooks()
    return f"Module '{name}' set to {'on' if value else 'off'}."


def cmd_maat_preset(cmd: str, context=None):
    m = re.match(r"^/maat preset (balanced|safe|creative|deep|symbolic)$", (cmd or "").strip())
    if not m:
        return "Usage: /maat preset balanced|safe|creative|deep|symbolic"

    preset = m.group(1)
    STATE["preset_profile"] = preset
    apply_dummy_preset(STATE)
    save_state()
    load_modules()
    rebuild_router()
    call_startup_hooks()
    return f"Preset '{preset}' applied."


def cmd_maat_events(cmd: str, context=None):
    events = SHARED.get("events", [])
    if not isinstance(events, list) or not events:
        return "No loader events recorded."

    last = events[-15:]
    lines = ["Recent loader events:"]
    for item in last:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind", "?")
        data = item.get("data", None)
        lines.append(f"- {kind}: {data}")
    return "\n".join(lines)


def register_core_commands():
    router = get_router()
    router.register("/maat", cmd_maat_root, "Show MAAT loader status")
    router.register("/maat help", cmd_maat_help, "Show registered MAAT commands")
    router.register("/maat state", cmd_maat_state, "Show current loader state")
    router.register("/maat modules", cmd_maat_modules, "List discovered modules and status")
    router.register("/maat reload", cmd_maat_reload, "Reload modules and rebuild router")
    router.register("/maat simple", cmd_maat_simple, "Enable simple UI mode")
    router.register("/maat advanced", cmd_maat_advanced, "Enable advanced UI mode")
    router.register("/maat module", cmd_maat_module, "Toggle a module on/off")
    router.register("/maat preset", cmd_maat_preset, "Apply a preset profile")
    router.register("/maat events", cmd_maat_events, "Show recent loader events")


def register_module_commands():
    router = get_router()

    for name, mod in MODULES.items():
        # preferred new API
        fn = getattr(mod, "register_commands", None)
        if callable(fn):
            try:
                fn(router, STATE, SHARED)
            except Exception as e:
                _debug(f"register_commands failed in {name}:", e)
                _push_event("module_register_commands_failed", {"name": name, "error": str(e)})


def rebuild_router():
    global ROUTER
    ROUTER = CommandRouter()
    register_core_commands()
    register_module_commands()


# ============================================================
# Event routing / legacy command compatibility
# ============================================================

def _module_call(func_name, *args, **kwargs):
    results = []
    for name, mod in MODULES.items():
        fn = getattr(mod, func_name, None)
        if callable(fn):
            try:
                results.append((name, fn(*args, **kwargs)))
            except Exception as e:
                _debug(f"{func_name} failed in {name}:", e)
                _push_event("module_hook_failed", {"module": name, "hook": func_name, "error": str(e)})
        else:
            continue
    return results


def _legacy_module_command_dispatch(cmd: str):
    """
    Backward compatibility:
    if no router command matches, try old module handle_command().
    """
    for name, result in _module_call("handle_command", cmd, STATE, SHARED):
        if result is not None:
            return result
    return None


def command(full_cmd: str, context=None):
    cmd = (full_cmd or "").strip()
    if not cmd:
        return None

    router = get_router()
    result = router.dispatch(cmd, context)

    if result is None:
        result = _legacy_module_command_dispatch(cmd)

    if result is not None:
        save_state()

    return result


# ============================================================
# Hook forwarding
# ============================================================

def input_modifier(string, state=None, is_chat=False):
    if not _framework_enabled():
        return string

    out = string
    for name, result in _module_call("input_modifier", out, state, is_chat, STATE, SHARED):
        if isinstance(result, str):
            out = result
    return out


def custom_generate_chat_prompt(user_input, state, **kwargs):
    SHARED["last_user_input"] = user_input or ""

    if not _framework_enabled():
        return None

    if isinstance(user_input, str) and user_input.strip().startswith("/maat"):
        result = command(user_input.strip(), state if isinstance(state, dict) else None)
        if result and isinstance(state, dict):
            _prepend_context_once(state, f"[MAAT_COMMAND_RESULT]\n{result}", "[MAAT_COMMAND_RESULT]")
        return None

    for name, result in _module_call("before_prompt", user_input, state, STATE, SHARED):
        inject = _extract_inject(result)
        inject_hidden = _extract_inject_hidden(result)

        if inject and isinstance(state, dict):
            _prepend_context(state, inject)

        if inject_hidden and isinstance(state, dict):
            # hidden inject is still added to model context,
            # but not surfaced as explicit visible command text
            _prepend_context(state, inject_hidden)

    return None


def bot_prefix_modifier(prefix: str):
    if not _framework_enabled():
        return prefix or ""

    out = prefix or ""
    for name, result in _module_call("bot_prefix_modifier", out, STATE, SHARED):
        if isinstance(result, str):
            out = result
    return out


def output_modifier(string, state=None, is_chat=False):
    SHARED["last_output"] = string or ""

    if not _framework_enabled():
        return string or ""

    out = string or ""
    for name, result in _module_call("after_output", SHARED.get("last_user_input", ""), out, state, STATE, SHARED):
        replacement = _extract_output(result)
        if isinstance(replacement, str):
            out = replacement

    return out


# ============================================================
# UI
# ============================================================

def _apply_and_reload_order():
    """Helper: save state, reload modules, return status strings."""
    save_state()
    load_modules()
    rebuild_router()
    call_startup_hooks()
    active = ", ".join(MODULES.keys()) or "(none)"
    order  = ", ".join(get_effective_module_order())
    return (
        f"Saved. Active: {active}\n\nCurrent order: {order}",
        order,
        f"Loaded modules: {active}",
    )


def ui():
    if gr is None:
        return

    with gr.Tab("MAAT Modular Plugin"):
        gr.Markdown("## MAAT Modular Plugin")
        gr.Markdown(
            "Use the Simple Menu if you want to enable or disable the main features quickly. "
            "Use the Advanced Menu for full control, including module order."
        )

        # ----------------------------------------------------
        # Loader basics
        # ----------------------------------------------------
        with gr.Accordion("Loader", open=True):
            enabled = gr.Checkbox(value=STATE.get("enabled", True), label="Framework Enabled")
            debug = gr.Checkbox(value=STATE.get("debug", False), label="Debug")
            save_loader_btn = gr.Button("Save Loader Settings", variant="primary")
            loader_status = gr.Markdown(value=f"Loaded modules: {', '.join(MODULES.keys()) or '(none)'}")

            def _save_loader(v_enabled, v_debug):
                STATE["enabled"] = bool(v_enabled)
                STATE["debug"] = bool(v_debug)
                save_state()
                return f"Loaded modules: {', '.join(MODULES.keys()) or '(none)'}"

            save_loader_btn.click(_save_loader, [enabled, debug], [loader_status])

        # ----------------------------------------------------
        # Simple menu
        # ----------------------------------------------------
        with gr.Accordion("🟢 Simple Menu", open=True):
            ui_simple_mode = gr.Checkbox(value=STATE.get("ui_simple_mode", True), label="Use Simple Mode")

            preset_profile = gr.Dropdown(
                choices=["balanced", "safe", "creative", "deep", "symbolic"],
                value=STATE.get("preset_profile", "balanced"),
                label="Profile",
                info="balanced = normal, safe = stricter, creative = freer, deep = more reflective, symbolic = stronger symbol/gematria focus",
            )

            with gr.Row():
                preset_memory = gr.Checkbox(value=STATE.get("preset_memory", True), label="Memory")
                preset_emotion = gr.Checkbox(value=STATE.get("preset_emotion", True), label="Emotion Understanding")
                preset_gematria = gr.Checkbox(value=STATE.get("preset_gematria", True), label="Gematria")

            with gr.Row():
                preset_rewrite = gr.Checkbox(value=STATE.get("preset_rewrite", True), label="Auto Improve Answers")
                preset_banner = gr.Checkbox(value=STATE.get("preset_banner", False), label="Show Status Banner")

            apply_simple_btn = gr.Button("Apply Simple Settings", variant="primary")
            simple_status = gr.Markdown(value=simple_status_text(STATE))

            def _apply_simple(v_ui_simple, v_profile, v_mem, v_emo, v_gem, v_rewrite, v_banner):
                STATE["ui_simple_mode"] = bool(v_ui_simple)
                STATE["preset_profile"] = v_profile
                STATE["preset_memory"] = bool(v_mem)
                STATE["preset_emotion"] = bool(v_emo)
                STATE["preset_gematria"] = bool(v_gem)
                STATE["preset_rewrite"] = bool(v_rewrite)
                STATE["preset_banner"] = bool(v_banner)

                apply_dummy_preset(STATE)
                save_state()
                load_modules()
                rebuild_router()
                call_startup_hooks()

                return (
                    simple_status_text(STATE),
                    f"Loaded modules: {', '.join(MODULES.keys()) or '(none)'}"
                )

            apply_simple_btn.click(
                _apply_simple,
                inputs=[
                    ui_simple_mode, preset_profile, preset_memory, preset_emotion,
                    preset_gematria, preset_rewrite, preset_banner
                ],
                outputs=[simple_status, loader_status]
            )

        # ----------------------------------------------------
        # Advanced menu
        # ----------------------------------------------------
        with gr.Accordion("🧠 Advanced Menu", open=False):
            gr.Markdown(
                "Detailed expert controls for fine-tuning behavior, thresholds, memory, emotion, gematria, rewrite logic, and module order."
            )

            with gr.Accordion("Module Manager", open=True):
                gr.Markdown(
                    "**Tip:** Modules loaded last appear highest in the context window "
                    "(most influence on the model). For the current MAAT setup, "
                    "identity / maat_thinking / maat_spirit / maat_reflection should be last."
                )

                module_names = get_effective_module_order()
                module_checkboxes = []
                for name in module_names:
                    cb = gr.Checkbox(
                        value=STATE["module_enabled"].get(name, True),
                        label=name
                    )
                    module_checkboxes.append((name, cb))

                module_order_text = gr.Textbox(
                    value=", ".join(get_effective_module_order()),
                    label="Module Load Order (comma-separated, last = highest context weight)",
                    lines=3,
                    info=(
                        "Empfohlen für aktuelles MAAT-System: "
                        "help, super_memory, maat_engine, cci_engine, plp_anti_hallu, "
                        "emotion, rewrite_loop, maat_value_core, maat_principles, "
                        "identity, maat_thinking, maat_spirit, maat_reflection"
                    )
                )

                with gr.Accordion("Reihenfolge mit Buttons ändern", open=False):
                    gr.Markdown("Modul auswählen und mit ⬆ / ⬇ verschieben.")
                    reorder_status = gr.Markdown(value="")

                    for mod_name in get_effective_module_order():
                        with gr.Row():
                            gr.Markdown(f"`{mod_name}`")
                            btn_up   = gr.Button("⬆", size="sm")
                            btn_down = gr.Button("⬇", size="sm")

                            def _move_up(name=mod_name):
                                move_module_up(name)
                                s, o, l = _apply_and_reload_order()
                                return s, o, l

                            def _move_down(name=mod_name):
                                move_module_down(name)
                                s, o, l = _apply_and_reload_order()
                                return s, o, l

                            btn_up.click(
                                _move_up,
                                outputs=[reorder_status, module_order_text, loader_status]
                            )
                            btn_down.click(
                                _move_down,
                                outputs=[reorder_status, module_order_text, loader_status]
                            )

                with gr.Row():
                    apply_modules_btn = gr.Button("Apply Module Selection + Order", variant="primary")
                    reset_order_btn = gr.Button("Reset to Recommended Order")

                module_status = gr.Markdown(value="")

                def _apply_modules(*values):
                    checkbox_values = values[:-1]
                    order_csv = values[-1]

                    for (name, _cb), value in zip(module_checkboxes, checkbox_values):
                        STATE["module_enabled"][name] = bool(value)

                    reorder_from_csv(order_csv)
                    save_state()
                    load_modules()
                    rebuild_router()
                    call_startup_hooks()

                    active = ", ".join(MODULES.keys()) or "(none)"
                    order = ", ".join(get_effective_module_order())
                    return (
                        f"Saved. Active: {active}\n\nCurrent order: {order}",
                        f"Loaded modules: {active}"
                    )

                def _reset_order():
                    discovered = discover_module_names()
                    STATE["module_order"] = _priority_sorted(discovered)
                    save_state()
                    load_modules()
                    rebuild_router()
                    call_startup_hooks()

                    order = ", ".join(get_effective_module_order())
                    return (
                        f"Order reset to recommended.\n\nOrder: {order}",
                        order,
                        f"Loaded modules: {', '.join(MODULES.keys()) or '(none)'}"
                    )

                apply_modules_btn.click(
                    _apply_modules,
                    [cb for _, cb in module_checkboxes] + [module_order_text],
                    [module_status, loader_status]
                )

                reset_order_btn.click(
                    _reset_order,
                    outputs=[module_status, module_order_text, loader_status]
                )

            with gr.Accordion("Global Advanced Settings", open=False):
                maat_mode = gr.Dropdown(
                    choices=["light", "balanced", "deep"],
                    value=STATE.get("maat_mode", "balanced"),
                    label="MAAT Mode"
                )
                show_banner = gr.Checkbox(value=STATE.get("show_banner", False), label="Show Banner")
                save_global_btn = gr.Button("Save Global Advanced Settings")
                global_status = gr.Markdown(value="Advanced settings loaded.")

                def _save_global(v_mode, v_banner):
                    STATE["maat_mode"] = v_mode
                    STATE["show_banner"] = bool(v_banner)
                    STATE["ui_simple_mode"] = False
                    save_state()
                    return "Global advanced settings saved."

                save_global_btn.click(_save_global, [maat_mode, show_banner], [global_status])

        # ----------------------------------------------------
        # Module UIs
        # ----------------------------------------------------
        for name, mod in MODULES.items():
            fn = getattr(mod, "build_ui", None)
            if callable(fn):
                try:
                    fn(STATE, SHARED, save_state)
                except Exception as e:
                    gr.Markdown(f"**UI error in {name}:** {e}")


# ============================================================
# Startup
# ============================================================

def _on_import():
    load_state()
    load_modules()
    rebuild_router()
    call_startup_hooks()
    _debug("loaded modules:", list(MODULES.keys()))


_on_import()