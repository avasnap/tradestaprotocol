#!/usr/bin/env python3
"""
TradeSta Volume-Over-Time

Pulls TradeSta's daily perpetuals trading volume from DefiLlama's public
derivatives API and renders it as a time series (ASCII chart + CSV) so you can
see how protocol volume has evolved over a window (default: since 2025-11-01,
the date of this repo's frozen snapshot).

Why DefiLlama:
    DefiLlama already runs a volume adapter for TradeSta, so daily USD notional
    is computed for you. This avoids reconstructing notional from raw on-chain
    position-open events. For an on-chain ground-truth alternative, extend the
    event scripts in scripts/ (see verify_events_enhanced.py) + Routescan utils.

Data source (no API key required):
    https://api.llama.fi/overview/derivatives             (find the slug)
    https://api.llama.fi/summary/derivatives/<slug>?dataType=dailyVolume

NETWORK NOTE:
    Needs outbound access to api.llama.fi. In a restricted-egress environment
    you will get HTTP 403 with body "Host not in allowlist" — add api.llama.fi
    to the environment's network egress allowlist first.
    Docs: https://code.claude.com/docs/en/claude-code-on-the-web

Usage:
    python3 scripts/plot_volume.py                          # monthly, since 2025-11-01
    python3 scripts/plot_volume.py --granularity weekly
    python3 scripts/plot_volume.py --since 2025-11-01 --png
    python3 scripts/plot_volume.py --list                   # list all Avalanche perp protocols
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime, date, timezone
from pathlib import Path

DEFILLAMA_BASE = "https://api.llama.fi"
DEFAULT_SLUG = "tradesta"
DEFAULT_SINCE = "2025-11-01"
USER_AGENT = "tradesta-verify/1.0 (+https://github.com/avasnap/tradestaprotocol)"


# --------------------------------------------------------------------------- #
# HTTP                                                                         #
# --------------------------------------------------------------------------- #
class EgressBlocked(SystemExit):
    """Raised when the egress proxy denies the data host (vs a normal 404)."""


def _egress_blocked(url: str, body: str) -> "NoReturn":
    """Print an actionable message when the egress proxy denies the host."""
    print("=" * 80)
    print("BLOCKED BY NETWORK EGRESS ALLOWLIST")
    print("=" * 80)
    print(f"URL : {url}")
    print(f"Says: {body.strip()}")
    print()
    print("Fix : add 'api.llama.fi' to this environment's network egress allowlist,")
    print("      then re-run this script.")
    print("Docs: https://code.claude.com/docs/en/claude-code-on-the-web")
    raise EgressBlocked(2)


def get_json(url: str) -> dict:
    """GET a URL and parse JSON, with a friendly message on egress denial."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if exc.code == 403 and "allowlist" in body.lower():
            _egress_blocked(url, body)
        raise SystemExit(f"HTTP {exc.code} fetching {url}\n{body[:400]}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Network error fetching {url}: {exc.reason}")


# --------------------------------------------------------------------------- #
# DefiLlama                                                                    #
# --------------------------------------------------------------------------- #
def list_avalanche_perps() -> list[dict]:
    """Return the list of perp/derivatives protocols tracked on Avalanche."""
    url = (
        f"{DEFILLAMA_BASE}/overview/derivatives/avalanche"
        "?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
    )
    data = get_json(url)
    return data.get("protocols", [])


def resolve_slug(name_or_slug: str) -> str:
    """
    Resolve a user-supplied name/slug to a DefiLlama derivatives slug.

    Tries the value as-is first; if the summary endpoint 404s, falls back to a
    case-insensitive name search across Avalanche perp protocols.
    """
    # Trust an explicit slug if the summary endpoint resolves.
    try:
        get_json(f"{DEFILLAMA_BASE}/summary/derivatives/{name_or_slug}?dataType=dailyVolume")
        return name_or_slug
    except EgressBlocked:
        raise  # host denied — propagate the actionable message
    except SystemExit:
        pass  # 404 / other fetch error — fall through to name search

    protocols = list_avalanche_perps()
    needle = name_or_slug.lower()
    matches = [
        p for p in protocols
        if needle in p.get("name", "").lower() or needle in str(p.get("slug", "")).lower()
    ]
    if not matches:
        names = ", ".join(sorted(p.get("name", "?") for p in protocols)) or "(none)"
        raise SystemExit(
            f"Could not find a protocol matching '{name_or_slug}'.\n"
            f"Avalanche perp protocols on DefiLlama: {names}"
        )
    slug = matches[0].get("slug") or matches[0].get("name", "").lower().replace(" ", "-")
    if len(matches) > 1:
        print(f"Note: multiple matches, using '{matches[0].get('name')}' ({slug})")
    return slug


def fetch_daily_volume(slug: str) -> tuple[dict, list[tuple[date, float]]]:
    """Fetch the daily-volume time series for a protocol slug."""
    data = get_json(f"{DEFILLAMA_BASE}/summary/derivatives/{slug}?dataType=dailyVolume")
    series: list[tuple[date, float]] = []
    for point in data.get("totalDataChart") or []:
        ts, val = point[0], point[1]
        day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        series.append((day, float(val or 0)))
    series.sort()
    return data, series


# --------------------------------------------------------------------------- #
# Aggregation + rendering                                                      #
# --------------------------------------------------------------------------- #
def bucket(series: list[tuple[date, float]], granularity: str, since: date) -> "OrderedDict[str, float]":
    """Sum volume into daily / weekly / monthly buckets, filtered to >= since."""
    out: "OrderedDict[str, float]" = OrderedDict()
    for day, vol in series:
        if day < since:
            continue
        if granularity == "daily":
            key = day.isoformat()
        elif granularity == "weekly":
            iso = day.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
        else:  # monthly
            key = f"{day.year}-{day.month:02d}"
        out[key] = out.get(key, 0.0) + vol
    return out


def fmt_usd(value: float) -> str:
    """Human-friendly USD with K/M/B suffix."""
    for unit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= unit:
            return f"${value / unit:,.2f}{suffix}"
    return f"${value:,.0f}"


def render_ascii(buckets: "OrderedDict[str, float]", title: str, width: int = 46) -> None:
    """Render a horizontal ASCII bar chart of the buckets."""
    print()
    print(title)
    print("-" * len(title))
    if not buckets:
        print("(no data in selected range)")
        return
    peak = max(buckets.values()) or 1.0
    label_w = max(len(k) for k in buckets)
    for key, vol in buckets.items():
        bars = round(vol / peak * width) if vol > 0 else 0
        bar = "#" * max(1, bars) if vol > 0 else ""
        print(f"{key:<{label_w}} | {bar:<{width}} {fmt_usd(vol)}")


def write_csv(path: Path, buckets: "OrderedDict[str, float]", period_header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([period_header, "volume_usd"])
        for key, vol in buckets.items():
            writer.writerow([key, f"{vol:.2f}"])
    print(f"Wrote {path}")


def maybe_write_png(daily: list[tuple[date, float]], path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("(--png skipped: matplotlib not installed — `pip install matplotlib`)")
        return
    xs = [d for d, _ in daily]
    ys = [v for _, v in daily]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(xs, ys, width=1.0, color="#e84142")  # Avalanche red
    ax.set_title("TradeSta — Daily Perp Volume (DefiLlama)")
    ax.set_ylabel("Volume (USD)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.yaxis.set_major_formatter(lambda v, _: fmt_usd(v))
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    print(f"Wrote {path}")


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Chart TradeSta perp volume over time (via DefiLlama).")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="DefiLlama protocol slug or name (default: tradesta)")
    parser.add_argument("--since", default=DEFAULT_SINCE, help="Start date YYYY-MM-DD (default: 2025-11-01)")
    parser.add_argument("--granularity", choices=("daily", "weekly", "monthly"), default="monthly",
                        help="ASCII chart bucket size (default: monthly)")
    parser.add_argument("--csv", metavar="PATH", help="Also write the chart buckets to this CSV path")
    parser.add_argument("--png", action="store_true", help="Also write a daily PNG to results/ (needs matplotlib)")
    parser.add_argument("--list", action="store_true", help="List Avalanche perp protocols and exit")
    args = parser.parse_args()

    if args.list:
        for proto in sorted(list_avalanche_perps(), key=lambda p: p.get("total24h") or 0, reverse=True):
            print(f"{proto.get('name','?'):<28} slug={proto.get('slug','?'):<24} "
                  f"24h={fmt_usd(proto.get('total24h') or 0)}")
        return

    try:
        since = date.fromisoformat(args.since)
    except ValueError:
        raise SystemExit(f"--since must be YYYY-MM-DD, got '{args.since}'")

    slug = resolve_slug(args.slug)
    meta, series = fetch_daily_volume(slug)

    print("=" * 80)
    print(f"TRADESTA VOLUME OVER TIME  (source: DefiLlama, slug='{slug}')")
    print("=" * 80)
    print(f"Protocol     : {meta.get('name', slug)}")
    if series:
        print(f"Data range   : {series[0][0]} -> {series[-1][0]}  ({len(series)} days)")
    print(f"24h volume   : {fmt_usd(meta.get('total24h') or 0)}")
    print(f"7d volume    : {fmt_usd(meta.get('total7d') or 0)}")
    print(f"All-time vol : {fmt_usd(meta.get('totalAllTime') or 0)}")

    windowed = [(d, v) for d, v in series if d >= since]
    if windowed:
        total = sum(v for _, v in windowed)
        peak_day, peak_val = max(windowed, key=lambda dv: dv[1])
        print(f"\nSince {since}: total {fmt_usd(total)} across {len(windowed)} days")
        print(f"Peak day     : {peak_day}  {fmt_usd(peak_val)}")
        print(f"Latest day   : {windowed[-1][0]}  {fmt_usd(windowed[-1][1])}")

    buckets = bucket(series, args.granularity, since)
    render_ascii(buckets, f"Volume by {args.granularity} since {since}")

    if args.csv:
        write_csv(Path(args.csv), buckets, args.granularity)
    if args.png:
        maybe_write_png(windowed, Path("results") / "tradesta_volume_daily.png")


if __name__ == "__main__":
    main()
