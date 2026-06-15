#!/usr/bin/env python3
"""
TradeSta On-Chain Volume Reconstruction (ground truth)

Reconstructs TradeSta perpetuals trading volume directly from on-chain
PositionCreated events -- NOT from any third-party volume adapter. For every
market it sums each new position's notional `positionSize` and buckets it by
the event's own on-chain `timestamp`, giving volume over time.

PositionManager event (see ABI_ANALYSIS_FINDINGS.md):
    PositionCreated(
        bytes32 indexed positionId,   # topics[1]
        address indexed owner,        # topics[2]
        uint256 collateralAmount,     # data word 0
        uint256 positionSize,         # data word 1  <- notional, scaled 1e6 (USDC)
        uint256 leverage,             # data word 2  (scaled 1e4)
        uint256 liquidationPrice,     # data word 3
        bool    isLong,               # data word 4
        uint256 timestamp             # data word 5  <- open time (unix)
    )

Why this only needs Routescan (no Avalanche RPC):
    The event carries `positionSize` (the volume) AND `timestamp` (the time
    bucket) in its data, so we never have to resolve block -> time over RPC.

Built-in correctness check:
    notional = collateral x leverage, so for each event
        positionSize / collateralAmount  ~=  leverage / 1e4
    The script reports observed vs stated leverage; a match confirms both the
    field offsets and the 1e6 USDC scale (i.e. volume = positionSize / 1e6).

Data source: Routescan API event logs only.

NETWORK NOTE:
    Needs outbound access to api.routescan.io. On a restricted-egress
    environment you'll get HTTP 403 "Host not in allowlist" -- add
    api.routescan.io to the network egress allowlist first.
    Docs: https://code.claude.com/docs/en/claude-code-on-the-web

Usage:
    python3 scripts/reconstruct_volume_onchain.py                 # all markets, monthly, since 2025-11-01
    python3 scripts/reconstruct_volume_onchain.py --sample 3      # top-3 markets only (fast)
    python3 scripts/reconstruct_volume_onchain.py --granularity weekly --csv results/onchain_vol.csv
    python3 scripts/reconstruct_volume_onchain.py --png
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from utils.chart import bucket_series, fmt_usd, maybe_write_png, render_ascii, write_csv
from utils.routescan_api import RoutescanAPI

# --- Protocol constants ---------------------------------------------------- #
MARKET_REGISTRY = "0x60f16b09a15f0c3210b40a735b19a6baf235dd18"
MARKET_CREATED_SIG = "0x5eb977f82e9d0d89f65f05a56a99ab87e2ebb3909780e0b3642bec962789ba7a"
# keccak256("PositionCreated(bytes32,address,uint256,uint256,uint256,uint256,bool,uint256)")
POSITION_CREATED_SIG = "0x52055f6ec9a38bd7aced9d289a234dc894a9537b635ebca189454066a91c7a36"

DEPLOY_BLOCK = 63_000_000
TO_BLOCK = 99_999_999          # "all" -- avoids needing an RPC for latest block
DEFAULT_SINCE = "2025-11-01"
USDC_DECIMALS = 6              # positionSize / collateralAmount scale
LEVERAGE_SCALE = 1e4           # leverage field scale (see ABI_ANALYSIS_FINDINGS.md)

# Known market labels (others fall back to a short address).
KNOWN_MARKETS = {
    "0x8d07fa9ac8b4bf833f099fb24971d2a808874c25": "AVAX/USD",
    "0x7da6e6d1b3582a2348fa76b3fe3b5e88d95281e7": "BTC/USD",
    "0x5bd078689c358ca2c64daff8761dbf8cfddfc51f": "ETH/USD",
}


# --- Decoding -------------------------------------------------------------- #
def _word(data_hex: str, index: int) -> int:
    """Return data word `index` (a uint256) as an int. Strips a 0x prefix."""
    body = data_hex[2:] if data_hex.startswith("0x") else data_hex
    start = index * 64
    return int(body[start:start + 64], 16)


def _event_day(event: dict, ts_from_data: int) -> date | None:
    """Pick a sane open-time for an event: the data timestamp, else log meta."""
    ts = ts_from_data
    if not (1_500_000_000 <= ts <= 2_000_000_000):  # ~2017..2033 sanity window
        meta = event.get("timeStamp")
        try:
            ts = int(meta, 16) if isinstance(meta, str) else int(meta)
        except (TypeError, ValueError):
            return None
    if not (1_500_000_000 <= ts <= 2_000_000_000):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


# --- Routescan ------------------------------------------------------------- #
def discover_markets(api: RoutescanAPI) -> list[dict]:
    """Return [{name, position_manager}] for every market via MarketCreated."""
    print("Discovering markets from MarketRegistry (MarketCreated events)...")
    events = api.get_all_logs(
        address=MARKET_REGISTRY, topic0=MARKET_CREATED_SIG,
        from_block=DEPLOY_BLOCK, to_block=TO_BLOCK, offset=10000,
    )
    markets, seen = [], set()
    for event in events:
        topics = event.get("topics") or []
        if len(topics) < 3:
            continue
        pm = ("0x" + topics[2][-40:]).lower()
        if pm in seen:
            continue
        seen.add(pm)
        markets.append({"name": KNOWN_MARKETS.get(pm, f"market-{pm[:10]}"), "position_manager": pm})
    print(f"  Found {len(markets)} markets")
    return markets


def market_positions(api: RoutescanAPI, pm_address: str) -> tuple[list, list]:
    """
    Return (series, samples) for one market.

    series  : list of (date, notional_usd) per PositionCreated event
    samples : list of (size_raw, collateral_raw, leverage_raw) for sanity check
    """
    events = api.get_all_logs(
        address=pm_address, topic0=POSITION_CREATED_SIG,
        from_block=DEPLOY_BLOCK, to_block=TO_BLOCK, offset=10000,
    )
    scale = 10 ** USDC_DECIMALS
    series, samples = [], []
    for event in events:
        data = event.get("data") or ""
        body = data[2:] if data.startswith("0x") else data
        if len(body) < 6 * 64:          # need 6 data words
            continue
        collateral = _word(data, 0)
        size = _word(data, 1)
        leverage = _word(data, 2)
        day = _event_day(event, _word(data, 5))
        if day is None:
            continue
        series.append((day, size / scale))
        if collateral > 0 and len(samples) < 500:
            samples.append((size, collateral, leverage))
    return series, samples


# --- Sanity check ---------------------------------------------------------- #
def report_sanity(samples: list, n_positions: int) -> None:
    print("\n" + "-" * 80)
    print("DECODING SANITY CHECK")
    print("-" * 80)
    if not samples:
        print("(no samples with positive collateral to check)")
        return
    stated = [lev / LEVERAGE_SCALE for _, _, lev in samples]
    implied = [size / col for size, col, _ in samples]   # notional/collateral ~= leverage
    notionals = [size / 10 ** USDC_DECIMALS for size, _, _ in samples]
    med_stated, med_implied = statistics.median(stated), statistics.median(implied)
    print(f"Samples checked          : {len(samples)} of {n_positions} positions")
    print(f"Median stated leverage   : {med_stated:.2f}x   (leverage field / 1e4)")
    print(f"Median implied leverage  : {med_implied:.2f}x   (positionSize / collateralAmount)")
    agree = med_stated > 0 and abs(med_stated - med_implied) / med_stated < 0.05
    print(f"Agreement (<5%)          : {'YES -> 1e6 USDC scale confirmed' if agree else 'NO -> check --usdc-decimals / offsets'}")
    print(f"Median position notional : {fmt_usd(statistics.median(notionals))}")
    print(f"Largest position notional: {fmt_usd(max(notionals))}")


# --- Main ------------------------------------------------------------------ #
def main() -> None:
    global USDC_DECIMALS
    parser = argparse.ArgumentParser(description="Reconstruct TradeSta perp volume over time from on-chain events.")
    parser.add_argument("--since", default=DEFAULT_SINCE, help="Start date YYYY-MM-DD (default: 2025-11-01)")
    parser.add_argument("--granularity", choices=("daily", "weekly", "monthly"), default="monthly",
                        help="ASCII chart bucket size (default: monthly)")
    parser.add_argument("--sample", type=int, metavar="N", help="Only the first N known markets (fast smoke test)")
    parser.add_argument("--csv", metavar="PATH", help="Also write the chart buckets to this CSV path")
    parser.add_argument("--png", action="store_true", help="Also write a daily PNG to results/ (needs matplotlib)")
    parser.add_argument("--usdc-decimals", type=int, default=USDC_DECIMALS,
                        help=f"positionSize scale (default: {USDC_DECIMALS}); override if the sanity check disagrees")
    args = parser.parse_args()
    USDC_DECIMALS = args.usdc_decimals

    try:
        since = date.fromisoformat(args.since)
    except ValueError:
        raise SystemExit(f"--since must be YYYY-MM-DD, got '{args.since}'")

    api = RoutescanAPI(cache_dir="cache")

    if args.sample:
        markets = [{"name": n, "position_manager": a} for a, n in KNOWN_MARKETS.items()][:args.sample]
        print(f"Sample mode: {len(markets)} known market(s)")
    else:
        markets = discover_markets(api)

    all_series, all_samples, per_market = [], [], []
    for market in markets:
        print(f"\n[{market['name']}] {market['position_manager']}")
        series, samples = market_positions(api, market["position_manager"])
        total = sum(v for _, v in series)
        per_market.append((market["name"], total, len(series)))
        all_series.extend(series)
        all_samples.extend(samples)
        print(f"  {len(series):,} positions, notional {fmt_usd(total)}")

    print("\n" + "=" * 80)
    print("TRADESTA VOLUME OVER TIME  (source: on-chain PositionCreated events)")
    print("=" * 80)
    if not all_series:
        print("No PositionCreated events found.")
        return

    all_series.sort()
    total_all = sum(v for _, v in all_series)
    windowed = [(d, v) for d, v in all_series if d >= since]
    print(f"Markets scanned : {len(markets)}")
    print(f"Positions total : {len(all_series):,}")
    print(f"Data range      : {all_series[0][0]} -> {all_series[-1][0]}")
    print(f"All-time volume : {fmt_usd(total_all)}")
    if windowed:
        print(f"Since {since}   : {fmt_usd(sum(v for _, v in windowed))} across {len(windowed):,} positions")
        print(f"Last position   : {windowed[-1][0]}")

    report_sanity(all_samples, len(all_series))

    print("\nTop markets by all-time notional:")
    for name, total, count in sorted(per_market, key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {name:<22} {fmt_usd(total):>12}  ({count:,} positions)")

    buckets = bucket_series(all_series, args.granularity, since)
    render_ascii(buckets, f"On-chain volume by {args.granularity} since {since}")

    if args.csv:
        write_csv(Path(args.csv), buckets, args.granularity)
    if args.png:
        maybe_write_png(windowed, Path("results") / "tradesta_volume_onchain.png",
                        "TradeSta — Daily Perp Volume (on-chain)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- surface a friendly egress hint
        text = f"{exc} {getattr(getattr(exc, 'response', None), 'text', '')}".lower()
        if "allowlist" in text or "host_not_allowed" in text or "403" in text:
            print("=" * 80)
            print("BLOCKED BY NETWORK EGRESS ALLOWLIST")
            print("=" * 80)
            print("This script needs outbound access to api.routescan.io.")
            print("Add 'api.routescan.io' to this environment's network egress allowlist,")
            print("then re-run. Docs: https://code.claude.com/docs/en/claude-code-on-the-web")
            sys.exit(2)
        raise
