#!/usr/bin/env python3
"""
TradeSta Position Lifecycle Verification

Verifies that all positions are properly accounted for:
- Every created position has been either: closed, liquidated (price), liquidated (funding), or is still open
- No "zombie positions" (positions that exist in events but not in contract state)
- No "ghost positions" (positions in contract state but missing creation events)

Formula:
    created_positions = closed + price_liquidated + funding_liquidated + currently_open

Uses:
- PositionCreated events for position IDs
- PositionClosed events for closed position IDs
- PositionLiquidated events for price-liquidated position IDs
- CollateralSeized events for funding-liquidated position IDs
- PositionManager.getAllActivePositionIds() for currently open positions

This verification is CRITICAL for ensuring:
- Complete event coverage
- Accurate accounting
- No stuck/lost positions
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Set, Any

sys.path.append(str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper, EVENT_SIGNATURES
from web3 import Web3

class PositionLifecycleVerifier:
    """Verify complete position lifecycle for all markets"""

    def __init__(self, sample_size: int = None):
        self.api = RoutescanAPI(cache_dir='cache')
        self.w3_helper = Web3Helper()
        self.sample_size = sample_size

        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latest_block": self.w3_helper.get_latest_block(),
            "verification_method": "position_lifecycle_accounting",
            "markets": [],
            "statistics": {
                "total_markets": 0,
                "total_created": 0,
                "total_closed": 0,
                "total_price_liquidated": 0,
                "total_funding_liquidated": 0,
                "total_expected_open": 0,
                "total_actual_open": 0,
                "total_zombie_positions": 0,
                "total_ghost_positions": 0,
                "lifecycle_complete_markets": 0
            }
        }

        # Event signatures
        self.collateral_seized_sig = Web3.keccak(text='CollateralSeized(bytes32,address,uint256,int256,uint256)').hex()

        # PositionManager ABI for getAllActivePositionIds()
        self.pm_abi = [
            {
                "inputs": [],
                "name": "getAllActivePositionIds",
                "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    def get_markets_to_verify(self) -> List[Dict[str, str]]:
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

        markets = []
        for i, event in enumerate(events, 1):
            topics = event['topics']
            position_manager = '0x' + topics[2][-40:]

            markets.append({
                "market_number": i,
                "position_manager": Web3.to_checksum_address(position_manager)
            })

        if self.sample_size:
            markets = markets[:self.sample_size]

        return markets

    def get_position_ids_from_events(
        self,
        position_manager: str,
        event_sig: str,
        event_name: str
    ) -> Set[str]:
        """Get set of position IDs from event logs"""
        print(f"    Querying {event_name} events...")

        events = self.api.get_all_logs(
            address=position_manager,
            topic0=event_sig,
            from_block=63_000_000,
            to_block=self.results["latest_block"],
            offset=10000
        )

        # positionId is first indexed parameter (topic1)
        position_ids = {evt['topics'][1] for evt in events}

        print(f"    ✅ Found {len(events):,} events, {len(position_ids):,} unique position IDs")

        return position_ids

    def get_active_positions_from_contract(self, position_manager: str) -> Set[str]:
        """Query contract for currently active position IDs"""
        print(f"    Querying contract for active positions...")

        contract = self.w3_helper.w3.eth.contract(
            address=position_manager,
            abi=self.pm_abi
        )

        try:
            active_ids = contract.functions.getAllActivePositionIds().call()

            # Convert bytes32 to hex string with 0x prefix
            active_ids_hex = {'0x' + id.hex() for id in active_ids}

            print(f"    ✅ Found {len(active_ids_hex):,} active positions in contract")

            return active_ids_hex

        except Exception as e:
            print(f"    ⚠️  Error querying contract: {e}")
            return set()

    def verify_market_lifecycle(self, market: Dict[str, str]) -> Dict[str, Any]:
        """Verify position lifecycle for a single market"""
        print(f"\n{'='*80}")
        print(f"MARKET #{market['market_number']}")
        print(f"{'='*80}")
        print(f"PositionManager: {market['position_manager']}")

        pm = market['position_manager']

        # Get position IDs from all lifecycle events
        created_ids = self.get_position_ids_from_events(
            pm,
            EVENT_SIGNATURES["PositionCreated"],
            "PositionCreated"
        )

        closed_ids = self.get_position_ids_from_events(
            pm,
            EVENT_SIGNATURES["PositionClosed"],
            "PositionClosed"
        )

        price_liquidated_ids = self.get_position_ids_from_events(
            pm,
            EVENT_SIGNATURES["PositionLiquidated"],
            "PositionLiquidated"
        )

        funding_liquidated_ids = self.get_position_ids_from_events(
            pm,
            self.collateral_seized_sig,
            "CollateralSeized"
        )

        # Get currently active positions from contract
        active_ids = self.get_active_positions_from_contract(pm)

        # Calculate settled positions
        settled_ids = closed_ids | price_liquidated_ids | funding_liquidated_ids

        # Expected open = created - settled
        expected_open_ids = created_ids - settled_ids

        # Verify lifecycle accounting
        zombie_positions = expected_open_ids - active_ids  # In events but not in contract
        ghost_positions = active_ids - created_ids  # In contract but not in events

        # Check for duplicates (position in multiple settlement categories)
        overlap_closed_price = closed_ids & price_liquidated_ids
        overlap_closed_funding = closed_ids & funding_liquidated_ids
        overlap_price_funding = price_liquidated_ids & funding_liquidated_ids

        market_result = {
            "market_number": market['market_number'],
            "position_manager": pm.lower(),
            "counts": {
                "created": len(created_ids),
                "closed": len(closed_ids),
                "price_liquidated": len(price_liquidated_ids),
                "funding_liquidated": len(funding_liquidated_ids),
                "total_settled": len(settled_ids),
                "expected_open": len(expected_open_ids),
                "actual_open": len(active_ids)
            },
            "verification": {
                "lifecycle_complete": len(zombie_positions) == 0 and len(ghost_positions) == 0,
                "zombie_positions": len(zombie_positions),
                "ghost_positions": len(ghost_positions),
                "duplicate_closed_price": len(overlap_closed_price),
                "duplicate_closed_funding": len(overlap_closed_funding),
                "duplicate_price_funding": len(overlap_price_funding)
            }
        }

        # Update statistics
        stats = self.results["statistics"]
        stats["total_created"] += len(created_ids)
        stats["total_closed"] += len(closed_ids)
        stats["total_price_liquidated"] += len(price_liquidated_ids)
        stats["total_funding_liquidated"] += len(funding_liquidated_ids)
        stats["total_expected_open"] += len(expected_open_ids)
        stats["total_actual_open"] += len(active_ids)
        stats["total_zombie_positions"] += len(zombie_positions)
        stats["total_ghost_positions"] += len(ghost_positions)

        if market_result["verification"]["lifecycle_complete"]:
            stats["lifecycle_complete_markets"] += 1

        # Print summary
        print(f"\n  📊 Lifecycle Summary:")
        print(f"     Created:            {len(created_ids):,}")
        print(f"     Closed:             {len(closed_ids):,}")
        print(f"     Price Liquidated:   {len(price_liquidated_ids):,}")
        print(f"     Funding Liquidated: {len(funding_liquidated_ids):,}")
        print(f"     Total Settled:      {len(settled_ids):,}")
        print(f"     Expected Open:      {len(expected_open_ids):,}")
        print(f"     Actual Open:        {len(active_ids):,}")

        print(f"\n  ✅ Verification:")
        if market_result["verification"]["lifecycle_complete"]:
            print(f"     ✅ LIFECYCLE COMPLETE - All positions accounted for")
        else:
            if zombie_positions:
                print(f"     ⚠️  {len(zombie_positions)} zombie positions (in events, not in contract)")
            if ghost_positions:
                print(f"     ⚠️  {len(ghost_positions)} ghost positions (in contract, not in events)")

        # Check for duplicates
        if any([overlap_closed_price, overlap_closed_funding, overlap_price_funding]):
            print(f"\n  ⚠️  DUPLICATES DETECTED:")
            if overlap_closed_price:
                print(f"     {len(overlap_closed_price)} positions both closed AND price-liquidated")
            if overlap_closed_funding:
                print(f"     {len(overlap_closed_funding)} positions both closed AND funding-liquidated")
            if overlap_price_funding:
                print(f"     {len(overlap_price_funding)} positions both price AND funding-liquidated")

        return market_result

    def verify_all_markets(self):
        """Verify lifecycle for all markets"""
        print("="*80)
        print("POSITION LIFECYCLE VERIFICATION")
        print("="*80)
        print("\nVerifies: created = closed + liquidated + open")
        print("Detects: zombie positions, ghost positions, duplicate settlements")

        markets = self.get_markets_to_verify()

        if self.sample_size:
            print(f"\n⚠️  Sample mode: Verifying first {self.sample_size} markets only")
        else:
            print(f"\n✅ Full verification: {len(markets)} markets")

        for market in markets:
            market_result = self.verify_market_lifecycle(market)
            self.results["markets"].append(market_result)
            self.results["statistics"]["total_markets"] += 1

    def generate_report(self):
        """Generate summary report"""
        print(f"\n{'='*80}")
        print(f"LIFECYCLE VERIFICATION SUMMARY")
        print(f"{'='*80}")

        stats = self.results["statistics"]

        print(f"\n📊 Aggregate Counts:")
        print(f"   Markets Verified:      {stats['total_markets']}")
        print(f"   Positions Created:     {stats['total_created']:,}")
        print(f"   Positions Closed:      {stats['total_closed']:,}")
        print(f"   Price Liquidations:    {stats['total_price_liquidated']:,}")
        print(f"   Funding Liquidations:  {stats['total_funding_liquidated']:,}")
        print(f"   Expected Open:         {stats['total_expected_open']:,}")
        print(f"   Actual Open:           {stats['total_actual_open']:,}")

        print(f"\n🔍 Verification Results:")
        print(f"   Markets with Complete Lifecycle: {stats['lifecycle_complete_markets']}/{stats['total_markets']}")

        if stats['total_zombie_positions'] > 0:
            print(f"   ⚠️  Zombie Positions:  {stats['total_zombie_positions']:,}")
            print(f"       (in events but not in contract - may be closed in newer blocks)")

        if stats['total_ghost_positions'] > 0:
            print(f"   ⚠️  Ghost Positions:   {stats['total_ghost_positions']:,}")
            print(f"       (in contract but missing creation events - DATA ERROR)")

        # Overall assessment
        print(f"\n🎯 Overall Assessment:")
        if stats['lifecycle_complete_markets'] == stats['total_markets']:
            print(f"   ✅ PERFECT - All markets have complete position lifecycle")
            print(f"   ✅ created = closed + liquidated + open")
            print(f"   ✅ No zombie or ghost positions")
        else:
            incomplete = stats['total_markets'] - stats['lifecycle_complete_markets']
            print(f"   ⚠️  {incomplete} market(s) have lifecycle discrepancies")

            if stats['total_zombie_positions'] > 0:
                print(f"   ℹ️  Zombie positions may be due to block timing (events vs contract state)")

            if stats['total_ghost_positions'] > 0:
                print(f"   ❌ Ghost positions indicate MISSING EVENTS - serious issue")

    def save_results(self, filename: str = "position_lifecycle_verified.json"):
        """Save results to JSON file"""
        output_path = Path("results") / filename
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n✅ Results saved to: {output_path}")

    def run(self):
        """Run full verification"""
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
        description='Verify position lifecycle for TradeSta markets'
    )
    parser.add_argument(
        '--sample',
        type=int,
        help='Verify only first N markets (for testing)'
    )

    args = parser.parse_args()
    sample_size = args.sample if args.sample else None

    verifier = PositionLifecycleVerifier(sample_size=sample_size)
    verifier.run()


if __name__ == "__main__":
    main()
