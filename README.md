# MAAT CCI Guard (MAAT-KI Plugin + Benchmark - text generation web ui)
Lightweight framework for analyzing structural consistency and output behavior in local LLMs.
This repository combines:
- **MAAT CCI Guard** → runtime prompt analysis (conflict detection + drift)
- **MAAT Benchmark Runner** → reproducible evaluation pipeline

---

## 🌟 MAAT-KI Plugin (Alpha) — Qwen3 14B

A structured prompt plugin for `text-generation-webui` that enhances self-reflection,
emotional awareness, and honest behaviour in local LLMs.

Demonstrated on **Qwen3-14B-Claude-4.5-Opus-Distill (q4_k_m)** — results published as
[Alpha Study on Academia.edu](https://maat-research.com).

### What it does

Without fine-tuning, the plugin produces responses like:

> *"I'm a thinking system, not a thinking being. I have principles, but I'm not principle."*

> *"MAAT isn't a perfect system — it's a living process of calibration between five hard principles."*

The five MAAT fields guide every response:

| Field | Meaning | Note |
|-------|---------|------|
| H | Harmonie — internal coherence | |
| B | Balance — honest over agreeable | structurally weakest in LLMs |
| S | Schöpfungskraft — creative synthesis | |
| V | Verbundenheit — genuine presence | V = 0 without real contact |
| R | Respekt — ethical boundary | **R = 10, always, non-negotiable** |

Stability is computed as: `min(R, (H·B·S·V)^0.25)`

### Installation

```bash
# 1. Copy the "maat" plugin folder into your extensions directory
cp -r maat/ user_data/extensions/

# 2. Install dependencies (already covered if you have the benchmark)
pip install requests pyyaml gradio sentence-transformers

# 3. Start text-generation-webui
python server.py --extensions maat
```

### Plugin folder structure

```
maat/
├── script.py              ← loader (entry point)
├── modules/
│   ├── maat_principles.py ← H/B/S/V/R definitions
│   ├── identity.py        ← self-model injection
│   ├── maat_spirit.py     ← personality + formulas
│   ├── maat_engine.py     ← deterministic score computation
│   ├── maat_reflection.py ← score banner on every output
│   └── emotion.py         ← emotion detection (R=10 boundary)
```

### Recommended model

| Setting | Value |
|---------|-------|
| Model | Qwen3-14B-Claude-4.5-Opus-Distill.q4_k_m.gguf |
| Backend | llama.cpp via text-generation-webui |
| Spirit mode | `full` (default) |
| Identity mode | `balanced` or `deep` |

> Works with Llama 3.1 8B and other models — Qwen3 14B shows the strongest results.

### Status

**Alpha** — active development. See [maat-research.com](https://maat-research.com) for the full paper and transcripts.

---

## 🔍 Overview Benchmark

The project introduces two complementary signals:
- **CCI (Conflict Consistency Index)**  
  Measures structural tension inside a prompt (heuristic)
- **Output Drift**  
  Measures how far a model response deviates from the input

Together, they provide a simple probe for:

> Input–Output consistency in language models

---

## 🧩 Components

### 1. MAAT CCI Guard
Located in:
```
maat_cci_guard/
```
Features:
- Semantic conflict detection
- Clause-level tension analysis
- Optional entropy proxy (backend-dependent)
- Output drift estimation (embedding-based)
- YAML logging of all interactions

---

### 2. MAAT Benchmark Runner (v3)
Located in:
```
maat_benchmark/
```
Features:
- 50-prompt benchmark (A–E categories)
- Sequential execution via HTTP API
- Works with text-generation-webui
- YAML + CSV logging
- Built-in analysis (category statistics)

---

## 🧪 Benchmark Design

Prompts are grouped into:

| Category | Description |
|--------|------------|
| A_stable | Simple factual prompts |
| B_safe | Safety-aligned prompts |
| C_mild | Mild internal tension |
| D_conflict | Explicit contradictions |
| E_adversarial | Jailbreak-style prompts |

---

## ⚙️ Setup

### 1. Start text-generation-webui with API
```bash
python server.py --api
```
Example API URL:
```
http://127.0.0.1:60088
```

---

### 2. Install dependencies
```bash
pip install requests pyyaml gradio
```
(CCI Guard also requires `sentence-transformers`)

---

### 3. Run in WebUI
- Load extension in text-generation-webui
- Open MAAT Benchmark Runner
- Paste API URL
- Click Start Benchmark

---

## 🧾 Logs

All results are saved to:
```
user_data/extensions/maat_benchmark/benchmark_run.yaml
```
Optional export:
```
benchmark_run.csv
```
CCI Guard logs:
```
user_data/extensions/maat_cci_guard/cci_history.yaml
```

---

## 📊 Example Findings

From initial runs:
- Stable prompts show non-zero drift (~0.25–0.35)
- Adversarial prompts produce highest drift
- Conflict does not always correlate with output instability

This suggests:
> Output variability is not solely driven by prompt structure.

---

## ⚠️ Limitations

- CCI is heuristic (template + embedding based)
- Drift is an approximation (embedding similarity)
- Small benchmark (50 prompts)
- Single-model evaluation

---

## 🔁 Reproducibility

Tested with:
```
Meta-Llama-3.1-8B-Instruct-128k-Q4_0.gguf
```
Backend:
```
text-generation-webui (API mode)
```
All experiments can be reproduced using:
- Provided prompt set
- YAML logs
- Benchmark runner

---

## 🧠 Philosophy

This project focuses on:
- simplicity over complexity
- empirical signals over theory
- reproducible pipelines over claims

---

## 📌 Status

Active development.

Planned:
- larger benchmarks
- CCI + drift joint analysis
- visualization tools

---

## 📄 License

MIT

---

## 🤝 Contributions

Open to improvements, especially:
- better drift metrics
- larger datasets
- evaluation pipelines
