import numpy as np
import matplotlib.pyplot as plt
import os
import csv

np.random.seed(42)

# --------------------------------------------------
# Output folder
# --------------------------------------------------
OUT_DIR = "output_ethics_sim"
os.makedirs(OUT_DIR, exist_ok=True)

# --------------------------------------------------
# Parameters
# --------------------------------------------------
N = 400
T = 80
step = 0.08

a0 = 1.0
Cc = 0.55
b = 1.0
gamma = 2.0
s_star = 0.55
kappa = 1.5
eps = 1e-6

lambda_F = 0.8
lambda_C = 0.6
C_star = 0.55

# --------------------------------------------------
# Initial population
# --------------------------------------------------
X = np.random.rand(N, 5)

# --------------------------------------------------
# Functions
# --------------------------------------------------
def ethics_score(x):
    return np.mean(x, axis=-1)

def order_parameter(x):
    H, B, S, V, R = x.T
    return np.clip((H * B * V * R) ** 0.25, 0, 1)

def imbalance(x):
    return np.std(x, axis=-1)

def cci(x):
    H, B, S, V, R = x.T
    O = order_parameter(x)
    return S * (1 + kappa * imbalance(x)) / (O + eps)

def a_coeff(x):
    return a0 * (cci(x) - Cc)

def free_energy(x):
    H, B, S, V, R = x.T
    O = order_parameter(x)
    a = a_coeff(x)
    return a * O**2 + b * O**4 + gamma * (S - s_star)**2

def objective(x):
    E = ethics_score(x)
    F = free_energy(x)
    C = cci(x)
    return E - lambda_F * F - lambda_C * np.abs(C - C_star)

# --------------------------------------------------
# Initial stats
# --------------------------------------------------
initial_E = ethics_score(X)
initial_F = free_energy(X)
initial_C = cci(X)

history_mean = []

# --------------------------------------------------
# Optimization loop
# --------------------------------------------------
for t in range(T):
    history_mean.append(np.mean(X, axis=0))

    proposal = X + step * np.random.randn(N, 5)
    proposal = np.clip(proposal, 0, 1)

    old_obj = objective(X)
    new_obj = objective(proposal)

    accept = new_obj > old_obj
    X[accept] = proposal[accept]

history_mean = np.array(history_mean)

# --------------------------------------------------
# Final stats
# --------------------------------------------------
final_E = ethics_score(X)
final_F = free_energy(X)
final_C = cci(X)

# --------------------------------------------------
# SAVE CSV DATA
# --------------------------------------------------
csv_path = os.path.join(OUT_DIR, "final_states.csv")

with open(csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["H", "B", "S", "V", "R", "E", "F", "CCI"])
    for i in range(N):
        writer.writerow([
            X[i,0], X[i,1], X[i,2], X[i,3], X[i,4],
            final_E[i], final_F[i], final_C[i]
        ])

# --------------------------------------------------
# SAVE SUMMARY
# --------------------------------------------------
summary_path = os.path.join(OUT_DIR, "summary.txt")

with open(summary_path, "w") as f:
    f.write("Initial mean E: {}\n".format(np.mean(initial_E)))
    f.write("Final mean E: {}\n".format(np.mean(final_E)))
    f.write("Initial mean F: {}\n".format(np.mean(initial_F)))
    f.write("Final mean F: {}\n".format(np.mean(final_F)))
    f.write("Initial mean CCI: {}\n".format(np.mean(initial_C)))
    f.write("Final mean CCI: {}\n".format(np.mean(final_C)))

# --------------------------------------------------
# PLOT 1: CCI vs Free Energy
# --------------------------------------------------
plt.figure()
plt.scatter(final_C, final_F, alpha=0.6)
plt.xlabel("CCI")
plt.ylabel("Structural Free Energy")
plt.title("CCI vs Free Energy")
plt.tight_layout()

plt.savefig(os.path.join(OUT_DIR, "plot_cci_vs_energy.png"), dpi=300)
plt.close()

# --------------------------------------------------
# PLOT 2: Ethics score distribution
# --------------------------------------------------
plt.figure()
plt.hist(initial_E, bins=25, alpha=0.6, label="initial")
plt.hist(final_E, bins=25, alpha=0.6, label="final")
plt.xlabel("Ethics Score")
plt.ylabel("Count")
plt.legend()
plt.title("Ethics Score Shift")
plt.tight_layout()

plt.savefig(os.path.join(OUT_DIR, "plot_ethics_hist.png"), dpi=300)
plt.close()

# --------------------------------------------------
# PLOT 3: Evolution of dimensions
# --------------------------------------------------
plt.figure()
labels = ["H", "B", "S", "V", "R"]
for i in range(5):
    plt.plot(history_mean[:, i], label=labels[i])

plt.xlabel("Iteration")
plt.ylabel("Mean value")
plt.title("Evolution of Ethical Dimensions")
plt.legend()
plt.tight_layout()

plt.savefig(os.path.join(OUT_DIR, "plot_evolution.png"), dpi=300)
plt.close()

# --------------------------------------------------
# PRINT RESULT
# --------------------------------------------------
print("=== Simulation complete ===")
print("Saved to:", OUT_DIR)
print("Final mean Ethics:", np.mean(final_E))
print("Final mean Free Energy:", np.mean(final_F))
print("Final mean CCI:", np.mean(final_C))