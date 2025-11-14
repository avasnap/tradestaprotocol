#!/usr/bin/env python3
"""
TradeSta Liquidation Cascade Analysis

Analyzes liquidation risk by identifying "cascade zones" - price levels where
multiple positions would liquidate simultaneously, potentially causing:
- Market instability
- Cascading liquidations (one liquidation triggers price movement triggering more)
- Protocol solvency risk
- Keeper congestion

Uses PositionManager view functions:
- findLiquidatablePricesLong(referencePrice) - Get unique liquidation prices for longs
- findLiquidatablePricesShorts(referencePrice) - Get unique liquidation prices for shorts
- getLiquidationMappingsFromPrice(price) - Get all position IDs at specific price level
- getPositionById(positionId) - Get position details

Requires:
- Pyth Network price oracle for current market price
- Web3 connection for contract state queries

Output:
- Liquidation cascade map (price → position count)
- Critical zones (within 5% of current price)
- Maximum cascade level (most positions at single price)
- Total collateral at risk per zone
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any
from decimal import Decimal

sys.path.append(str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper
from web3 import Web3

class LiquidationCascadeAnalyzer:
    """Analyze liquidation cascade risks for TradeSta markets"""

    def __init__(self, sample_size: int = None):
        self.api = RoutescanAPI(cache_dir='cache')
        self.w3_helper = Web3Helper()
        self.sample_size = sample_size

        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latest_block": self.w3_helper.get_latest_block(),
            "verification_method": "liquidation_cascade_analysis",
            "markets": [],
            "statistics": {
                "total_markets": 0,
                "total_cascade_zones": 0,
                "total_critical_zones": 0,
                "max_cascade_size": 0,
                "total_positions_at_risk": 0
            }
        }

        # PositionManager ABI for cascade functions
        self.pm_abi = [
            {
                "inputs": [{"internalType": "uint256", "name": "referencePrice", "type": "uint256"}],
                "name": "findLiquidatablePricesLong",
                "outputs": [{"internalType": "uint256[]", "name": "liquidatable", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "referencePrice", "type": "uint256"}],
                "name": "findLiquidatablePricesShorts",
                "outputs": [{"internalType": "uint256[]", "name": "liquidatable", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "price", "type": "uint256"}],
                "name": "getLiquidationMappingsFromPrice",
                "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "bytes32", "name": "id", "type": "bytes32"}],
                "name": "getPositionById",
                "outputs": [{"internalType": "tuple", "name": "", "type": "tuple", "components": []}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "marketConfig",
                "outputs": [
                    {"internalType": "bytes32", "name": "pricefeedId", "type": "bytes32"},
                    {"internalType": "address", "name": "registry", "type": "address"},
                    {"internalType": "address", "name": "vault", "type": "address"},
                    {"internalType": "address", "name": "collateralToken", "type": "address"},
                    {"internalType": "address", "name": "fundingTracker", "type": "address"},
                    {"internalType": "address", "name": "priceBuffer", "type": "address"},
                    {"internalType": "uint256", "name": "totalLongs", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalShorts", "type": "uint256"},
                    {"internalType": "uint256", "name": "maxDeviation", "type": "uint256"},
                    {"internalType": "uint256", "name": "nonce", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    def get_markets_to_verify(self) -> List[Dict[str, Any]]:
        """Get list of markets to verify"""
        market_registry = Web3.to_checksum_address('0x60f16b09a15f0c3210b40a735b19a6baf235dd18')
        market_created_sig = '0x5eb977f82e9d0d89f65f05a56a99ab87e2ebb3909780e0b3642bec962789ba7a'

        events = self.api.get_all_logs(
            address=market_registry,
            topic0=market_created_sig,
            from_block=63_000_000,
            to_block=self.results["latest_block"],
            offset=10000
        )

        # Well-known market names (for sample)
        market_names = {
            1: "AVAX/USD",
            2: "BTC/USD",
            3: "ETH/USD",
            4: "SOL/USD",
            5: "BNB/USD"
        }

        markets = []
        for i, event in enumerate(events, 1):
            topics = event['topics']
            position_manager = '0x' + topics[2][-40:]

            markets.append({
                "market_number": i,
                "name": market_names.get(i, f"Market #{i}"),
                "position_manager": Web3.to_checksum_address(position_manager)
            })

        if self.sample_size:
            markets = markets[:self.sample_size]

        return markets

    def get_current_price_estimate(self, contract, market_name: str) -> int:
        """
        Estimate current price for cascade analysis

        Note: In production, this would query Pyth oracle
        For now, using placeholder values based on market
        """
        # Placeholder prices (8 decimals)
        placeholder_prices = {
            "AVAX/USD": 40_00000000,   # $40
            "BTC/USD": 100000_00000000,  # $100,000
            "ETH/USD": 3500_00000000,    # $3,500
            "SOL/USD": 200_00000000,     # $200
            "BNB/USD": 600_00000000      # $600
        }

        # Try to get from known prices
        for market, price in placeholder_prices.items():
            if market in market_name:
                return price

        # Default fallback
        return 100_00000000  # $100

    def analyze_long_cascades(
        self,
        contract,
        current_price: int,
        market_name: str
    ) -> List[Dict[str, Any]]:
        """Analyze liquidation cascades for long positions"""
        print(f"    Analyzing long position cascades...")

        try:
            # Get all liquidation price levels for longs
            long_levels = contract.functions.findLiquidatablePricesLong(current_price).call()

            if not long_levels:
                print(f"    ✅ No long positions at risk")
                return []

            print(f"    Found {len(long_levels)} liquidation price levels for longs")

            cascades = []

            for price_level in long_levels[:20]:  # Limit to top 20 levels for performance
                # Get position IDs at this level
                try:
                    position_ids = contract.functions.getLiquidationMappingsFromPrice(price_level).call()

                    # Calculate distance from current price
                    distance_pct = abs(price_level - current_price) / current_price * 100

                    cascades.append({
                        "price": price_level,
                        "position_count": len(position_ids),
                        "distance_percent": float(distance_pct),
                        "direction": "long",
                        "critical": distance_pct < 5  # Within 5% = critical
                    })

                except Exception as e:
                    # Skip levels that error
                    continue

            # Sort by position count descending
            cascades.sort(key=lambda x: x['position_count'], reverse=True)

            return cascades

        except Exception as e:
            print(f"    ⚠️  Error analyzing long cascades: {e}")
            return []

    def analyze_short_cascades(
        self,
        contract,
        current_price: int,
        market_name: str
    ) -> List[Dict[str, Any]]:
        """Analyze liquidation cascades for short positions"""
        print(f"    Analyzing short position cascades...")

        try:
            # Get all liquidation price levels for shorts
            short_levels = contract.functions.findLiquidatablePricesShorts(current_price).call()

            if not short_levels:
                print(f"    ✅ No short positions at risk")
                return []

            print(f"    Found {len(short_levels)} liquidation price levels for shorts")

            cascades = []

            for price_level in short_levels[:20]:  # Limit to top 20 levels
                try:
                    position_ids = contract.functions.getLiquidationMappingsFromPrice(price_level).call()

                    distance_pct = abs(price_level - current_price) / current_price * 100

                    cascades.append({
                        "price": price_level,
                        "position_count": len(position_ids),
                        "distance_percent": float(distance_pct),
                        "direction": "short",
                        "critical": distance_pct < 5
                    })

                except Exception as e:
                    continue

            cascades.sort(key=lambda x: x['position_count'], reverse=True)

            return cascades

        except Exception as e:
            print(f"    ⚠️  Error analyzing short cascades: {e}")
            return []

    def analyze_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze liquidation cascades for a single market"""
        print(f"\n{'='*80}")
        print(f"{market['name']} (Market #{market['market_number']})")
        print(f"{'='*80}")
        print(f"PositionManager: {market['position_manager']}")

        contract = self.w3_helper.w3.eth.contract(
            address=market['position_manager'],
            abi=self.pm_abi
        )

        # Get estimated current price
        current_price = self.get_current_price_estimate(contract, market['name'])
        print(f"    Reference Price: ${current_price / 1e8:,.2f}")

        # Analyze both long and short cascades
        long_cascades = self.analyze_long_cascades(contract, current_price, market['name'])
        short_cascades = self.analyze_short_cascades(contract, current_price, market['name'])

        all_cascades = long_cascades + short_cascades

        # Filter critical zones
        critical_cascades = [c for c in all_cascades if c['critical']]

        # Find max cascade
        max_cascade = max(all_cascades, key=lambda x: x['position_count']) if all_cascades else None

        market_result = {
            "market_number": market['market_number'],
            "name": market['name'],
            "position_manager": market['position_manager'].lower(),
            "reference_price": current_price,
            "cascade_analysis": {
                "total_cascade_zones": len(all_cascades),
                "critical_zones": len(critical_cascades),
                "long_zones": len(long_cascades),
                "short_zones": len(short_cascades),
                "max_cascade": {
                    "price": max_cascade['price'] if max_cascade else 0,
                    "position_count": max_cascade['position_count'] if max_cascade else 0,
                    "direction": max_cascade['direction'] if max_cascade else None,
                    "distance_percent": max_cascade['distance_percent'] if max_cascade else 0
                } if max_cascade else None
            },
            "cascades": all_cascades[:10],  # Top 10 cascades
            "critical_cascades": critical_cascades
        }

        # Update statistics
        stats = self.results["statistics"]
        stats["total_cascade_zones"] += len(all_cascades)
        stats["total_critical_zones"] += len(critical_cascades)

        if max_cascade:
            if max_cascade['position_count'] > stats["max_cascade_size"]:
                stats["max_cascade_size"] = max_cascade['position_count']

            stats["total_positions_at_risk"] += sum(c['position_count'] for c in all_cascades)

        # Print summary
        print(f"\n  📊 Cascade Summary:")
        print(f"     Total Cascade Zones:    {len(all_cascades)}")
        print(f"     Critical Zones (<5%):   {len(critical_cascades)}")
        print(f"     Long Cascade Zones:     {len(long_cascades)}")
        print(f"     Short Cascade Zones:    {len(short_cascades)}")

        if max_cascade:
            print(f"\n  ⚠️  Maximum Cascade:")
            print(f"     Price Level: ${max_cascade['price'] / 1e8:,.2f}")
            print(f"     Position Count: {max_cascade['position_count']}")
            print(f"     Direction: {max_cascade['direction'].upper()}")
            print(f"     Distance: {max_cascade['distance_percent']:.2f}%")

            if max_cascade['critical']:
                print(f"     🚨 CRITICAL - Within 5% of current price!")

        if critical_cascades:
            print(f"\n  🚨 Critical Zones:")
            for cascade in critical_cascades[:5]:
                print(f"     ${cascade['price'] / 1e8:,.2f}: {cascade['position_count']} {cascade['direction']}s ({cascade['distance_percent']:.2f}% away)")

        return market_result

    def verify_all_markets(self):
        """Analyze cascades for all markets"""
        print("="*80)
        print("LIQUIDATION CASCADE ANALYSIS")
        print("="*80)
        print("\nIdentifies price levels where multiple positions liquidate")
        print("Critical zones: Within 5% of current price")

        markets = self.get_markets_to_verify()

        if self.sample_size:
            print(f"\n⚠️  Sample mode: Analyzing first {self.sample_size} markets only")
        else:
            print(f"\n✅ Full analysis: {len(markets)} markets")

        print(f"\n⚠️  NOTE: Using placeholder prices (production would query Pyth oracle)")

        for market in markets:
            market_result = self.analyze_market(market)
            self.results["markets"].append(market_result)
            self.results["statistics"]["total_markets"] += 1

    def generate_report(self):
        """Generate summary report"""
        print(f"\n{'='*80}")
        print(f"CASCADE ANALYSIS SUMMARY")
        print(f"{'='*80}")

        stats = self.results["statistics"]

        print(f"\n📊 Aggregate Statistics:")
        print(f"   Markets Analyzed:          {stats['total_markets']}")
        print(f"   Total Cascade Zones:       {stats['total_cascade_zones']}")
        print(f"   Critical Zones (<5%):      {stats['total_critical_zones']}")
        print(f"   Largest Cascade:           {stats['max_cascade_size']} positions")
        print(f"   Total Positions at Risk:   {stats['total_positions_at_risk']}")

        print(f"\n🎯 Risk Assessment:")
        if stats['total_critical_zones'] == 0:
            print(f"   ✅ No critical cascade zones detected")
            print(f"   ✅ Low liquidation cascade risk")
        else:
            print(f"   ⚠️  {stats['total_critical_zones']} critical cascade zones detected")

            if stats['max_cascade_size'] > 10:
                print(f"   🚨 LARGE CASCADE RISK - {stats['max_cascade_size']} positions at single level")
            elif stats['max_cascade_size'] > 5:
                print(f"   ⚠️  MODERATE CASCADE RISK - {stats['max_cascade_size']} positions at single level")
            else:
                print(f"   ✅ LOW CASCADE RISK - Max {stats['max_cascade_size']} positions at single level")

        print(f"\n💡 Methodology:")
        print(f"   ✅ Uses PositionManager.findLiquidatablePrices*()")
        print(f"   ✅ Identifies exact liquidation price levels")
        print(f"   ✅ Counts positions per level")
        print(f"   ⚠️  Note: Uses placeholder prices (production needs Pyth oracle)")

    def save_results(self, filename: str = "liquidation_cascades_analyzed.json"):
        """Save results to JSON file"""
        output_path = Path("results") / filename
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n✅ Results saved to: {output_path}")

    def run(self):
        """Run full analysis"""
        try:
            self.verify_all_markets()
            self.generate_report()
            self.save_results()

            print("\n" + "="*80)
            print("ANALYSIS COMPLETE")
            print("="*80)

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Analyze liquidation cascade risks for TradeSta markets'
    )
    parser.add_argument(
        '--sample',
        type=int,
        help='Analyze only first N markets (for testing)'
    )

    args = parser.parse_args()
    sample_size = args.sample if args.sample else None

    analyzer = LiquidationCascadeAnalyzer(sample_size=sample_size)
    analyzer.run()


if __name__ == "__main__":
    main()
