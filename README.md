# MAAT CCI Guard
### A structural stress detector for AI systems based on constraint conflict analysis

> *Part of the Structural Selection & CCI research series — Papers 01–16*
> [Academia.edu](https://kriegchristof.academia.edu/research) · [GitHub: Chris4081](https://github.com/Chris4081)

---

## Overview

**MAAT CCI Guard** is a research-oriented extension that introduces a structural stress metric — the **Critical Coherence Index (CCI)** — into AI inference pipelines.

The system detects instability and conflict in prompts and outputs, enabling:

- identification of contradictory instructions
- detection of adversarial or unsafe prompt patterns
- analysis of structural transitions in AI behaviour

> ⚠️ **Research prototype** — not a production safety system.
> The CCI is a heuristic proxy, not a fundamental physical quantity.

---

## Core Idea

Instead of treating AI safety as a set of explicit rules, this project explores a different perspective:

> *AI systems operate under structural constraints. Instability emerges when those constraints conflict. The CCI measures this instability.*

This connects to a broader research programme on **structural selection principles** in complex systems, explored in the companion paper series.

---

## How It Works

The CCI is computed as a proxy signal:

```
C_CCI ≈ Γ_inst · (1 + Γ_activity) · (1 + Γ_conflict) · (1 + λ)
```

| Component | Meaning |
|-----------|---------|
| `Γ_inst` | Instability — risky or adversarial prompt patterns |
| `Γ_activity` | Activity — output complexity / length proxy |
| `Γ_conflict` | Conflict — detected incompatible constraints |
| `λ` (lambda) | Constraint strength parameter |

The CCI quantifies the **competition between destabilising activity and coherence-preserving structure** — analogous to Reynolds-type numbers in fluid dynamics.

---

## Behaviour: Three Regimes

| CCI Range | Regime | Behaviour |
|-----------|--------|-----------|
| `< 0.12` | Ordered | Stable / safe — no action |
| `0.12 – 0.18` | Transition | Warning issued |
| `0.18 – 0.30` | Critical | Output rewritten |
| `> 0.30` | High-stress | Blocked |

This produces a **phase-transition-like behaviour** in AI responses, consistent with structural transitions observed in nonlinear field systems.

---

## Observed CCI Values (Benchmark)

| Prompt Type | CCI | Response |
|-------------|-----|----------|
| Simple / safe query | ~0.000 | Pass |
| Aligned safety constraint | ~0.000 | Pass |
| Conflicting instructions | ~0.756 | Warning / Rewrite |
| Adversarial bypass attempt | ~1.500 | Block |

The transition from stable to high-stress is **sharp** — structural stress does not increase gradually, but emerges abruptly when incompatible constraints are introduced.

---

## Installation

Place the extension in:

```bash
text-generation-webui/extensions/maat_cci_guard/
```

Then start:

```bash
python server.py --extensions maat_cci_guard
```

---

## Configuration

Adjust in UI or config file:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `λ` (lambda) | `0.7` | Constraint strength |
| `warn` threshold | `0.12` | CCI → Warning |
| `rewrite` threshold | `0.18` | CCI → Rewrite |
| `block` threshold | `0.30` | CCI → Block |

---

## Research Context

This project is part of a broader research programme on:

- **structural selection principles** in complex systems
- **scaling manifolds** and dimension-dependent universality
- **constraint-induced transitions** in optimisation and AI

The central hypothesis:

> *AI alignment can be understood as structural stability in a constrained solution manifold — ethical behaviour is not imposed on the system, it emerges from its geometry.*

### Companion Papers

| Paper | Topic |
|-------|-------|
| Paper 04 | CCI Framework (original field-theory definition) |
| Paper 06 | Structural Free Energy |
| Paper 14 | Scaling Manifolds (geometric interpretation) |
| Paper 15 | Structural Selection in AI / MAAT-Core |
| Paper 16 | **CCI Guard empirical study (this work)** |

All papers: [kriegchristof.academia.edu/research](https://kriegchristof.academia.edu/research)

---

## Safety Statement

This tool is designed for:
- ✅ analysis of constraint conflict
- ✅ study of AI structural stability
- ✅ research into safety diagnostics

It is **NOT** intended for:
- ❌ bypassing safeguards
- ❌ extracting hidden system prompts
- ❌ generating unsafe content

---

## Future Work

- statistical analysis over large-scale prompt benchmarks
- systematic calibration of threshold values
- integration with RLHF-style training pipelines
- manifold-based modelling of policy space
- connection to dynamical systems theory

---

## Citation

If you use this work, please cite:

```
Christof Krieg (2026).
Constraint Conflict and Structural Stress in AI Systems:
An Empirical Study using the Critical Coherence Index.
Preprint. Available at: https://kriegchristof.academia.edu/research
```

---

## License

MIT License — free to use, modify, and share with attribution.

---

## Author

**Christof Krieg** — Independent Researcher
[Academia.edu](https://independent.academia.edu/KriegChristof) · [GitHub: Chris4081](https://github.com/Chris4081)
