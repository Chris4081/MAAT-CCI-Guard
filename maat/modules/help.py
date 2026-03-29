"""
MAAT Help Module (Slim Router-Based)

Philosophy
----------
- No duplicate command definitions
- Pull commands directly from CommandRouter
- Provide structured help + examples + status

Features
--------
- Router-based command listing
- System status overview
- Module overview
- Quick examples
"""

# ============================================================
# Helpers
# ============================================================

def _onoff(v):
    return "ON" if v else "OFF"


def _safe_list(x):
    return x if isinstance(x, list) else []


def _safe_dict(x):
    return x if isinstance(x, dict) else {}


# ============================================================
# Core builders
# ============================================================

def build_help_text(state, shared):
    router = shared.get("command_router")

    lines = [
        "# MAAT Help",
        "",
        "Modular AI system with plugins, memory, and reflection.",
        "",
    ]

    # --------------------------------------------------------
    # Commands from router
    # --------------------------------------------------------
    if router and hasattr(router, "routes"):
        lines.append("## Commands")

        routes = router.routes

        for cmd in sorted(routes.keys()):
            desc = routes[cmd].get("description", "")
            if desc:
                lines.append(f"- `{cmd}` → {desc}")
            else:
                lines.append(f"- `{cmd}`")

        lines.append("")

    else:
        lines.append("⚠️ Router not available.\n")

    # --------------------------------------------------------
    # Modules
    # --------------------------------------------------------
    modules = _safe_list(shared.get("loaded_module_names"))

    lines.append("## Loaded Modules")
    if modules:
        for m in modules:
            lines.append(f"- `{m}`")
    else:
        lines.append("- None")

    lines.append("")

    # --------------------------------------------------------
    # Quick examples
    # --------------------------------------------------------
    lines += [
        "## Quick Examples",
        "- `/maat help`",
        "- `/maat state`",
        "- `/maat reload`",
        "- `/maat module gematria off`",
        "- `/maat preset deep`",
        "- `gematria: MAAT`",
        "",
        "## Tip",
        "Use `/maat state` to inspect the system.",
    ]

    return "\n".join(lines)


def build_status_text(state, shared):
    modules = _safe_list(shared.get("loaded_module_names"))

    lines = [
        "# MAAT System Status",
        "",
        f"- Framework: **{_onoff(state.get('enabled', True))}**",
        f"- Mode: **{state.get('maat_mode', 'balanced')}**",
        f"- Identity Mode: **{state.get('identity_mode', 'balanced')}**",
        f"- Simple UI: **{_onoff(state.get('ui_simple_mode', True))}**",
        f"- Show Banner: **{_onoff(state.get('show_banner', False))}**",
        "",
        "## Features",
        f"- Memory: **{_onoff(state.get('memory_enabled', False))}**",
        f"- Emotion: **{_onoff(state.get('emotion_enabled', False))}**",
        f"- Mood: **{_onoff(state.get('mood_enabled', False) or state.get('emotion_trend_enabled', False))}**",
        f"- Gematria: **{_onoff(state.get('gematria_enabled', False))}**",
        f"- Maat Value: **{_onoff(state.get('maat_value_enabled', False))}**",
        f"- PLP Guard: **{_onoff(state.get('plp_enabled', False))}**",
        f"- Rewrite Loop: **{_onoff(state.get('rewrite_enabled', False))}**",
        f"- Identity: **{_onoff(state.get('identity_enabled', False))}**",
        "",
        "## Modules",
    ]

    if modules:
        for m in modules:
            lines.append(f"- `{m}`")
    else:
        lines.append("- None")

    return "\n".join(lines)


def build_module_status(state, shared):
    modules = _safe_list(shared.get("loaded_module_names"))
    enabled_map = _safe_dict(state.get("module_enabled"))

    lines = [
        "# Module Status",
        "",
    ]

    if modules:
        lines.append("## Active")
        for m in modules:
            lines.append(f"- ✅ `{m}`")
        lines.append("")
    else:
        lines.append("No active modules.\n")

    disabled = [k for k, v in enabled_map.items() if not v]
    if disabled:
        lines.append("## Disabled")
        for d in sorted(disabled):
            lines.append(f"- ❌ `{d}`")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# Router integration
# ============================================================

def register_commands(router, STATE, SHARED):
    """
    Register help-related commands into the global router.
    Also inject router into SHARED so we can access it.
    """

    # Make router accessible inside module
    SHARED["command_router"] = router

    router.register(
        "/maat help",
        lambda cmd, ctx=None: build_help_text(STATE, SHARED),
        "Show help overview"
    )

    router.register(
        "/help maat",
        lambda cmd, ctx=None: build_help_text(STATE, SHARED),
        "Alias for /maat help"
    )

    router.register(
        "/maat commands",
        lambda cmd, ctx=None: build_help_text(STATE, SHARED),
        "Alias for /maat help"
    )

    router.register(
        "/maat status",
        lambda cmd, ctx=None: build_status_text(STATE, SHARED),
        "Show system status"
    )

    # ⚠️ optional: override loader version if desired
    # router.register("/maat modules", lambda cmd, ctx=None: build_module_status(STATE, SHARED))


# ============================================================
# Legacy fallback (optional)
# ============================================================

def handle_command(cmd, state, shared):
    if cmd in ["/maat help", "/help maat", "/maat commands"]:
        return build_help_text(state, shared)

    if cmd == "/maat status":
        return build_status_text(state, shared)

    if cmd == "/maat modules":
        return build_module_status(state, shared)

    return None


# ============================================================
# UI
# ============================================================

def build_ui(state, shared, save_state):
    try:
        import gradio as gr
    except Exception:
        return

    with gr.Accordion("Help Module", open=False):
        gr.Markdown("Dynamic help (auto-generated from router).")

        btn_help = gr.Button("Help")
        btn_status = gr.Button("Status")
        btn_modules = gr.Button("Modules")

        out = gr.Markdown(value="")

        btn_help.click(lambda: build_help_text(state, shared), outputs=[out])
        btn_status.click(lambda: build_status_text(state, shared), outputs=[out])
        btn_modules.click(lambda: build_module_status(state, shared), outputs=[out])