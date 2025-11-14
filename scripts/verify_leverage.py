#!/usr/bin/env python3
"""
Verify Max Leverage Usage Across All Markets

Analyzes PositionCreated events to determine the maximum leverage
ever used in each market.

Note: TradeSta doesn't have a global maxLeverage parameter on contracts.
Instead, traders can choose their leverage per position (typically up to
50x or 100x depending on the market, enforced during position creation).
"""

import sys
from pathlib import Path
from collections import Counter, defaultdict
import json
from web3 import Web3

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from utils.web3_helpers import Web3Helper, EVENT_SIGNATURES
from utils.routescan_api import RoutescanAPI

def main():
    print("="*80)
    print("TRADESTA LEVERAGE USAGE VERIFICATION")
    print("="*80)
    print("\nAnalyzing leverage from PositionCreated events across all markets...\n")

    w3_helper = Web3Helper()
    api = RoutescanAPI()

    MARKET_REGISTRY = '0x60F16B09A15F0c3210b40a735b19A6bAF235dd18'

    # Get MarketCreated events
    print("Fetching markets from MarketRegistry...")
    market_created_sig = '0x5eb977f82e9d0d89f65f05a56a99ab87e2ebb3909780e0b3642bec962789ba7a'

    market_events = api.get_all_logs(
        address=MARKET_REGISTRY,
        topic0=market_created_sig,
        from_block=63000000,
        offset=10000
    )

    total_markets = len(market_events)
    print(f'✅ Found {total_markets} markets\n')

    # Get PositionCreated event signature from EVENT_SIGNATURES
    position_created_sig = EVENT_SIGNATURES['PositionCreated']

    market_leverages = {}
    errors = []

    print(f"{'='*80}")
    print("ANALYZING POSITION LEVERAGE")
    print(f"{'='*80}\n")

    for i, market_event in enumerate(market_events, 1):
        # PositionManager address is in topics[2]
        pm_address = Web3Helper.to_checksum('0x' + market_event['topics'][2][-40:])

        # Query PositionCreated events for this market
        try:
            print(f'Market #{i:2d} ({pm_address}): Fetching positions...', end=' ')

            position_events = api.get_all_logs(
                address=pm_address,
                topic0=position_created_sig,
                from_block=63000000,
                offset=10000
            )

            if not position_events:
                print(f'No positions found')
                market_leverages[pm_address] = {
                    'max_leverage': 0,
                    'position_count': 0,
                    'leverage_distribution': {}
                }
                continue

            # Decode leverage from each event
            # PositionCreated has: positionId (indexed), owner (indexed), collateralAmount, positionSize, leverage, liquidationPrice, isLong, timestamp
            # leverage is the 3rd field (index 2) in the data
            leverages_used = []
            for pos_event in position_events:
                # Decode data field (contains non-indexed parameters)
                data = pos_event['data'][2:]  # Remove '0x'
                # Each uint256 is 64 hex chars (32 bytes)
                # Fields: collateralAmount (0-63), positionSize (64-127), leverage (128-191), ...
                if len(data) < 192:
                    continue  # Skip malformed events
                leverage_hex = data[128:192]
                if not leverage_hex:
                    continue
                # Leverage is stored as basis points (500 = 5x, 10000 = 100x)
                leverage = int(leverage_hex, 16) / 100
                leverages_used.append(int(leverage))

            max_lev = max(leverages_used)
            lev_counts = Counter(leverages_used)

            market_leverages[pm_address] = {
                'max_leverage': max_lev,
                'position_count': len(position_events),
                'leverage_distribution': dict(lev_counts)
            }

            print(f'{len(position_events):,} positions, max leverage: {max_lev}x')

        except Exception as e:
            errors.append((pm_address, str(e)))
            print(f'❌ Error - {e}')

    # Print summary
    print(f'\n{"="*80}')
    print("LEVERAGE VERIFICATION SUMMARY")
    print(f'{"="*80}\n')

    markets_with_positions = {addr: data for addr, data in market_leverages.items() if data['position_count'] > 0}

    if markets_with_positions:
        print(f'📊 Markets Analyzed: {len(markets_with_positions)}/{total_markets} (with positions)')
        print(f'   Total Positions: {sum(data["position_count"] for data in markets_with_positions.values()):,}')

        # Find overall max leverage
        overall_max = max(data['max_leverage'] for data in markets_with_positions.values())
        print(f'   Max Leverage Used: {overall_max}x')

        # Count markets by max leverage
        max_lev_by_market = Counter(data['max_leverage'] for data in markets_with_positions.values())
        print(f'\n📈 Markets by Maximum Leverage:')
        for lev, count in sorted(max_lev_by_market.items(), reverse=True):
            pct = (count / len(markets_with_positions)) * 100
            print(f'   {lev:3d}x max: {count:2d} markets ({pct:5.1f}%)')

        # Overall leverage usage across all positions
        all_leverages = []
        for data in markets_with_positions.values():
            for lev, count in data['leverage_distribution'].items():
                all_leverages.extend([lev] * count)

        if all_leverages:
            lev_usage = Counter(all_leverages)
            print(f'\n📊 Overall Leverage Usage (all {len(all_leverages):,} positions):')
            for lev, count in sorted(lev_usage.items(), reverse=True)[:10]:  # Top 10
                pct = (count / len(all_leverages)) * 100
                print(f'   {lev:3d}x: {count:6,} positions ({pct:5.1f}%)')

    if errors:
        print(f'\n⚠️  Errors: {len(errors)} markets failed analysis')

    print(f'\n{"="*80}')
    print("✅ VERIFICATION COMPLETE")
    print(f'{"="*80}\n')

    # Save results
    results = {
        'markets_analyzed': len(market_leverages),
        'markets_with_positions': len(markets_with_positions),
        'total_markets': total_markets,
        'total_positions': sum(data['position_count'] for data in market_leverages.values()),
        'max_leverage_observed': max((data['max_leverage'] for data in markets_with_positions.values()), default=0),
        'markets': {
            addr.lower(): data
            for addr, data in market_leverages.items()
        },
        'methodology': 'Analyzed PositionCreated events to determine actual leverage usage',
        'note': 'TradeSta does not have a global maxLeverage parameter - traders choose leverage per position'
    }

    output_file = Path('results/leverage_verified.json')
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'Results saved to: {output_file}\n')

if __name__ == '__main__':
    main()
