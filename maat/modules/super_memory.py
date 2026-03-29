"""
MAAT Super Memory Module  (super_memory.py)
===========================================

Drop into:
    user_data/extensions/maat_textgenplugin/modules/super_memory.py

The complete cognitive memory system of MAAT-KI.
Inspired by the human brain — 4 layers:

  ┌─────────────────────────────────────────────────────┐
  │  Working memory      (last N turns, RAM)           │
  ├─────────────────────────────────────────────────────┤
  │  Episodic memory     (SQLite, time-ordered)        │
  ├─────────────────────────────────────────────────────┤
  │  Semantic memory     (SQLite, hash-vectors)        │
  ├─────────────────────────────────────────────────────┤
  │  Keyword memory      (JSON, MAAT rules/facts)      │
  └─────────────────────────────────────────────────────┘
                    ↓
          Mini-Dreaming (consolidation on load)
          Memory Fusion  (combined recall)

Commands
--------
    /maat memory                – show recent entries
    /maat memory search X       – search memories
    /maat memory dream          – run consolidation manually
    /maat memory stats          – show statistics
    /maat memory clear          – delete all (with confirmation)
    /maat memory save <text>    – explicit save command

Natural save triggers
---------------------
    remember: <text>
    remember <text>
    merke dir <text>
    merk dir <text>
    speichere <text>
    bitte merke dir <text>
    bitte speichere <text>
    notiere <text>

Model save
----------
    save: (<text>)
    save: { "memory": "...", "keywords": "...", "always": false }
"""

import os
import io
import re
import json
import time
import sqlite3
import hashlib
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import gradio as gr
except Exception:
    gr = None


# ============================================================
# Paths / globals
# ============================================================

_EXT_DIR = None
_DB_PATH = None
_KW_PATH = None
_IO_LOCK = threading.Lock()

DEFAULTS: Dict[str, Any] = {
    "supermem_enabled": True,
    "supermem_autostore": True,
    "supermem_autorecall": True,
    "supermem_debug": False,

    # Recall settings
    "supermem_top_k": 5,
    "supermem_min_score": 0.15,
    "supermem_show_source": True,

    # Storage limits
    "supermem_max_episodic": 500,
    "supermem_max_semantic": 300,
    "supermem_max_keyword": 200,

    # Dreaming
    "supermem_dream_on_load": True,
    "supermem_dream_hours": 24,

    # Model save
    "supermem_allow_model_saves": True,
}

_WORKING_MEMORY: List[Dict[str, Any]] = []
_MAX_WORKING = 12

_DEBUG_STATE = {"enabled": False}
_RUNTIME_CFG = {
    "max_episodic": 500,
    "max_semantic": 300,
    "max_keyword": 200,
}


# ============================================================
# Category detection
# ============================================================

_CATEGORY_KEYWORDS = {
    "beziehung": ["freund", "familie", "partner", "liebe", "vertrauen", "nähe", "du", "ich", "hilfe"],
    "technik":   ["ki", "ai", "modell", "python", "gpu", "linux", "code", "plugin", "modul", "script"],
    "emotion":   ["glücklich", "traurig", "angst", "wut", "freude", "hoffnung", "fühle", "gefühl"],
    "meta":      ["bewusstsein", "philosophie", "maat", "harmonie", "balance", "universum", "kosmos"],
    "projekt":   ["maat-ki", "github", "paper", "theorie", "veröffentlich", "research", "zenodo"],
    "wissen":    ["was ist", "erkläre", "definition", "bedeutet", "warum", "wie funktioniert"],
}


def _detect_category(text: str) -> str:
    t = (text or "").lower()
    scores = {cat: sum(1 for w in words if w in t) for cat, words in _CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "allgemein"


# ============================================================
# Text utilities
# ============================================================

def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9äöüÄÖÜß_+\-]+", _norm(s))


def _stopwords() -> set:
    return {
        "ich", "du", "der", "die", "das", "ein", "eine", "und", "oder", "aber", "mit",
        "für", "auf", "in", "am", "von", "zu", "ist", "war", "sind", "sein", "habe",
        "hat", "haben", "dass", "ohne", "nicht", "sich", "wie", "was", "wer", "wo",
        "the", "a", "an", "is", "are", "was", "were", "it", "this", "that", "and", "or",
    }


def _keywords(text: str) -> List[str]:
    stop = _stopwords()
    toks = _tokens(text)
    words = [w for w in toks if w not in stop and len(w) > 2]
    words.sort(key=lambda x: -len(x))
    return words[:8]


def _stable_token_value(tok: str) -> int:
    return int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16) % 10000


def _sentence_vector(text: str) -> float:
    tokens = _tokens(text.lower())
    if not tokens:
        return 0.0
    vals = [_stable_token_value(tok) for tok in tokens]
    return sum(vals) / len(vals)


def _importance(text: str) -> float:
    t = _norm(text)
    score = 0.10

    if len(t) > 100:
        score += 0.10
    if len(_tokens(t)) >= 5:
        score += 0.08

    maat_markers = [
        "maat", "bewusstsein", "harmonie", "balance", "respekt",
        "schöpfungskraft", "verbundenheit",
        "h=", "b=", "s=", "v=", "r=",
        "stability", "maat-wert", "maat wert", "plp",
        "plugin", "modul", "engine", "reflection", "identity", "spirit",
        "qwen", "mistral", "phi-3", "llama", "gguf",
    ]

    for m in maat_markers:
        if m in t:
            score += 0.06

    if any(p in t for p in [
        "merke dir", "merk dir", "speichere", "remember", "notiere"
    ]):
        score += 0.20

    return min(score, 1.0)


def _fingerprint(text: str) -> str:
    return hashlib.md5(_norm(text).encode()).hexdigest()[:12]


def _compress(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 2] + "…"


def _debug(*parts):
    if _DEBUG_STATE.get("enabled"):
        print("[maat/super_memory]", *parts, flush=True)


# ============================================================
# Database setup
# ============================================================

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodic (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         REAL,
            role       TEXT,
            content    TEXT,
            compressed TEXT,
            keywords   TEXT,
            category   TEXT,
            importance REAL,
            fp         TEXT UNIQUE,
            hits       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS semantic (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       REAL,
            text     TEXT UNIQUE,
            vector   REAL,
            category TEXT,
            fp       TEXT UNIQUE
        );

        CREATE INDEX IF NOT EXISTS ep_ts  ON episodic(ts);
        CREATE INDEX IF NOT EXISTS ep_cat ON episodic(category);
        CREATE INDEX IF NOT EXISTS sm_vec ON semantic(vector);
        """)


# ============================================================
# Working memory (RAM)
# ============================================================

def _add_working(role: str, text: str):
    _WORKING_MEMORY.append({"role": role, "text": text, "ts": time.time()})
    if len(_WORKING_MEMORY) > _MAX_WORKING:
        _WORKING_MEMORY.pop(0)


def _recall_working(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    if not _WORKING_MEMORY:
        return []

    q_toks = set(_tokens(query))
    scored = []
    for item in reversed(_WORKING_MEMORY):
        toks = set(_tokens(item["text"]))
        if not q_toks or not toks:
            score = 0.0
        else:
            inter = len(q_toks & toks)
            union = len(q_toks | toks)
            score = inter / union if union else 0.0
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 3), "source": "working", **it} for s, it in scored[:top_k] if s > 0.05]


# ============================================================
# Episodic memory
# ============================================================

def _add_episodic(role: str, text: str):
    fp = _fingerprint(text)
    with _IO_LOCK:
        with _get_conn() as conn:
            existing = conn.execute("SELECT id, hits FROM episodic WHERE fp=?", (fp,)).fetchone()
            if existing:
                conn.execute("UPDATE episodic SET hits=hits+1 WHERE id=?", (existing["id"],))
            else:
                conn.execute("""
                    INSERT INTO episodic
                      (ts, role, content, compressed, keywords, category, importance, fp)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    time.time(),
                    role,
                    text,
                    _compress(text),
                    ",".join(_keywords(text)),
                    _detect_category(text),
                    _importance(text),
                    fp,
                ))
                max_ep = int(_RUNTIME_CFG.get("max_episodic", 500))
                conn.execute("""
                    DELETE FROM episodic WHERE id NOT IN (
                        SELECT id FROM episodic
                        ORDER BY importance DESC, hits DESC, ts DESC
                        LIMIT ?
                    )
                """, (max_ep,))


def _recall_episodic(query: str, top_k: int = 5, min_score: float = 0.15) -> List[Dict[str, Any]]:
    q_toks = set(_keywords(query))
    if not q_toks:
        return []

    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT content, compressed, category, importance, hits, ts FROM episodic ORDER BY ts DESC LIMIT 200"
        ).fetchall()

    scored = []
    for row in rows:
        toks = set(_tokens(row["content"]))
        inter = len(q_toks & toks)
        union = len(q_toks | toks)
        score = inter / union if union else 0.0
        score += 0.08 * float(row["importance"])
        score += 0.01 * min(int(row["hits"]), 5)
        if score >= min_score:
            scored.append((score, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 3), "source": "episodic", **it} for s, it in scored[:top_k]]


# ============================================================
# Semantic memory
# ============================================================

def _add_semantic(text: str):
    fp = _fingerprint(text)
    vec = _sentence_vector(text)
    with _IO_LOCK:
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO semantic (ts, text, vector, category, fp)
                VALUES (?,?,?,?,?)
            """, (time.time(), text, vec, _detect_category(text), fp))
            max_sm = int(_RUNTIME_CFG.get("max_semantic", 300))
            conn.execute("""
                DELETE FROM semantic WHERE id NOT IN (
                    SELECT id FROM semantic ORDER BY ts DESC LIMIT ?
                )
            """, (max_sm,))


def _recall_semantic(query: str, top_k: int = 3, min_score: float = 0.15) -> List[Dict[str, Any]]:
    qv = _sentence_vector(query)
    with _get_conn() as conn:
        rows = conn.execute("SELECT text, vector, category, ts FROM semantic").fetchall()

    scored = []
    for row in rows:
        dist = abs(float(row["vector"]) - qv)
        score = 1.0 / (1.0 + dist / 1000.0)
        if score >= min_score:
            scored.append((score, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 3), "source": "semantic", "content": it["text"], **it} for s, it in scored[:top_k]]


# ============================================================
# Keyword memory
# ============================================================

def _load_keywords() -> List[Dict[str, Any]]:
    if not _KW_PATH or not os.path.exists(_KW_PATH):
        return []
    try:
        with io.open(_KW_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_keywords(items: List[Dict[str, Any]]):
    if not _KW_PATH:
        return
    tmp = _KW_PATH + ".tmp"
    with _IO_LOCK:
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _KW_PATH)


def _add_keyword(memory: str, keywords: str = "", always: bool = False) -> Tuple[bool, str]:
    memory = (memory or "").strip()
    if not memory or len(memory) < 8:
        return False, "Too short."

    items = _load_keywords()
    fp = _fingerprint(memory)

    for it in items:
        if _fingerprint(it.get("memory", "")) == fp:
            return False, "Already exists."

    items.append({
        "memory": memory,
        "keywords": keywords or ",".join(_keywords(memory)[:4]),
        "always": bool(always),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "fp": fp,
    })

    items = items[-int(_RUNTIME_CFG.get("max_keyword", 200)):]
    _save_keywords(items)
    return True, "Saved."


def _recall_keywords(query: str, top_k: int = 4) -> List[Dict[str, Any]]:
    items = _load_keywords()
    lower = query.lower()
    q_toks = set(_tokens(query))
    scored = []

    for it in items:
        kws = [k.strip().lower() for k in (it.get("keywords", "")).split(",") if k.strip()]
        if it.get("always"):
            score = 0.5
        else:
            score = sum(1.0 for kw in kws if kw in lower or kw in q_toks) / max(len(kws), 1)

        if score > 0.05:
            scored.append((score, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 3), "source": "keyword", "content": it["memory"], **it} for s, it in scored[:top_k]]


# ============================================================
# Natural save trigger parser
# ============================================================

_MANUAL_SAVE_PATTERNS = [
    re.compile(r'^\s*remember\s*:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*remember\s+(.+)$', re.IGNORECASE),

    re.compile(r'^\s*merke\s+dir\s*:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*merke\s+dir\s+(.+)$', re.IGNORECASE),

    re.compile(r'^\s*merk\s+dir\s*:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*merk\s+dir\s+(.+)$', re.IGNORECASE),

    re.compile(r'^\s*speichere\s*:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*speichere\s+(.+)$', re.IGNORECASE),

    re.compile(r'^\s*bitte\s+merke\s+dir\s+(.+)$', re.IGNORECASE),
    re.compile(r'^\s*bitte\s+speichere\s+(.+)$', re.IGNORECASE),

    re.compile(r'^\s*notiere\s*:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*notiere\s+(.+)$', re.IGNORECASE),
]


def _extract_manual_save(text: str) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None

    for pat in _MANUAL_SAVE_PATTERNS:
        m = pat.match(raw)
        if m:
            value = (m.group(1) or "").strip()
            if value:
                return value

    return None

def _is_memory_question(text: str) -> bool:
    t = (text or "").lower()

    patterns = [
        "was habe ich", "was hab ich",
        "was habe ich dir gesagt",
        "woran erinnerst du dich",
        "was hast du gespeichert",
        "was weißt du über mich",
        "was habe ich gestern",
        "erinnerst du dich",
        "what did i",
        "what do you remember",
        "what did i say",
        "what do you know about me",
    ]
    return any(p in t for p in patterns)


# ============================================================
# Memory fusion
# ============================================================

def recall_all(query: str, state: dict) -> List[Dict[str, Any]]:
    k = int(state.get("supermem_top_k", 5))
    minsc = float(state.get("supermem_min_score", 0.15))

    results = []
    seen_fps = set()

    for item in (
        _recall_working(query, top_k=3)
        + _recall_keywords(query, top_k=k)
        + _recall_episodic(query, top_k=k, min_score=minsc)
        + _recall_semantic(query, top_k=3, min_score=minsc)
    ):
        content = item.get("content") or item.get("text") or item.get("compressed", "")
        fp = _fingerprint(content)
        if fp not in seen_fps:
            seen_fps.add(fp)
            item["content"] = content
            results.append(item)

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:k]


def _format_recall_block(memories: List[Dict[str, Any]], show_source: bool = True, lang: str = "de") -> str:
    if not memories:
        return ""

    if lang == "en":
        header = f"[MAAT_MEMORY — {len(memories)} recalled memories]"
    else:
        header = f"[MAAT_MEMORY — {len(memories)} erinnerte Erinnerungen]"

    lines = [header]
    for i, m in enumerate(memories, 1):
        src = f" ({m['source']})" if show_source else ""
        cat = m.get("category", "")
        cat_str = f" [{cat}]" if cat else ""
        txt = (m.get("content") or "")[:200]
        lines.append(f"{i}.{src}{cat_str} {txt}")
    return "\n".join(lines)


# ============================================================
# Mini-dreaming
# ============================================================

def _run_dreaming(hours_back: int = 24) -> str:
    cutoff = time.time() - hours_back * 3600
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT content, category FROM episodic
            WHERE ts >= ? ORDER BY importance DESC LIMIT 100
        """, (cutoff,)).fetchall()

    if not rows:
        return "No new memories to consolidate."

    by_cat: Dict[str, List[str]] = {}
    for row in rows:
        cat = row["category"]
        by_cat.setdefault(cat, []).append(row["content"])

    count = 0
    for cat, texts in by_cat.items():
        summary = _compress(" ".join(texts[:5]), max_len=300)
        dream_text = f"[Maat-Dream:{cat}] {summary}"
        _add_semantic(dream_text)
        count += 1

    return f"Dreaming complete: {count} categories consolidated."


# ============================================================
# Model-driven save parser
# ============================================================

_SAVE_PATTERNS = [
    re.compile(r'(?is)\bsave\s*:\s*\((.*?)\)\s*'),
    re.compile(r'(?is)\bsave\s*:\s*({.*?})\s*'),
    re.compile(r'(?is)\bsave\s*:\s*(.+?)(?:\n|$)'),
]


def _parse_save(raw: str) -> Optional[Dict[str, Any]]:
    raw = (raw or "").strip()
    if not raw:
        return None

    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
            return {
                "memory": str(obj.get("memory", raw)).strip(),
                "keywords": str(obj.get("keywords", "")).strip(),
                "always": bool(obj.get("always", False)),
            }
        except Exception:
            pass

    if "=" in raw and "," in raw:
        kv = {}
        for part in raw.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                kv[k.strip().lower()] = v.strip()
        if "memory" in kv:
            return {
                "memory": kv.get("memory", ""),
                "keywords": kv.get("keywords", ""),
                "always": kv.get("always", "").lower() in ("true", "1", "yes"),
            }

    return {"memory": raw, "keywords": "", "always": False}


# ============================================================
# Store helper for all layers
# ============================================================

def _store_all_layers(role: str, text: str, always_keyword: bool = False):
    text = (text or "").strip()
    if not text:
        return
    _add_episodic(role, text)
    _add_semantic(text)
    _add_keyword(text, always=always_keyword)


# ============================================================
# Loader hooks
# ============================================================

def on_load(state: dict, shared: dict, ext_dir: str):
    global _EXT_DIR, _DB_PATH, _KW_PATH

    _EXT_DIR = ext_dir
    os.makedirs(ext_dir, exist_ok=True)
    _DB_PATH = os.path.join(ext_dir, "super_memory.db")
    _KW_PATH = os.path.join(ext_dir, "super_memory_keywords.json")

    for k, v in DEFAULTS.items():
        state.setdefault(k, v)

    _DEBUG_STATE["enabled"] = bool(state.get("supermem_debug", False))
    _RUNTIME_CFG["max_episodic"] = int(state.get("supermem_max_episodic", 500))
    _RUNTIME_CFG["max_semantic"] = int(state.get("supermem_max_semantic", 300))
    _RUNTIME_CFG["max_keyword"] = int(state.get("supermem_max_keyword", 200))

    _init_db()

    def _store_memory_proxy(text, state=None, source="cross", **kw):
        _store_all_layers(source, str(text), always_keyword=bool(kw.get("always", False)))
        return True

    shared["module_memory"] = type("MemProxy", (), {
        "store_memory": staticmethod(_store_memory_proxy)
    })()

    if state.get("supermem_dream_on_load", True):
        try:
            _run_dreaming(int(state.get("supermem_dream_hours", 24)))
        except Exception:
            pass

    print("[maat/super_memory] ready ✓")


def on_startup(state: dict, shared: dict, ext_dir: str):
    shared.setdefault("super_memory_status", {})
    shared["super_memory_status"] = {
        "enabled": state.get("supermem_enabled", True),
        "autostore": state.get("supermem_autostore", True),
        "autorecall": state.get("supermem_autorecall", True),
    }


def before_prompt(user_input: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("supermem_enabled", True):
        return {}
    if not state.get("supermem_autorecall", True):
        return {}

    memories = recall_all(user_input or "", state)

    _add_working("user", user_input or "")

    if isinstance(user_input, str):
        manual_mem = _extract_manual_save(user_input)
        if manual_mem:
            _store_all_layers("user", manual_mem, always_keyword=False)

    if not memories:
        return {}

    lang = shared.get("detected_language", "de")
    show_src = state.get("supermem_show_source", True)
    block = _format_recall_block(memories, show_source=show_src, lang=lang)

    if _is_memory_question(user_input or ""):
        priority_block = (
            "[MAAT_MEMORY_PRIORITY]\n"
            "Die Userfrage bezieht sich auf gespeicherte Erinnerungen.\n"
            "Beantworte sie direkt, konkret und faktisch.\n"
            "Keine Spekulation. Keine Fantasie. Keine poetische Ausweichantwort.\n"
            "Wenn eine passende Erinnerung vorhanden ist, nutze sie zuerst.\n\n"
            + block +
            "\n[/MAAT_MEMORY_PRIORITY]"
        )
        return {"inject_hidden": priority_block}

    return {"inject_hidden": block}


def after_output(user_input: str, output: str, state_obj, state: dict, shared: dict) -> dict:
    if not state.get("supermem_enabled", True):
        return {}

    _add_working("assistant", output or "")

    if state.get("supermem_autostore", True):
        imp = _importance(user_input or "")
        if imp >= 0.25:
            _add_episodic("user", user_input or "")
        if imp >= 0.40:
            _add_semantic(user_input or "")

        out_imp = _importance(output or "")
        if out_imp >= 0.45 and len((output or "").strip()) > 120:
            _add_episodic("assistant", _compress(output or "", 400))

    if state.get("supermem_allow_model_saves", True):
        modified = output or ""
        for pat in _SAVE_PATTERNS:
            for m in list(pat.finditer(modified)):
                parsed = _parse_save(m.group(1))
                if parsed and parsed.get("memory"):
                    _add_keyword(
                        parsed["memory"],
                        parsed.get("keywords", ""),
                        parsed.get("always", False),
                    )
                    modified = modified[:m.start()] + modified[m.end():]
        if modified != output:
            return {"output": modified.strip()}

    return {}


# ============================================================
# Commands
# ============================================================

def _memory_status_text(state: dict) -> str:
    return (
        f"MAAT Super Memory: {'on' if state.get('supermem_enabled', True) else 'off'}  "
        f"autostore={'on' if state.get('supermem_autostore', True) else 'off'}  "
        f"autorecall={'on' if state.get('supermem_autorecall', True) else 'off'}"
    )


def _set_enabled(state: dict, value: bool) -> str:
    state["supermem_enabled"] = bool(value)
    return f"MAAT super memory {'enabled' if value else 'disabled'}."


def cmd_memory_search(cmd: str, state: dict) -> str:
    m = re.match(r"^/maat memory search (.+)$", cmd)
    if not m:
        return "Usage: /maat memory search <query>"

    query = m.group(1).strip()
    results = recall_all(query, state)
    if not results:
        return f"No memories found for: {query}"

    lines = [f"Memories for '{query}':"]
    for i, r in enumerate(results, 1):
        src = r.get("source", "?")
        txt = (r.get("content") or "")[:100]
        lines.append(f"{i}. [{src}] {txt}")
    return "\n".join(lines)


def cmd_memory_recent() -> str:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT content, category, ts FROM episodic ORDER BY ts DESC LIMIT 8"
        ).fetchall()

    if not rows:
        return "Episodic memory empty."

    lines = ["Recent memories:"]
    for i, r in enumerate(rows, 1):
        ts = datetime.fromtimestamp(r["ts"]).strftime("%d.%m %H:%M")
        txt = (r["content"] or "")[:80]
        lines.append(f"{i}. [{ts}] [{r['category']}] {txt}")
    return "\n".join(lines)


def cmd_memory_stats() -> str:
    with _get_conn() as conn:
        ep_count = conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]
        sm_count = conn.execute("SELECT COUNT(*) FROM semantic").fetchone()[0]

    kw_count = len(_load_keywords())
    wm_count = len(_WORKING_MEMORY)
    return (
        f"Super Memory Stats:\n"
        f"  Working memory:  {wm_count} entries (RAM)\n"
        f"  Episodic:        {ep_count} entries (SQLite)\n"
        f"  Semantic:        {sm_count} entries (SQLite)\n"
        f"  Keyword:         {kw_count} entries (JSON)\n"
        f"  DB: {_DB_PATH}"
    )


def register_commands(router, STATE, SHARED):
    router.register("/maat memory", lambda cmd, context=None: cmd_memory_recent(), "Show recent memory entries")
    router.register("/maat memory on", lambda cmd, context=None: _set_enabled(STATE, True), "Enable super memory")
    router.register("/maat memory off", lambda cmd, context=None: _set_enabled(STATE, False), "Disable super memory")
    router.register("/maat memory search", lambda cmd, context=None: cmd_memory_search(cmd, STATE), "Search memories")
    router.register("/maat memory dream", lambda cmd, context=None: _run_dreaming(int(STATE.get("supermem_dream_hours", 24))), "Run consolidation")
    router.register("/maat memory stats", lambda cmd, context=None: cmd_memory_stats(), "Show memory stats")
    router.register("/maat memory clear", lambda cmd, context=None: (
        "Are you sure? This permanently deletes ALL memories.\n"
        "Confirm with: /maat memory clear confirm"
    ), "Delete all memories")
    router.register("/maat memory save", lambda cmd, context=None: _cmd_memory_save(cmd), "Explicitly save memory")


def _cmd_memory_save(cmd: str) -> str:
    m = re.match(r"^/maat memory save (.+)$", cmd, re.IGNORECASE)
    if not m:
        return "Usage: /maat memory save <text>"
    text = m.group(1).strip()
    if not text:
        return "No text provided."
    _store_all_layers("user", text, always_keyword=False)
    return "Gespeichert: Saved."


def handle_command(cmd: str, state: dict, shared: dict) -> Optional[str]:
    cmd = (cmd or "").strip()

    if cmd == "/maat memory":
        return cmd_memory_recent()

    if cmd == "/maat memory stats":
        return cmd_memory_stats()

    if cmd == "/maat memory dream":
        return _run_dreaming(int(state.get("supermem_dream_hours", 24)))

    if cmd == "/maat memory clear":
        return (
            "Are you sure? This permanently deletes ALL memories.\n"
            "Confirm with: /maat memory clear confirm"
        )

    if cmd == "/maat memory clear confirm":
        with _IO_LOCK:
            with _get_conn() as conn:
                conn.execute("DELETE FROM episodic")
                conn.execute("DELETE FROM semantic")
        _save_keywords([])
        _WORKING_MEMORY.clear()
        return "All memories deleted."

    m = re.match(r"^/maat memory search (.+)$", cmd)
    if m:
        return cmd_memory_search(cmd, state)

    m = re.match(r"^/maat memory save (.+)$", cmd, re.IGNORECASE)
    if m:
        return _cmd_memory_save(cmd)

    manual_mem = _extract_manual_save(cmd)
    if manual_mem:
        _store_all_layers("user", manual_mem, always_keyword=False)
        return "Gespeichert: Saved."

    m = re.match(r"^/maat_mem add (.+)$", cmd)
    if m:
        ok, msg = _add_keyword(m.group(1).strip())
        return msg

    m = re.match(r"^/maat_mem pin (.+)$", cmd)
    if m:
        ok, msg = _add_keyword(m.group(1).strip(), always=True)
        return msg

    return None


# ============================================================
# UI
# ============================================================
def build_ui(state: dict, shared: dict, save_state):
    if gr is None:
        return

    if not _DB_PATH:
        return

    with gr.Accordion("🧠 Super Memory Module", open=False):
        gr.Markdown(
            "### Cognitive Memory System\n"
            "4 layers: Working · Episodic · Semantic · Keyword\n\n"
            "Replaces `memory.py` and `auto_memory.py`."
        )

        with gr.Row():
            cb_en = gr.Checkbox(value=state.get("supermem_enabled", True), label="Enabled")
            cb_store = gr.Checkbox(value=state.get("supermem_autostore", True), label="Auto-Store")
            cb_rec = gr.Checkbox(value=state.get("supermem_autorecall", True), label="Auto-Recall")
            cb_dream = gr.Checkbox(value=state.get("supermem_dream_on_load", True), label="Dream on Load")
            cb_model = gr.Checkbox(value=state.get("supermem_allow_model_saves", True), label="Model-Save (save:...)")

        with gr.Row():
            sl_k = gr.Slider(1, 10, step=1, value=int(state.get("supermem_top_k", 5)), label="Recall Top-K")
            sl_score = gr.Slider(0.0, 1.0, step=0.05, value=float(state.get("supermem_min_score", 0.15)), label="Min Score")
            sl_hours = gr.Slider(1, 72, step=1, value=int(state.get("supermem_dream_hours", 24)), label="Dream hours back")

        save_btn = gr.Button("Save Settings", variant="primary")
        status = gr.Markdown()

        def _save(en, store, rec, dream, model, k, score, hours):
            state["supermem_enabled"] = bool(en)
            state["supermem_autostore"] = bool(store)
            state["supermem_autorecall"] = bool(rec)
            state["supermem_dream_on_load"] = bool(dream)
            state["supermem_allow_model_saves"] = bool(model)
            state["supermem_top_k"] = int(k)
            state["supermem_min_score"] = float(score)
            state["supermem_dream_hours"] = int(hours)
            save_state()
            return "Saved."

        save_btn.click(
            _save,
            [cb_en, cb_store, cb_rec, cb_dream, cb_model, sl_k, sl_score, sl_hours],
            [status]
        )

        with gr.Accordion("View Memory", open=False):
            out_mem = gr.Markdown()

            def _show_stats():
                try:
                    with _get_conn() as conn:
                        ep = conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]
                        sm = conn.execute("SELECT COUNT(*) FROM semantic").fetchone()[0]
                    kw = len(_load_keywords())
                    wm = len(_WORKING_MEMORY)
                    return (
                        f"**Working memory:** {wm}  \n"
                        f"**Episodisch:** {ep}  \n"
                        f"**Semantisch:** {sm}  \n"
                        f"**Keyword:** {kw}"
                    )
                except Exception as e:
                    return f"Error: {e}"

            def _show_recent():
                try:
                    with _get_conn() as conn:
                        rows = conn.execute(
                            "SELECT content, category, ts FROM episodic ORDER BY ts DESC LIMIT 10"
                        ).fetchall()
                    if not rows:
                        return "Empty."
                    lines = []
                    for r in rows:
                        ts = datetime.fromtimestamp(r["ts"]).strftime("%d.%m %H:%M")
                        txt = (r["content"] or "")[:80]
                        lines.append(f"**[{ts}]** [{r['category']}] {txt}")
                    return "\n\n".join(lines)
                except Exception as e:
                    return f"Error: {e}"

            with gr.Row():
                gr.Button("Stats").click(_show_stats, outputs=[out_mem])
                gr.Button("Recent Episodes").click(_show_recent, outputs=[out_mem])

        with gr.Accordion("Add Manually", open=False):
            tb_mem = gr.Textbox(label="Memory", lines=2)
            tb_kw = gr.Textbox(label="Keywords (comma-separated)")
            cb_alw = gr.Checkbox(label="Always recall", value=False)
            btn_add = gr.Button("Save")
            out_add = gr.Markdown()

            def _add(mem, kw, alw):
                if not (mem or "").strip():
                    return "Please enter text."
                _add_episodic("user", mem)
                _add_semantic(mem)
                ok, msg = _add_keyword(mem, kw or "", bool(alw))
                return msg

            btn_add.click(_add, [tb_mem, tb_kw, cb_alw], [out_add])

        with gr.Accordion("Dreaming (Consolidation)", open=False):
            gr.Markdown("Consolidates episodic memories into semantic memory.")
            btn_dream = gr.Button("Consolidate now")
            out_dream = gr.Markdown()
            btn_dream.click(
                lambda: _run_dreaming(state.get("supermem_dream_hours", 24)),
                outputs=[out_dream]
            )


# ============================================================
# Init
# ============================================================

def _init():
    print("[maat/super_memory] module loaded")

_init()