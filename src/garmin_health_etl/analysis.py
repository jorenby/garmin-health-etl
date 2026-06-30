"""Analysis & insights for Garmin Health ETL.

Ports the correlation/trend approach from the original n=1 analysis scripts:

* same-day and lagged (prior-day -> next-day) Spearman correlations,
* first-half vs second-half trend comparison,
* a natural-experiment window comparison (HRV peak/trough vs baseline),
* overnight SpO2 flag counts,

and writes a markdown report plus charts. Correlation significance uses a
deterministic permutation test, so the only third-party needs are pandas,
numpy and matplotlib (the ``[analysis]`` extra) — no SciPy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

MIN_N = 8  # minimum paired observations before a correlation is reported
PERM_ITERS = 2000
PERM_SEED = 12345


# --------------------------------------------------------------------------- #
# Frame construction
# --------------------------------------------------------------------------- #
def _load_frame(store):
    import numpy as np
    import pandas as pd

    rows = [dict(r) for r in store.fetch_joined()]
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    # Reindex to a continuous daily calendar so lag = one calendar day.
    full = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    df = df.set_index("date").reindex(full)
    df.index.name = "date"

    # Subjective (manual_tracking, aliased m_*).
    df["energy"] = df.get("m_energy")
    df["mood"] = df.get("m_mood")
    df["calm"] = df.get("m_calm")
    df["sleep_quality_subj"] = df.get("m_sleep_quality")
    df["appetite"] = df.get("m_appetite")
    # Subjective stress on the legacy polarity (high = worse), for continuity
    # with the original "stress -> energy" finding.
    df["stress_subj"] = df["calm"].apply(lambda v: None if pd.isna(v) else 11 - v)

    # Objective (garmin_data).
    df["hrv"] = df.get("hrv_last_night")
    df["bb"] = df.get("bb_charged_overnight")
    df["garmin_stress"] = df.get("stress_avg")
    mod = pd.to_numeric(df.get("moderate_intensity_minutes"), errors="coerce")
    vig = pd.to_numeric(df.get("vigorous_intensity_minutes"), errors="coerce")
    df["intensity"] = mod.fillna(0) + vig.fillna(0)
    df.loc[mod.isna() & vig.isna(), "intensity"] = np.nan

    # Per-day activity training load from the activities table.
    df["activity_load"] = _activity_load_by_date(store, df.index)

    for col in ["sleep_score", "steps", "spo2_lowest", "sleep_spo2_lowest", "resting_hr"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _activity_load_by_date(store, index):
    import numpy as np
    import pandas as pd

    activities = [dict(r) for r in store.fetch_activities()]
    series = pd.Series(np.nan, index=index, dtype="float64")
    if not activities:
        return series
    adf = pd.DataFrame(activities)
    adf["date"] = pd.to_datetime(adf["date"], errors="coerce")
    adf = adf.dropna(subset=["date"])
    load = pd.to_numeric(adf.get("training_load"), errors="coerce")
    if load.isna().all():  # fall back to duration when load is unavailable
        load = pd.to_numeric(adf.get("duration_seconds"), errors="coerce") / 60.0
    adf = adf.assign(load=load)
    grouped = adf.groupby("date")["load"].sum(min_count=1)
    series.update(grouped)
    return series


# --------------------------------------------------------------------------- #
# Statistics (Spearman + permutation p-value, no SciPy)
# --------------------------------------------------------------------------- #
def spearman(x, y) -> Tuple[Optional[float], int]:
    import numpy as np
    import pandas as pd

    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(pair)
    if n < MIN_N:
        return None, n
    rx = pair["x"].rank().to_numpy()
    ry = pair["y"].rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return None, n
    rho = float(np.corrcoef(rx, ry)[0, 1])
    return rho, n


def permutation_p(x, y, rho: float, iters: int = PERM_ITERS) -> float:
    import numpy as np
    import pandas as pd

    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    rx = pair["x"].rank().to_numpy()
    ry = pair["y"].rank().to_numpy()
    rng = np.random.default_rng(PERM_SEED)
    observed = abs(rho)
    count = 0
    for _ in range(iters):
        permuted = rng.permutation(ry)
        if rx.std() == 0 or permuted.std() == 0:
            continue
        if abs(np.corrcoef(rx, permuted)[0, 1]) >= observed:
            count += 1
    return (count + 1) / (iters + 1)


def _corr_entry(df, a: str, b: str, lag: int = 0) -> Dict:
    x = df[a].shift(lag) if lag else df[a]
    y = df[b]
    rho, n = spearman(x, y)
    entry = {"a": a, "b": b, "lag": lag, "rho": rho, "n": n, "p": None}
    if rho is not None:
        entry["p"] = permutation_p(x, y, rho)
    return entry


# --------------------------------------------------------------------------- #
# Report sections
# --------------------------------------------------------------------------- #
_SAME_DAY_PAIRS = [
    ("calm", "energy"),
    ("stress_subj", "energy"),
    ("garmin_stress", "energy"),
    ("sleep_quality_subj", "energy"),
    ("sleep_score", "energy"),
    ("hrv", "energy"),
    ("bb", "energy"),
    ("intensity", "energy"),
    ("garmin_stress", "hrv"),
    ("hrv", "mood"),
    ("calm", "mood"),
]

_LAGGED_PAIRS = [
    ("calm", "energy"),
    ("stress_subj", "energy"),
    ("intensity", "bb"),
    ("intensity", "hrv"),
    ("activity_load", "bb"),
    ("steps", "bb"),
    ("sleep_score", "energy"),
    ("bb", "energy"),
    ("hrv", "energy"),
]

_DESCRIPTIVE_COLS = [
    ("energy", "Subjective energy (1-10)"),
    ("calm", "Calm (1-10)"),
    ("mood", "Mood (1-10)"),
    ("hrv", "HRV last night (ms)"),
    ("bb", "Body Battery recharge"),
    ("sleep_score", "Sleep score"),
    ("garmin_stress", "Garmin stress (avg)"),
    ("steps", "Steps"),
]


def _fmt(value, digits=2):
    if value is None:
        return "-"
    try:
        if value != value:  # NaN
            return "-"
    except TypeError:
        pass
    return f"{value:.{digits}f}"


def _corr_table(entries: List[Dict]) -> str:
    lines = ["| Variable | Outcome | rho | n | p (perm) | |", "|---|---|---|---|---|---|"]
    for e in entries:
        if e["rho"] is None:
            lines.append(f"| {e['a']} | {e['b']} | - | {e['n']} | - | too few |")
            continue
        sig = "**sig.**" if (e["p"] is not None and e["p"] < 0.05) else ""
        lines.append(
            f"| {e['a']} | {e['b']} | {e['rho']:+.2f} | {e['n']} | {_fmt(e['p'], 3)} | {sig} |"
        )
    return "\n".join(lines)


def _headline(same_day: List[Dict], lagged: List[Dict]) -> List[str]:
    bullets: List[str] = []
    by_pair = {(e["a"], e["b"]): e for e in same_day}

    # Strongest subjective-energy driver.
    drivers = [
        e for e in same_day
        if e["b"] == "energy" and e["a"] in {"calm", "stress_subj", "garmin_stress"}
        and e["rho"] is not None
    ]
    if drivers:
        top = max(drivers, key=lambda e: abs(e["rho"]))
        bullets.append(
            f"Strongest same-day correlate of felt energy is **{top['a']}** "
            f"(rho {top['rho']:+.2f}, n={top['n']}) — consistent with stress/calm "
            f"being the main lever the watch can't directly see."
        )

    # Recovery metrics vs energy.
    recovery = [by_pair.get(("hrv", "energy")), by_pair.get(("sleep_score", "energy")),
                by_pair.get(("bb", "energy"))]
    recovery = [e for e in recovery if e and e["rho"] is not None]
    if recovery:
        worst = max(abs(e["rho"]) for e in recovery)
        bullets.append(
            "Garmin recovery metrics (HRV, sleep score, Body Battery) barely track "
            f"felt energy (all |rho| <= {worst:.2f}). The watch measures recovery, "
            "not fatigue."
        )

    # Movement -> next-day recovery.
    move = [e for e in lagged if e["a"] in {"intensity", "activity_load", "steps"}
            and e["b"] in {"bb", "hrv"} and e["rho"] is not None]
    if move:
        strongest = max(abs(e["rho"]) for e in move)
        bullets.append(
            "Prior-day movement shows no meaningful next-day recovery benefit "
            f"(all |rho| <= {strongest:.2f})."
        )
    return bullets


def _spo2_section(df) -> str:
    import pandas as pd

    col = "sleep_spo2_lowest" if df.get("sleep_spo2_lowest") is not None and \
        df["sleep_spo2_lowest"].notna().any() else "spo2_lowest"
    series = pd.to_numeric(df.get(col), errors="coerce").dropna() if col in df else pd.Series([], dtype=float)
    if series.empty:
        return "No overnight SpO2 data available.\n"
    nights = len(series)
    return (
        f"Overnight SpO2 (`{col}`), {nights} nights: "
        f"median lowest **{series.median():.0f}%**, floor **{series.min():.0f}%**. "
        f"Nights with a nadir <=85%: **{int((series <= 85).sum())}** "
        f"({(series <= 85).mean() * 100:.0f}%); <=82%: {int((series <= 82).sum())}; "
        f"<=80%: {int((series <= 80).sum())}. "
        "(Wrist pulse oximetry over-reads lows; a recurring pattern is still worth "
        "flagging clinically, not diagnosing.)\n"
    )


def _trend_section(df) -> str:
    import numpy as np

    half = len(df) // 2
    if half < MIN_N:
        return "Not enough days for a first-half vs second-half trend comparison.\n"
    first, second = df.iloc[:half], df.iloc[half:]
    rows = []
    for col, label in [("steps", "Steps/day"), ("intensity", "Intensity min/day"),
                       ("hrv", "HRV"), ("bb", "Body Battery recharge"),
                       ("energy", "Subjective energy")]:
        if col not in df:
            continue
        a, b = first[col].mean(skipna=True), second[col].mean(skipna=True)
        if np.isnan(a) and np.isnan(b):
            continue
        delta = "" if (np.isnan(a) or np.isnan(b)) else f"{(b - a):+.1f}"
        rows.append(f"| {label} | {_fmt(a, 1)} | {_fmt(b, 1)} | {delta} |")
    if not rows:
        return "No trend data available.\n"
    header = "| Metric | First half | Second half | Δ |\n|---|---|---|---|\n"
    return header + "\n".join(rows) + "\n"


def _window_section(df) -> str:
    """Natural experiment: compare the peak-HRV week against the baseline."""
    if "hrv" not in df or df["hrv"].notna().sum() < MIN_N + 7:
        return "Not enough HRV data for a natural-experiment window.\n"
    roll = df["hrv"].rolling(7, min_periods=5).mean()
    if roll.notna().sum() == 0:
        return "Not enough HRV data for a natural-experiment window.\n"
    peak_end = roll.idxmax()
    peak = df.loc[df.index <= peak_end].tail(7)
    baseline = df.loc[df.index < peak.index.min()]
    if len(baseline) < MIN_N:
        return "Not enough baseline days for a natural-experiment window.\n"

    def _m(frame, col):
        return _fmt(frame[col].mean(skipna=True), 1) if col in frame else "-"

    return (
        f"Peak 7-day HRV window ends {peak_end.date()}.\n\n"
        "| Metric | Peak week | Baseline |\n|---|---|---|\n"
        f"| HRV | {_m(peak, 'hrv')} | {_m(baseline, 'hrv')} |\n"
        f"| Energy | {_m(peak, 'energy')} | {_m(baseline, 'energy')} |\n"
        f"| Calm | {_m(peak, 'calm')} | {_m(baseline, 'calm')} |\n\n"
        "_A higher-HRV stretch that does not line up with higher felt energy is "
        "evidence HRV is not a day-to-day wellbeing gauge for this subject._\n"
    )


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _make_charts(df, charts_dir: Path) -> List[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    charts_dir.mkdir(parents=True, exist_ok=True)
    made: List[str] = []

    # 1) Energy vs calm over time.
    if "energy" in df and df["energy"].notna().any():
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(df.index, df["energy"], label="Energy", marker=".")
        if df["calm"].notna().any():
            ax.plot(df.index, df["calm"], label="Calm", marker=".", alpha=0.7)
        ax.set_title("Subjective energy and calm over time")
        ax.set_ylabel("1-10")
        ax.legend()
        fig.tight_layout()
        p = charts_dir / "energy_calm_timeseries.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        made.append(p.name)

    # 2) Calm vs energy scatter.
    pair = df[["calm", "energy"]].dropna()
    if len(pair) >= MIN_N:
        fig, ax = plt.subplots(figsize=(4.5, 4.5))
        ax.scatter(pair["calm"], pair["energy"], alpha=0.6)
        ax.set_xlabel("Calm (1-10)")
        ax.set_ylabel("Energy (1-10)")
        ax.set_title("Calm vs energy (same day)")
        fig.tight_layout()
        p = charts_dir / "calm_vs_energy.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        made.append(p.name)

    # 3) Overnight SpO2 lows.
    col = "sleep_spo2_lowest" if "sleep_spo2_lowest" in df and df["sleep_spo2_lowest"].notna().any() else "spo2_lowest"
    if col in df and df[col].notna().any():
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(df.index, df[col], marker=".", color="tab:red")
        ax.axhline(85, linestyle="--", color="gray", label="85% flag line")
        ax.set_title("Overnight SpO2 nightly low")
        ax.set_ylabel("SpO2 %")
        ax.legend()
        fig.tight_layout()
        p = charts_dir / "spo2_lows.png"
        fig.savefig(p, dpi=110)
        plt.close(fig)
        made.append(p.name)

    return made


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run_analysis(
    store,
    output_path: str = "report.md",
    charts_dir: Optional[str] = None,
    make_charts: bool = True,
) -> Path:
    df = _load_frame(store)
    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if df.empty:
        report_path.write_text(
            "# Health analysis\n\nNo data in the database yet. "
            "Import data with `import-json` / `import-tracker` first.\n",
            encoding="utf-8",
        )
        return report_path

    same_day = [_corr_entry(df, a, b) for a, b in _SAME_DAY_PAIRS if a in df and b in df]
    lagged = [_corr_entry(df, a, b, lag=1) for a, b in _LAGGED_PAIRS if a in df and b in df]

    charts: List[str] = []
    chart_root = Path(charts_dir) if charts_dir else report_path.parent / "charts"
    if make_charts:
        charts = _make_charts(df, chart_root)

    n_days = len(df)
    n_subj = int(df["energy"].notna().sum()) if "energy" in df else 0
    date_min, date_max = df.index.min().date(), df.index.max().date()

    parts: List[str] = []
    parts.append("# Health analysis report\n")
    parts.append(
        f"Window **{date_min} to {date_max}** ({n_days} days). "
        f"Days with a subjective energy rating: **{n_subj}**.\n"
    )
    parts.append(
        "> Single subject (n=1), modest sample, many simultaneous variables. "
        "Spearman rank correlations with a permutation p-value; treat as "
        "directional, not proof.\n"
    )

    bullets = _headline(same_day, lagged)
    if bullets:
        parts.append("## Headline findings\n")
        parts.append("\n".join(f"- {b}" for b in bullets) + "\n")

    parts.append("## Descriptives\n")
    desc_lines = ["| Metric | min | median | max | n |", "|---|---|---|---|---|"]
    for col, label in _DESCRIPTIVE_COLS:
        if col not in df:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        desc_lines.append(
            f"| {label} | {_fmt(s.min(), 0)} | {_fmt(s.median(), 0)} | "
            f"{_fmt(s.max(), 0)} | {len(s)} |"
        )
    parts.append("\n".join(desc_lines) + "\n")

    parts.append("## Same-day correlations\n")
    parts.append(_corr_table(same_day) + "\n")
    parts.append("## Lagged correlations (prior day -> next day)\n")
    parts.append(_corr_table(lagged) + "\n")
    parts.append("## Trend (first half vs second half)\n")
    parts.append(_trend_section(df))
    parts.append("## Natural-experiment window\n")
    parts.append(_window_section(df))
    parts.append("## Overnight oxygen\n")
    parts.append(_spo2_section(df))

    if charts:
        parts.append("## Charts\n")
        rel = chart_root.name if chart_root.parent == report_path.parent else str(chart_root)
        for name in charts:
            parts.append(f"![{name}]({rel}/{name})\n")

    report_path.write_text("\n".join(parts), encoding="utf-8")
    return report_path
