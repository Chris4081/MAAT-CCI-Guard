import os
import numpy as np
import matplotlib.pyplot as plt

EPS = 1e-12

# --------------------------------------------------
# phi^4 model in 2D
# --------------------------------------------------
def potential(phi: np.ndarray) -> np.ndarray:
    return 0.25 * (phi**2 - 1.0) ** 2


def dV(phi: np.ndarray) -> np.ndarray:
    return phi * (phi**2 - 1.0)


def laplacian_2d(phi: np.ndarray, dx: float) -> np.ndarray:
    return (
        np.roll(phi, 1, axis=0)
        + np.roll(phi, -1, axis=0)
        + np.roll(phi, 1, axis=1)
        + np.roll(phi, -1, axis=1)
        - 4.0 * phi
    ) / dx**2


def grad_sq_2d(phi: np.ndarray, dx: float) -> np.ndarray:
    dphix = (np.roll(phi, -1, axis=1) - np.roll(phi, 1, axis=1)) / (2.0 * dx)
    dphiy = (np.roll(phi, -1, axis=0) - np.roll(phi, 1, axis=0)) / (2.0 * dx)
    return dphix**2 + dphiy**2


def energy_density(phi: np.ndarray, pi: np.ndarray, dx: float) -> np.ndarray:
    return 0.5 * pi**2 + 0.5 * grad_sq_2d(phi, dx) + potential(phi)


# --------------------------------------------------
# initial conditions
# --------------------------------------------------
def make_state_2d(kind: str, X: np.ndarray, Y: np.ndarray, rng: np.random.Generator):
    n = X.shape[0]

    if kind == "vacuum":
        phi = np.ones_like(X) + 0.01 * rng.normal(size=X.shape)
        pi = 0.01 * rng.normal(size=X.shape)

    elif kind == "domainwall":
        phi = np.tanh(Y / 1.5) + 0.03 * rng.normal(size=X.shape)
        pi = 0.01 * rng.normal(size=X.shape)

    elif kind == "localized":
        r2 = X**2 + Y**2
        phi = 1.0 - 1.5 * np.exp(-r2 / 12.0) + 0.05 * rng.normal(size=X.shape)
        pi = 0.05 * rng.normal(size=X.shape)

    elif kind == "chaotic":
        phi = rng.normal(scale=0.9, size=X.shape)
        pi = rng.normal(scale=0.8, size=X.shape)

    else:
        raise ValueError(f"unknown kind: {kind}")

    return phi, pi


# --------------------------------------------------
# scoring helpers
# --------------------------------------------------
def inverse_score(x: float, scale: float = 1.0) -> float:
    return float(1.0 / (1.0 + x / (scale + EPS)))


def saturating_score(x: float, scale: float = 1.0) -> float:
    return float(x / (x + scale + EPS))


def bounded(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(np.clip(x, lo, hi))


# --------------------------------------------------
# diagnostics
# --------------------------------------------------
def compute_diagnostics_2d(phi: np.ndarray, pi: np.ndarray, dx: float):
    lap = laplacian_2d(phi, dx)
    edens = energy_density(phi, pi, dx)

    # H: equation-of-motion consistency
    eom_residual = lap - dV(phi)
    H_raw = np.mean(eom_residual**2)
    H = inverse_score(H_raw, scale=0.25)

    # B: quadrant energy balance
    n0, n1 = phi.shape
    q1 = np.sum(edens[: n0 // 2, : n1 // 2])
    q2 = np.sum(edens[: n0 // 2, n1 // 2 :])
    q3 = np.sum(edens[n0 // 2 :, : n1 // 2])
    q4 = np.sum(edens[n0 // 2 :, n1 // 2 :])
    qs = np.array([q1, q2, q3, q4], dtype=float)
    imbalance = np.std(qs) / (np.mean(qs) + EPS)
    B = inverse_score(imbalance, scale=0.10)

    # S: dynamical / structural activity
    activity = np.mean(pi**2 + lap**2)
    S = saturating_score(activity, scale=0.6)

    # V: neighbor coherence
    corr_x = np.mean(phi * np.roll(phi, 1, axis=1)) / (np.mean(phi**2) + EPS)
    corr_y = np.mean(phi * np.roll(phi, 1, axis=0)) / (np.mean(phi**2) + EPS)
    neighbor_corr = 0.5 * (corr_x + corr_y)
    V = bounded((neighbor_corr + 1.0) / 2.0)

    # R: regularity / boundary respect
    top = np.mean(np.abs(phi[0, :] - phi[1, :]))
    bottom = np.mean(np.abs(phi[-1, :] - phi[-2, :]))
    left = np.mean(np.abs(phi[:, 0] - phi[:, 1]))
    right = np.mean(np.abs(phi[:, -1] - phi[:, -2]))
    boundary_penalty = 0.25 * (top + bottom + left + right)

    rough_x = np.mean((np.roll(phi, -1, axis=1) - phi) ** 2)
    rough_y = np.mean((np.roll(phi, -1, axis=0) - phi) ** 2)
    roughness = 0.5 * (rough_x + rough_y)
    R = inverse_score(boundary_penalty + 0.5 * roughness, scale=0.20)

    # K: spectral coherence proxy
    spectral = np.abs(np.fft.rfftn(phi)) ** 2
    p = spectral / (np.sum(spectral) + EPS)
    entropy = -np.sum(p * np.log(p + EPS))
    entropy_norm = entropy / (np.log(p.size + EPS) + EPS)
    K = bounded(1.0 - 0.7 * entropy_norm, lo=0.05, hi=1.0)

    # Costs
    C = 0.25 + 0.6 * (1.0 - R) + 0.4 * (1.0 - B)
    dE = float(np.mean(edens))

    # CCI ingredients
    gamma_inst = saturating_score(activity, scale=0.5)
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
# PLP / F_struct / CCI
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
    return float(-compute_log_plp(diag))


def compute_cci(diag: dict) -> float:
    num = diag["gamma_inst"] * diag["gamma_prod"] + EPS
    den = diag["gamma_coh"] + diag["gamma_corr"] + EPS
    return float(num / den)


# --------------------------------------------------
# experiment
# --------------------------------------------------
def run_experiment_2d(n_per_class: int = 60, seed: int = 7):
    rng = np.random.default_rng(seed)

    n = 96
    L = 30.0
    xs = np.linspace(-L / 2, L / 2, n, endpoint=False)
    dx = xs[1] - xs[0]
    X, Y = np.meshgrid(xs, xs)

    classes = ["vacuum", "domainwall", "localized", "chaotic"]
    rows = []

    for cls in classes:
        for _ in range(n_per_class):
            phi, pi = make_state_2d(cls, X, Y, rng)
            diag = compute_diagnostics_2d(phi, pi, dx)
            row = {
                "class": cls,
                "PLP": compute_plp(diag),
                "log_PLP": compute_log_plp(diag),
                "F_struct": compute_fstruct(diag),
                "CCI": compute_cci(diag),
            }
            row.update(diag)
            rows.append(row)

    return rows


# --------------------------------------------------
# stats
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


def summarize(rows):
    classes = sorted(set(r["class"] for r in rows))
    print("\nClass means:")
    print(
        f"{'class':<12} {'PLP':>10} {'F_struct':>12} {'CCI':>10} "
        f"{'H':>8} {'B':>8} {'S':>8} {'V':>8} {'R':>8} {'K':>8}"
    )
    for cls in classes:
        sub = [r for r in rows if r["class"] == cls]
        mean = lambda k: np.mean([r[k] for r in sub])
        print(
            f"{cls:<12} "
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
# plots
# --------------------------------------------------
def plot_results(rows, outdir="plots_2d"):
    os.makedirs(outdir, exist_ok=True)

    classes = sorted(set(r["class"] for r in rows))
    markers = {
        "vacuum": "o",
        "domainwall": "s",
        "localized": "^",
        "chaotic": "x",
    }

    plt.figure(figsize=(8, 6))
    for cls in classes:
        sub = [r for r in rows if r["class"] == cls]
        plt.scatter(
            [r["CCI"] for r in sub],
            [r["PLP"] for r in sub],
            alpha=0.7,
            label=cls,
            marker=markers.get(cls, "o"),
        )
    plt.xlabel("CCI")
    plt.ylabel("PLP")
    plt.title("2D: PLP vs CCI")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{outdir}/plp_vs_cci_2d.png", dpi=300, bbox_inches="tight")
    plt.close()

    plt.figure(figsize=(8, 6))
    for cls in classes:
        sub = [r for r in rows if r["class"] == cls]
        plt.scatter(
            [r["CCI"] for r in sub],
            [r["F_struct"] for r in sub],
            alpha=0.7,
            label=cls,
            marker=markers.get(cls, "o"),
        )
    plt.xlabel("CCI")
    plt.ylabel("F_struct")
    plt.title("2D: CCI vs Structural Free Energy")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{outdir}/cci_vs_fstruct_2d.png", dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Plots saved in folder: {outdir}/")


if __name__ == "__main__":
    rows = run_experiment_2d(n_per_class=60, seed=7)
    summarize(rows)
    plot_results(rows)