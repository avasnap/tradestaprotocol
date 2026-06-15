"""
Shared aggregation + rendering helpers for TradeSta volume scripts.

Used by both plot_volume.py (DefiLlama reported volume) and
reconstruct_volume_onchain.py (on-chain ground truth) so the two render
identically and can be compared apples-to-apples.

A "series" is a list of (datetime.date, value_float) pairs (unaggregated).
"""
from __future__ import annotations

import csv
from collections import OrderedDict
from datetime import date
from pathlib import Path
from typing import Iterable, Optional


def bucket_series(
    series: Iterable[tuple[date, float]],
    granularity: str,
    since: Optional[date] = None,
) -> "OrderedDict[str, float]":
    """Sum a (date, value) series into daily / weekly / monthly buckets."""
    out: "OrderedDict[str, float]" = OrderedDict()
    for day, value in sorted(series):
        if since is not None and day < since:
            continue
        if granularity == "daily":
            key = day.isoformat()
        elif granularity == "weekly":
            iso = day.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
        else:  # monthly
            key = f"{day.year}-{day.month:02d}"
        out[key] = out.get(key, 0.0) + value
    return out


def fmt_usd(value: float) -> str:
    """Human-friendly USD with K/M/B suffix."""
    for unit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= unit:
            return f"${value / unit:,.2f}{suffix}"
    return f"${value:,.0f}"


def render_ascii(buckets: "OrderedDict[str, float]", title: str, width: int = 46) -> None:
    """Render a horizontal ASCII bar chart of the buckets to stdout."""
    print()
    print(title)
    print("-" * len(title))
    if not buckets:
        print("(no data in selected range)")
        return
    peak = max(buckets.values()) or 1.0
    label_w = max(len(k) for k in buckets)
    for key, value in buckets.items():
        bars = round(value / peak * width) if value > 0 else 0
        bar = "#" * max(1, bars) if value > 0 else ""
        print(f"{key:<{label_w}} | {bar:<{width}} {fmt_usd(value)}")


def write_csv(path: str | Path, buckets: "OrderedDict[str, float]", period_header: str) -> None:
    """Write the aggregated buckets to a two-column CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([period_header, "volume_usd"])
        for key, value in buckets.items():
            writer.writerow([key, f"{value:.2f}"])
    print(f"Wrote {path}")


def maybe_write_png(daily: list[tuple[date, float]], path: str | Path, title: str) -> None:
    """Write a daily bar-chart PNG if matplotlib is available, else skip."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        print("(--png skipped: matplotlib not installed — `pip install matplotlib`)")
        return
    if not daily:
        print("(--png skipped: no data)")
        return
    xs = [d for d, _ in daily]
    ys = [v for _, v in daily]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(xs, ys, width=1.0, color="#e84142")  # Avalanche red
    ax.set_title(title)
    ax.set_ylabel("Volume (USD)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.yaxis.set_major_formatter(lambda v, _: fmt_usd(v))
    fig.autofmt_xdate()
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    print(f"Wrote {path}")
