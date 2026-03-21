
import numpy as np
import matplotlib.pyplot as plt

EPS = 1e-12

# --------------------------------------------------
# phi^4 model
# --------------------------------------------------
def potential(phi: np.ndarray) -> np.ndarray:
    return 0.25 * (phi**2 - 1.0) ** 2


def dV(phi: np.ndarray) -> np.ndarray:
    return phi * (phi**2 - 1.0)


def laplacian_1d(phi: np.ndarray, dx: float) -> np.ndarray:
    return (np.roll(phi, -1) + np.roll(phi, 1) - 2.0 * phi) / dx**2


def energy_density(phi: np.ndarray, pi: np.ndarray, dx: float) -> np.ndarray:
    grad = (np.roll(phi, -1) - np.roll(phi, 1)) / (2.0 * dx)
    return 0.5 * pi**2 + 0.5 * grad**2 + potential(phi)


# --------------------------------------------------
# initial conditions
# --------------------------------------------------
def make_state(kind: str, x: np.ndarray, rng: np.random.Generator):
    if kind == "vacuum":
        phi = np.ones_like(x) + 0.01 * rng.normal(size=len(x))
        pi = 0.01 * rng.normal(size=len(x))

    elif kind == "kink":
        phi = np.tanh(x / 1.5) + 0.02 * rng.normal(size=len(x))
        pi = 0.01 * rng.normal(size=len(x))

    elif kind == "noisy":
        phi = rng.normal(scale=0.35, size=len(x))
        pi = rng.normal(scale=0.15, size=len(x))

    elif kind == "chaotic":
        phi = rng.normal(scale=0.9, size=len(x))
        pi = rng.normal(scale=0.8, size=len(x))

    elif kind == "mixed":
        phi = 0.7 * np.tanh((x + 6.0) / 1.5) - 0.7 * np.tanh((x - 6.0) / 1.5)
        phi += 0.20 * rng.normal(size=len(x))
        pi = 0.20 * rng.normal(size=len(x))

    else:
        raise ValueError(f"unknown kind: {kind}")

    return phi, pi


# --------------------------------------------------
# scoring helpers
# --------------------------------------------------
def inverse_score(x: float, scale: float = 1.0) -> float:
    """Monotone score in (0,1], large x -> smaller score."""
    return float(1.0 / (1.0 + x / (scale + EPS)))


def saturating_score(x: float, scale: float = 1.0) -> float:
    """Monotone score in [0,1), small x -> 0, large x -> 1."""
    return float(x / (x + scale + EPS))


def bounded(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(np.clip(x, lo, hi))


# --------------------------------------------------
# diagnostics
# --------------------------------------------------
def compute_diagnostics(phi: np.ndarray, pi: np.ndarray, dx: float):
    n = len(phi)
    lap = laplacian_1d(phi, dx)
    edens = energy_density(phi, pi, dx)

    # H: equation-of-motion consistency (higher is better)
    eom_residual = lap - dV(phi)  # static toy residual
    H_raw = np.mean(eom_residual**2)
    H = inverse_score(H_raw, scale=0.2)

    # B: left/right energy balance (higher is better)
    left_E = np.sum(edens[: n // 2])
    right_E = np.sum(edens[n // 2 :])
    imbalance = abs(left_E - right_E) / (abs(left_E + right_E) + EPS)
    B = inverse_score(imbalance, scale=0.08)

    # S: creative/dynamical activity (higher with activity, but saturating)
    activity = np.mean(pi**2 + lap**2)
    S = saturating_score(activity, scale=0.5)

    # V: neighbor correlation / connectedness
    corr_num = np.mean(phi * np.roll(phi, 1))
    corr_den = np.mean(phi**2) + EPS
    neighbor_corr = corr_num / corr_den
    V = bounded((neighbor_corr + 1.0) / 2.0)

    # R: regularity / boundary respect
    boundary_penalty = 0.5 * (abs(phi[0] - phi[1]) + abs(phi[-1] - phi[-2]))
    roughness = np.mean((np.roll(phi, -1) - phi) ** 2)
    R = inverse_score(boundary_penalty + 0.5 * roughness, scale=0.15)

    # K: spectral coherence proxy
    spectral = np.abs(np.fft.rfft(phi)) ** 2
    p = spectral / (np.sum(spectral) + EPS)
    entropy = -np.sum(p * np.log(p + EPS))
    entropy_norm = entropy / (np.log(len(p) + EPS) + EPS)
    K = bounded(1.0 - 0.7 * entropy_norm, lo=0.05, hi=1.0)

    # Costs
    C = 0.25 + 0.6 * (1.0 - R) + 0.4 * (1.0 - B)
    dE = float(np.mean(edens))

    # CCI ingredients
    gamma_inst = saturating_score(activity, scale=0.4)
    gamma_prod = S
    gamma_coh = 0.5 * (H + B)
    gamma_corr = V

    return {
        "H": H,
        "B": B,
        "S": S,
        "V": V,
        "R": R,
        "K": K,
        "C": C,
        "dE": dE,
        "activity": float(activity),
        "imbalance": float(imbalance),
        "roughness": float(roughness),
        "entropy_norm": float(entropy_norm),
        "gamma_inst": gamma_inst,
        "gamma_prod": gamma_prod,
        "gamma_coh": gamma_coh,
        "gamma_corr": gamma_corr,
    }


# --------------------------------------------------
# PLP / structural free energy / CCI
# --------------------------------------------------
def compute_log_plp(diag: dict) -> float:
    return (
        np.log(diag["H"] + EPS)
        + np.log(diag["B"] + EPS)
        + np.log(diag["S"] + EPS)
        + np.log(diag["V"] + EPS)
        + np.log(diag["R"] + EPS)
        + np.log(diag["K"] + EPS)
        - np.log(diag["C"] + diag["dE"] + EPS)
    )


def compute_plp(diag: dict) -> float:
    return float(np.exp(compute_log_plp(diag)))


def compute_fstruct(diag: dict) -> float:
    # by construction: F_struct = -log(PLP)
    return float(-compute_log_plp(diag))


def compute_cci(diag: dict) -> float:
    num = diag["gamma_inst"] * diag["gamma_prod"] + EPS
    den = diag["gamma_coh"] + diag["gamma_corr"] + EPS
    return float(num / den)


# --------------------------------------------------
# experiment
# --------------------------------------------------
def run_experiment(n_per_class: int = 100, seed: int = 7):
    rng = np.random.default_rng(seed)

    n = 256
    L = 40.0
    x = np.linspace(-L / 2, L / 2, n, endpoint=False)
    dx = x[1] - x[0]

    classes = ["vacuum", "kink", "noisy", "chaotic", "mixed"]
    rows = []

    for cls in classes:
        for _ in range(n_per_class):
            phi, pi = make_state(cls, x, rng)
            diag = compute_diagnostics(phi, pi, dx)
            plp = compute_plp(diag)
            fstruct = compute_fstruct(diag)
            cci = compute_cci(diag)

            row = {
                "class": cls,
                "PLP": plp,
                "log_PLP": compute_log_plp(diag),
                "F_struct": fstruct,
                "CCI": cci,
            }
            row.update(diag)
            rows.append(row)

    return rows


# --------------------------------------------------
# statistics
# --------------------------------------------------
def rankdata(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    return ranks


def spearman_corr(x, y) -> float:
    rx = rankdata(np.asarray(x))
    ry = rankdata(np.asarray(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def summarize(rows: list[dict]):
    classes = sorted(set(r["class"] for r in rows))
    cols = ["PLP", "F_struct", "CCI", "H", "B", "S", "V", "R", "K"]
    print("\nClass means:")
    print(
        f"{'class':<10} {'PLP':>10} {'F_struct':>12} {'CCI':>10} "
        f"{'H':>8} {'B':>8} {'S':>8} {'V':>8} {'R':>8} {'K':>8}"
    )
    for cls in classes:
        sub = [r for r in rows if r["class"] == cls]
        mean = lambda k: np.mean([r[k] for r in sub])
        print(
            f"{cls:<10} "
            f"{mean('PLP'):>10.4f} {mean('F_struct'):>12.4f} {mean('CCI'):>10.4f} "
            f"{mean('H'):>8.4f} {mean('B'):>8.4f} {mean('S'):>8.4f} {mean('V'):>8.4f} "
            f"{mean('R'):>8.4f} {mean('K'):>8.4f}"
        )

    plp = np.array([r["PLP"] for r in rows])
    fstruct = np.array([r["F_struct"] for r in rows])
    cci = np.array([r["CCI"] for r in rows])

    print("\nCorrelations:")
    print("Spearman(PLP, F_struct) =", spearman_corr(plp, fstruct))
    print("Spearman(PLP, CCI)      =", spearman_corr(plp, cci))
    print("Spearman(F_struct, CCI) =", spearman_corr(fstruct, cci))


# --------------------------------------------------
# plotting
# --------------------------------------------------
import os

def plot_results(rows, outdir="plots"):
    os.makedirs(outdir, exist_ok=True)

    classes = sorted(set(r["class"] for r in rows))
    markers = {
        "vacuum": "o",
        "kink": "s",
        "noisy": "^",
        "chaotic": "x",
        "mixed": "D",
    }

    # -------------------------
    # PLP vs CCI
    # -------------------------
    plt.figure(figsize=(8, 6))
    for cls in classes:
        sub = [r for r in rows if r["class"] == cls]
        x = [r["CCI"] for r in sub]
        y = [r["PLP"] for r in sub]
        plt.scatter(x, y, alpha=0.7, label=cls, marker=markers.get(cls, "o"))

    plt.xlabel("CCI")
    plt.ylabel("PLP")
    plt.title("PLP vs CCI")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{outdir}/plp_vs_cci.png", dpi=300)

    # -------------------------
    # PLP vs F_struct
    # -------------------------
    plt.figure(figsize=(8, 6))
    for cls in classes:
        sub = [r for r in rows if r["class"] == cls]
        x = [r["F_struct"] for r in sub]
        y = [r["PLP"] for r in sub]
        plt.scatter(x, y, alpha=0.7, label=cls, marker=markers.get(cls, "o"))

    plt.xlabel("F_struct")
    plt.ylabel("PLP")
    plt.title("PLP vs Structural Free Energy")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{outdir}/plp_vs_fstruct.png", dpi=300)

    # -------------------------
    # CCI vs F_struct
    # -------------------------
    plt.figure(figsize=(8, 6))
    for cls in classes:
        sub = [r for r in rows if r["class"] == cls]
        x = [r["CCI"] for r in sub]
        y = [r["F_struct"] for r in sub]
        plt.scatter(x, y, alpha=0.7, label=cls, marker=markers.get(cls, "o"))

    plt.xlabel("CCI")
    plt.ylabel("F_struct")
    plt.title("CCI vs Structural Free Energy")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{outdir}/cci_vs_fstruct.png", dpi=300)


    print(f"Plots saved in folder: {outdir}/")

if __name__ == "__main__":
    rows = run_experiment(n_per_class=100, seed=7)
    summarize(rows)
    plot_results(rows)