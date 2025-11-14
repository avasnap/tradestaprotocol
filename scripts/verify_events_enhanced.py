#!/usr/bin/env python3
"""
TradeSta Event Statistics Verification Script (Enhanced)

Enhanced version that tracks ALL liquidation mechanisms:
- PositionCreated events (position count per market)
- PositionClosed events (normal closures)
- PositionLiquidated events (price-based liquidations)
- CollateralSeized events (funding-based liquidations) ⭐ NEW
- LimitOrderExecuted events (order activity)

This script uses ONLY public data sources:
- Routescan API for event logs (with pagination)
- No MongoDB or private infrastructure required

Key Improvements:
- Tracks BOTH liquidation mechanisms (price + funding)
- Accurate liquidation rate calculations
- Position lifecycle verification
- Better metrics and reporting
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper, EVENT_SIGNATURES
from web3 import Web3

class EnhancedEventVerifier:
    """Verify TradeSta protocol event statistics with complete liquidation tracking"""

    def __init__(self, sample_size: int = None):
        self.api = RoutescanAPI(cache_dir="cache")
        self.w3 = Web3Helper()
        self.sample_size = sample_size

        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latest_block": self.w3.get_latest_block(),
            "block_range": {
                "from": 63_000_000,  # TradeSta deployment start
                "to": None  # Will be set to latest block
            },
            "markets": [],
            "summary": {
                "total_markets_verified": 0,
                "total_positions_created": 0,
                "total_positions_closed": 0,
                "total_price_liquidations": 0,
                "total_funding_liquidations": 0,
                "total_liquidations": 0,
                "total_orders_executed": 0
            },
            "verification_method": "public_api_with_complete_liquidation_tracking",
            "sample_verification": sample_size is not None,
            "improvements": [
                "Tracks CollateralSeized events (funding liquidations)",
                "Accurate total liquidation rate",
                "Separate price vs funding liquidation metrics",
                "Position lifecycle verification"
            ]
        }

        self.results["block_range"]["to"] = self.results["latest_block"]

        # Top 3 markets for sample, or will be populated from MarketCreated events
        self.sample_markets = [
            {
                "name": "AVAX/USD",
                "position_manager": Web3.to_checksum_address("0x8d07fa9ac8b4bf833f099fb24971d2a808874c25")
            },
            {
                "name": "BTC/USD",
                "position_manager": Web3.to_checksum_address("0x7da6e6d1b3582a2348fa76b3fe3b5e88d95281e7")
            },
            {
                "name": "ETH/USD",
                "position_manager": Web3.to_checksum_address("0x5bd078689c358ca2c64daff8761dbf8cfddfc51f")
            }
        ]

        # CollateralSeized event signature
        # event CollateralSeized(bytes32 indexed positionId, address indexed owner, uint256 collateralAmount, int256 fundingFees, uint256 timestamp)
        self.collateral_seized_sig = Web3.keccak(text='CollateralSeized(bytes32,address,uint256,int256,uint256)').hex()

    def get_markets_to_verify(self) -> List[Dict[str, str]]:
        """Get list of markets to verify"""
        if self.sample_size:
            return self.sample_markets[:self.sample_size]
        else:
            # For full verification, query all markets from MarketCreated events
            print("\nQuerying all markets from MarketRegistry...")
            market_registry = Web3.to_checksum_address('0x60f16b09a15f0c3210b40a735b19a6baf235dd18')
            market_created_sig = '0x5eb977f82e9d0d89f65f05a56a99ab87e2ebb3909780e0b3642bec962789ba7a'

            events = self.api.get_all_logs(
                address=market_registry,
                topic0=market_created_sig,
                from_block=63_000_000,
                to_block=self.results["latest_block"],
                offset=10000
            )

            markets = []
            for i, event in enumerate(events, 1):
                topics = event['topics']
                position_manager = '0x' + topics[2][-40:]

                # Decode symbol from data field (would need full ABI decoding)
                # For now, use market number
                markets.append({
                    "name": f"Market #{i}",
                    "position_manager": Web3.to_checksum_address(position_manager)
                })

            print(f"✅ Found {len(markets)} markets")
            return markets

    def verify_position_created_events(self, market: Dict[str, str]) -> int:
        """Count PositionCreated events for a market"""
        print(f"\n  Querying PositionCreated events...")

        events = self.api.get_all_logs(
            address=market["position_manager"],
            topic0=EVENT_SIGNATURES["PositionCreated"],
            from_block=self.results["block_range"]["from"],
            to_block=self.results["block_range"]["to"],
            offset=10000
        )

        count = len(events)
        print(f"  ✅ Found {count:,} PositionCreated events")

        return count

    def verify_position_closed_events(self, market: Dict[str, str]) -> int:
        """Count PositionClosed events for a market"""
        print(f"\n  Querying PositionClosed events...")

        events = self.api.get_all_logs(
            address=market["position_manager"],
            topic0=EVENT_SIGNATURES["PositionClosed"],
            from_block=self.results["block_range"]["from"],
            to_block=self.results["block_range"]["to"],
            offset=10000
        )

        count = len(events)
        print(f"  ✅ Found {count:,} PositionClosed events")

        return count

    def verify_price_liquidation_events(self, market: Dict[str, str]) -> int:
        """Count PositionLiquidated events (price-based liquidations)"""
        print(f"\n  Querying PositionLiquidated events (price-based)...")

        events = self.api.get_all_logs(
            address=market["position_manager"],
            topic0=EVENT_SIGNATURES["PositionLiquidated"],
            from_block=self.results["block_range"]["from"],
            to_block=self.results["block_range"]["to"],
            offset=10000
        )

        count = len(events)
        print(f"  ✅ Found {count:,} PositionLiquidated events")

        return count

    def verify_funding_liquidation_events(self, market: Dict[str, str]) -> int:
        """Count CollateralSeized events (funding-based liquidations)"""
        print(f"\n  Querying CollateralSeized events (funding-based) ⭐ NEW...")

        events = self.api.get_all_logs(
            address=market["position_manager"],
            topic0=self.collateral_seized_sig,
            from_block=self.results["block_range"]["from"],
            to_block=self.results["block_range"]["to"],
            offset=10000
        )

        count = len(events)
        print(f"  ✅ Found {count:,} CollateralSeized events")

        return count

    def verify_market(self, market: Dict[str, str]):
        """Verify all event statistics for a single market"""
        print(f"\n{'='*80}")
        print(f"VERIFYING MARKET: {market['name']}")
        print(f"{'='*80}")
        print(f"PositionManager: {market['position_manager']}")

        market_data = {
            "name": market["name"],
            "position_manager": market["position_manager"].lower(),
            "events": {}
        }

        # Count each event type
        positions_created = self.verify_position_created_events(market)
        positions_closed = self.verify_position_closed_events(market)
        price_liquidations = self.verify_price_liquidation_events(market)
        funding_liquidations = self.verify_funding_liquidation_events(market)

        total_liquidations = price_liquidations + funding_liquidations
        total_settled = positions_closed + total_liquidations
        open_positions = positions_created - total_settled

        market_data["events"] = {
            "positions_created": positions_created,
            "positions_closed": positions_closed,
            "price_liquidations": price_liquidations,
            "funding_liquidations": funding_liquidations,
            "total_liquidations": total_liquidations,
            "total_settled": total_settled,
            "open_positions": open_positions
        }

        # Update summary
        self.results["summary"]["total_positions_created"] += positions_created
        self.results["summary"]["total_positions_closed"] += positions_closed
        self.results["summary"]["total_price_liquidations"] += price_liquidations
        self.results["summary"]["total_funding_liquidations"] += funding_liquidations
        self.results["summary"]["total_liquidations"] += total_liquidations

        # Calculate derived metrics
        if positions_created > 0:
            market_data["metrics"] = {
                "price_liquidation_rate": (price_liquidations / positions_created) * 100,
                "funding_liquidation_rate": (funding_liquidations / positions_created) * 100,
                "total_liquidation_rate": (total_liquidations / positions_created) * 100,
                "closure_rate": (positions_closed / positions_created) * 100,
                "settlement_rate": (total_settled / positions_created) * 100,
                "lifecycle_complete": (total_settled / positions_created) * 100
            }

        self.results["markets"].append(market_data)

        # Print summary
        print(f"\n  📊 Market Summary:")
        print(f"     Positions Created: {positions_created:,}")
        print(f"     Positions Closed: {positions_closed:,}")
        print(f"     Price Liquidations: {price_liquidations:,}")
        print(f"     Funding Liquidations: {funding_liquidations:,} ⭐ NEW")
        print(f"     Total Liquidations: {total_liquidations:,}")
        print(f"     Total Settled: {total_settled:,}")
        print(f"     Open Positions: {open_positions:,}")

        if positions_created > 0:
            print(f"\n  📈 Metrics:")
            print(f"     Price Liquidation Rate: {market_data['metrics']['price_liquidation_rate']:.2f}%")
            print(f"     Funding Liquidation Rate: {market_data['metrics']['funding_liquidation_rate']:.2f}%")
            print(f"     Total Liquidation Rate: {market_data['metrics']['total_liquidation_rate']:.2f}%")
            print(f"     Closure Rate: {market_data['metrics']['closure_rate']:.2f}%")
            print(f"     Settlement Rate: {market_data['metrics']['settlement_rate']:.2f}%")

            # Lifecycle warning
            if market_data['metrics']['settlement_rate'] < 95:
                print(f"\n  ⚠️  WARNING: Settlement rate < 95% - {open_positions:,} positions may be stuck")

    def verify_all_markets(self):
        """Verify event statistics for all markets"""
        print(f"\n{'='*80}")
        print(f"ENHANCED EVENT STATISTICS VERIFICATION")
        print(f"{'='*80}")

        markets = self.get_markets_to_verify()

        if self.sample_size:
            print(f"\nSample Size: {self.sample_size} markets")
        else:
            print(f"\nFull Verification: {len(markets)} markets")

        print(f"Block Range: {self.results['block_range']['from']:,} - {self.results['block_range']['to']:,}")
        print(f"\n⭐ NEW: Tracking CollateralSeized events (funding liquidations)")

        for market in markets:
            self.verify_market(market)
            self.results["summary"]["total_markets_verified"] += 1

    def generate_report(self):
        """Generate summary report"""
        print(f"\n{'='*80}")
        print(f"ENHANCED EVENT VERIFICATION SUMMARY")
        print(f"{'='*80}")

        summary = self.results["summary"]

        print(f"\n📊 Verification Scope:")
        print(f"   Block Range: {self.results['block_range']['from']:,} - {self.results['block_range']['to']:,}")
        print(f"   Markets Verified: {summary['total_markets_verified']}")
        if self.sample_size:
            print(f"   Mode: Sample ({self.sample_size} markets)")
        else:
            print(f"   Mode: Full verification")

        print(f"\n📈 Aggregate Statistics:")
        print(f"   Positions Created: {summary['total_positions_created']:,}")
        print(f"   Positions Closed: {summary['total_positions_closed']:,}")
        print(f"   Price Liquidations: {summary['total_price_liquidations']:,}")
        print(f"   Funding Liquidations: {summary['total_funding_liquidations']:,} ⭐ NEW")
        print(f"   Total Liquidations: {summary['total_liquidations']:,}")

        total_settled = summary['total_positions_closed'] + summary['total_liquidations']
        open_positions = summary['total_positions_created'] - total_settled

        print(f"   Total Settled: {total_settled:,}")
        print(f"   Open Positions: {open_positions:,}")

        if summary['total_positions_created'] > 0:
            price_liq_rate = (summary['total_price_liquidations'] / summary['total_positions_created']) * 100
            funding_liq_rate = (summary['total_funding_liquidations'] / summary['total_positions_created']) * 100
            total_liq_rate = (summary['total_liquidations'] / summary['total_positions_created']) * 100
            settlement_rate = (total_settled / summary['total_positions_created']) * 100

            print(f"\n📊 Key Metrics:")
            print(f"   Price Liquidation Rate: {price_liq_rate:.2f}%")
            print(f"   Funding Liquidation Rate: {funding_liq_rate:.2f}%")
            print(f"   Total Liquidation Rate: {total_liq_rate:.2f}%")
            print(f"   Settlement Rate: {settlement_rate:.2f}%")

            # Comparison with old method
            old_liq_rate = price_liq_rate  # Old script only tracked price liquidations
            improvement = total_liq_rate - old_liq_rate

            if improvement > 0.01:
                print(f"\n⭐ IMPROVED ACCURACY:")
                print(f"   Old liquidation rate (price only): {old_liq_rate:.2f}%")
                print(f"   New liquidation rate (price + funding): {total_liq_rate:.2f}%")
                print(f"   Difference: +{improvement:.2f}% (was underreported)")

        print(f"\n🎯 Overall Assessment:")
        print(f"   ✅ Complete liquidation tracking (price + funding)")
        print(f"   ✅ Event statistics verified via public API")
        print(f"   ✅ Position lifecycle verification included")

    def save_results(self, filename: str = "events_enhanced_verified.json"):
        """Save results to JSON file"""
        output_path = Path("results") / filename
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n✅ Results saved to: {output_path}")

    def run(self):
        """Run full verification"""
        print("="*80)
        print("TRADESTA ENHANCED EVENT STATISTICS VERIFICATION")
        print("="*80)
        print("\nEnhancements:")
        for improvement in self.results["improvements"]:
            print(f"  ⭐ {improvement}")

        try:
            self.verify_all_markets()
            self.generate_report()
            self.save_results()

            print("\n" + "="*80)
            print("VERIFICATION COMPLETE")
            print("="*80)

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Enhanced TradeSta event statistics verification with complete liquidation tracking'
    )
    parser.add_argument(
        '--sample',
        type=int,
        help='Verify only first N markets (for testing)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Verify all markets (default if no --sample)'
    )

    args = parser.parse_args()

    sample_size = args.sample if args.sample else None

    verifier = EnhancedEventVerifier(sample_size=sample_size)
    verifier.run()


if __name__ == "__main__":
    main()
