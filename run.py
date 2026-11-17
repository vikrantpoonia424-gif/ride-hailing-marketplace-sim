"""Sweep commission x peak-incentive policies and pick the best feasible one."""
import itertools
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from rhsim import Policy, monte_carlo

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)

COMMISSIONS = [0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30]
INCENTIVES = [0, 10, 20, 30, 40]
RUNS = 10
DRIVER_FLOOR = 185.0       # Rs/hour take-home needed to retain drivers
COMPLETION_FLOOR = 0.72    # minimum share of requests served
BASELINE = (0.20, 0)


def heatmap(df, col, title, fmt, path, cmap="viridis"):
    grid = df.pivot(index="incentive", columns="commission", values=col)
    fig, ax = plt.subplots(figsize=(7, 3.8))
    im = ax.imshow(grid.values, cmap=cmap, aspect="auto", origin="lower")
    ax.set_xticks(range(len(grid.columns)), [f"{c:.0%}" for c in grid.columns])
    ax.set_yticks(range(len(grid.index)), [f"Rs {i}" for i in grid.index])
    for (i, j), v in pd.DataFrame(grid.values).stack().items():
        ax.text(j, i, format(v, fmt), ha="center", va="center", fontsize=7, color="white")
    ax.set_xlabel("Platform commission")
    ax.set_ylabel("Peak incentive / driver-hour")
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    rows = [monte_carlo(Policy(c, i), runs=RUNS)
            for c, i in itertools.product(COMMISSIONS, INCENTIVES)]
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "policy_sweep.csv", index=False)

    heatmap(df, "contribution", "Platform contribution per day (Rs)", ".0f", OUT / "heat_contribution.png")
    heatmap(df, "completion_rate", "Share of requests completed", ".0%", OUT / "heat_completion.png")
    heatmap(df, "driver_hourly", "Driver take-home per online hour (Rs)", ".0f", OUT / "heat_driver_hourly.png")

    feasible = df[(df.driver_hourly >= DRIVER_FLOOR) & (df.completion_rate >= COMPLETION_FLOOR)]
    best = feasible.loc[feasible.contribution.idxmax()]
    base = df[(df.commission == BASELINE[0]) & (df.incentive == BASELINE[1])].iloc[0]

    # Best way to meet the driver floor using the commission lever alone.
    flat = feasible[feasible.incentive == 0]
    flat_best = flat.loc[flat.contribution.idxmax()]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    sc = ax.scatter(df.driver_hourly, df.contribution / 1000, c=df.incentive, cmap="plasma",
                    s=[200 * c for c in df.commission])
    ax.axvline(DRIVER_FLOOR, ls="--", c="grey")
    ax.scatter([best.driver_hourly], [best.contribution / 1000], s=250, facecolors="none",
               edgecolors="black", linewidths=2, label="recommended")
    ax.set_xlabel("Driver take-home (Rs/hour)")
    ax.set_ylabel("Platform contribution (Rs '000/day)")
    ax.set_title("Driver earnings vs platform margin (dot size = commission)")
    fig.colorbar(sc, ax=ax, label="Peak incentive (Rs/hour)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "frontier.png", dpi=150)
    plt.close(fig)

    lines = [
        "# Results",
        f"{len(df)} policies x {RUNS} simulated days each.",
        "",
        "| | Baseline | Recommended |",
        "|---|---|---|",
        f"| Commission | {base.commission:.0%} | {best.commission:.0%} |",
        f"| Peak incentive (Rs/hr) | {base.incentive:.0f} | {best.incentive:.0f} |",
        f"| Completion rate | {base.completion_rate:.1%} | {best.completion_rate:.1%} |",
        f"| Avg pickup ETA (min) | {base.avg_eta_min:.2f} | {best.avg_eta_min:.2f} |",
        f"| Driver take-home (Rs/hr) | {base.driver_hourly:.0f} | {best.driver_hourly:.0f} |",
        f"| Contribution / day (Rs) | {base.contribution:,.0f} +/- {base.contribution_ci:,.0f} "
        f"| {best.contribution:,.0f} +/- {best.contribution_ci:,.0f} |",
        f"| Contribution / trip (Rs) | {base.contribution_per_trip:.1f} | {best.contribution_per_trip:.1f} |",
        "",
        f"- Feasible = driver take-home >= Rs {DRIVER_FLOOR:.0f}/hr and completion >= {COMPLETION_FLOOR:.0%}; "
        f"{len(feasible)} of {len(df)} policies qualify.",
        f"- Baseline feasible? {'yes' if base.driver_hourly >= DRIVER_FLOOR and base.completion_rate >= COMPLETION_FLOOR else 'no'}.",
        f"- Fixing driver pay with a flat commission cut alone needs {flat_best.commission:.0%} commission "
        f"and leaves Rs {flat_best.contribution:,.0f}/day.",
        f"- Shifting pay into peak hours ({best.commission:.0%} + Rs {best.incentive:.0f}/peak hour) meets the "
        f"same floor and keeps Rs {best.contribution - flat_best.contribution:,.0f}/day more "
        f"(+{best.contribution / flat_best.contribution - 1:.0%}); completion "
        f"{best.completion_rate:.1%} vs {flat_best.completion_rate:.1%}.",
    ]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
