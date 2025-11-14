#!/usr/bin/env python3
"""
Verify Max Leverage Configuration Across All Markets

This script verifies leverage settings by:
1. Querying MarketRegistry for configured max leverage per market
2. Analyzing actual leverage usage from PositionCreated events
3. Comparing configured limits vs actual usage

The configured max leverage is stored in MarketRegistry.markets[pricefeedId].maximumLeverage
"""

import sys
from pathlib import Path
from collections import Counter, defaultdict
import json
from web3 import Web3
from eth_abi import decode

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from utils.web3_helpers import Web3Helper, EVENT_SIGNATURES
from utils.routescan_api import RoutescanAPI

def main():
    print("="*80)
    print("TRADESTA LEVERAGE VERIFICATION")
    print("="*80)
    print("\nVerifying configured max leverage and actual usage across all markets...\n")

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

    market_data = {}
    errors = []

    print(f"{'='*80}")
    print("QUERYING CONFIGURED MAX LEVERAGE")
    print(f"{'='*80}\n")

    # Query configured max leverage for each market
    for i, market_event in enumerate(market_events, 1):
        pricefeed_id = market_event['topics'][1]
        pm_address = Web3Helper.to_checksum('0x' + market_event['topics'][2][-40:])

        try:
            # Query markets(pricefeedId) to get market data
            function_sig = Web3.keccak(text='markets(bytes32)')[:4]
            call_data = function_sig + bytes.fromhex(pricefeed_id[2:])

            result = w3_helper.w3.eth.call({
                'to': MARKET_REGISTRY,
                'data': call_data.hex()
            })

            # Decode: (string, bytes32, address, address, address, address, uint256, uint256, uint256, uint256, uint256)
            types = ['string', 'bytes32', 'address', 'address', 'address', 'address',
                    'uint256', 'uint256', 'uint256', 'uint256', 'uint256']
            decoded = decode(types, result)

            symbol = decoded[0]
            max_leverage_configured = decoded[9] / 100  # Convert from basis points

            market_data[pm_address] = {
                'symbol': symbol,
                'pricefeed_id': pricefeed_id,
                'max_leverage_configured': int(max_leverage_configured),
                'position_count': 0,
                'max_leverage_used': 0,
                'leverage_distribution': {}
            }

            print(f'Market #{i:2d} ({symbol:10s}): Configured max leverage = {max_leverage_configured:.0f}x')

        except Exception as e:
            errors.append((pm_address, f"Config query failed: {e}"))
            print(f'Market #{i:2d} ({pm_address}): ❌ Error - {e}')

    print(f"\n{'='*80}")
    print("ANALYZING ACTUAL LEVERAGE USAGE")
    print(f"{'='*80}\n")

    # Now analyze actual usage from PositionCreated events
    for i, (pm_address, data) in enumerate(market_data.items(), 1):
        try:
            symbol = data['symbol']
            print(f'Market #{i:2d} ({symbol:10s}): Fetching positions...', end=' ')

            position_events = api.get_all_logs(
                address=pm_address,
                topic0=position_created_sig,
                from_block=63000000,
                offset=10000
            )

            if not position_events:
                print(f'No positions found')
                continue

            # Decode leverage from each event
            leverages_used = []
            for pos_event in position_events:
                event_data = pos_event['data'][2:]  # Remove '0x'
                if len(event_data) < 192:
                    continue
                leverage_hex = event_data[128:192]
                if not leverage_hex:
                    continue
                # Leverage stored as basis points (10000 = 100x)
                leverage = int(leverage_hex, 16) / 100
                leverages_used.append(int(leverage))

            if leverages_used:
                max_lev_used = max(leverages_used)
                lev_counts = Counter(leverages_used)

                data['position_count'] = len(position_events)
                data['max_leverage_used'] = max_lev_used
                data['leverage_distribution'] = dict(lev_counts)

                # Check if anyone exceeded configured limit
                exceeded = "⚠️  EXCEEDED!" if max_lev_used > data['max_leverage_configured'] else ""
                print(f'{len(position_events):,} positions, max used: {max_lev_used}x {exceeded}')
            else:
                print(f'{len(position_events):,} positions (could not decode leverage)')

        except Exception as e:
            errors.append((pm_address, f"Usage analysis failed: {e}"))
            print(f'❌ Error - {e}')

    # Print summary
    print(f'\n{"="*80}')
    print("LEVERAGE VERIFICATION SUMMARY")
    print(f'{"="*80}\n')

    markets_with_positions = {addr: data for addr, data in market_data.items() if data['position_count'] > 0}

    if markets_with_positions:
        print(f'📊 Markets Analyzed: {len(markets_with_positions)}/{total_markets} (with positions)')
        print(f'   Total Positions: {sum(data["position_count"] for data in markets_with_positions.values()):,}')

        # Configured limits
        configured_limits = Counter(data['max_leverage_configured'] for data in market_data.values())
        print(f'\n⚙️  Configured Maximum Leverage:')
        for lev, count in sorted(configured_limits.items(), reverse=True):
            pct = (count / len(market_data)) * 100
            print(f'   {lev:3d}x: {count:2d} markets ({pct:5.1f}%)')

        # Actual usage maximums
        max_lev_by_market = Counter(data['max_leverage_used'] for data in markets_with_positions.values())
        print(f'\n📈 Maximum Leverage Actually Used:')
        for lev, count in sorted(max_lev_by_market.items(), reverse=True)[:10]:
            pct = (count / len(markets_with_positions)) * 100
            print(f'   {lev:3d}x: {count:2d} markets ({pct:5.1f}%)')

        # Check for violations
        violations = [(addr, data) for addr, data in markets_with_positions.items()
                     if data['max_leverage_used'] > data['max_leverage_configured']]

        if violations:
            print(f'\n⚠️  WARNING: {len(violations)} market(s) have positions exceeding configured limits!')
            for addr, data in violations:
                print(f'   {data["symbol"]}: configured={data["max_leverage_configured"]}x, used={data["max_leverage_used"]}x')
        else:
            print(f'\n✅ All positions respect configured leverage limits')

        # Overall leverage usage stats
        all_leverages = []
        for data in markets_with_positions.values():
            for lev, count in data['leverage_distribution'].items():
                all_leverages.extend([lev] * count)

        if all_leverages:
            lev_usage = Counter(all_leverages)
            print(f'\n📊 Overall Leverage Usage (all {len(all_leverages):,} positions):')
            for lev, count in sorted(lev_usage.items(), reverse=True)[:10]:
                pct = (count / len(all_leverages)) * 100
                print(f'   {lev:3d}x: {count:6,} positions ({pct:5.1f}%)')

    if errors:
        print(f'\n⚠️  Errors: {len(errors)} markets had errors')

    print(f'\n{"="*80}')
    print("✅ VERIFICATION COMPLETE")
    print(f'{"="*80}\n')

    # Save results
    results = {
        'markets_analyzed': len(market_data),
        'markets_with_positions': len(markets_with_positions),
        'total_markets': total_markets,
        'total_positions': sum(data['position_count'] for data in market_data.values()),
        'configured_max_leverage': max((data['max_leverage_configured'] for data in market_data.values()), default=0),
        'max_leverage_actually_used': max((data['max_leverage_used'] for data in markets_with_positions.values()), default=0),
        'violations': len(violations) if markets_with_positions else 0,
        'markets': {
            addr.lower(): data
            for addr, data in market_data.items()
        },
        'methodology': 'Queried MarketRegistry.markets() for configured limits, analyzed PositionCreated events for actual usage'
    }

    output_file = Path('results/leverage_verified.json')
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'Results saved to: {output_file}\n')

if __name__ == '__main__':
    main()
