#!/usr/bin/env python3
"""
TradeSta Associated Contracts Verification Script (v2 - Improved)

Verifies associated contracts using the CORRECT method:
1. Query MarketCreated events for pricefeed IDs
2. Call MarketRegistry getter functions for each contract type

This is the authoritative method - queries contract state directly.
No transaction parsing, no source code queries needed.

Associated contracts verified:
- Orders contracts (limit order management)
- Vault contracts (USDC collateral pools) - CRITICAL for security
- FundingTracker contracts (perpetual funding rates)
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

sys.path.append(str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper
from web3 import Web3

class AssociatedContractsVerifierV2:
    """Verify associated contracts using MarketRegistry getter functions"""

    def __init__(self, sample_size: int = None):
        self.api = RoutescanAPI(cache_dir='cache')
        self.w3_helper = Web3Helper()
        self.sample_size = sample_size

        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "latest_block": self.w3_helper.get_latest_block(),
            "verification_method": "marketregistry_getter_functions",
            "markets": [],
            "statistics": {
                "total_markets": 0,
                "complete_quartets": 0,
                "vaults_verified": 0,
                "orders_verified": 0,
                "funding_trackers_verified": 0,
                "collateral_token_verified": False
            }
        }

        self.market_registry = Web3.to_checksum_address(
            '0x60f16b09a15f0c3210b40a735b19a6baf235dd18'
        )
        self.market_created_sig = '0x5eb977f82e9d0d89f65f05a56a99ab87e2ebb3909780e0b3642bec962789ba7a'

    def verify_collateral_token(self):
        """Verify collateral token is USDC"""
        print("\n" + "="*80)
        print("VERIFYING COLLATERAL TOKEN")
        print("="*80)

        # Call collateralTokenAddress()
        function_sig = Web3.keccak(text='collateralTokenAddress()')[:4]

        result = self.w3_helper.w3.eth.call({
            'to': self.market_registry,
            'data': function_sig.hex()
        })

        collateral_token = '0x' + result[-20:].hex()
        expected_usdc = '0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e'

        is_match = collateral_token.lower() == expected_usdc

        print(f"\nCollateral Token: {collateral_token}")
        print(f"Expected (USDC):  {expected_usdc}")
        print(f"Match: {'✅' if is_match else '❌'}")

        self.results["collateral_token"] = {
            "address": collateral_token.lower(),
            "expected": expected_usdc,
            "verified": is_match,
            "symbol": "USDC" if is_match else "Unknown"
        }
        self.results["statistics"]["collateral_token_verified"] = is_match

        return is_match

    def get_market_created_events(self) -> List[Dict[str, Any]]:
        """Query all MarketCreated events"""
        print("\n" + "="*80)
        print("QUERYING MARKET DEPLOYMENTS")
        print("="*80)

        print(f"\nQuerying MarketCreated events from MarketRegistry...")

        events = self.api.get_all_logs(
            address=self.market_registry,
            topic0=self.market_created_sig,
            from_block=63_000_000,
            to_block=self.results["latest_block"],
            offset=10000
        )

        print(f"✅ Found {len(events)} markets")

        return events

    def get_quartet_for_market(self, pricefeed_id: str) -> Dict[str, str]:
        """
        Query MarketRegistry getter functions to get complete quartet

        Args:
            pricefeed_id: Pyth price feed ID (bytes32)

        Returns:
            Dictionary with all 4 contract addresses
        """
        quartet = {}

        # Define getter functions
        functions = {
            'position_manager': 'getPositionManagerAddress(bytes32)',
            'orders': 'getOrderManagerAddress(bytes32)',
            'vault': 'getVaultAddress(bytes32)',
            'funding_tracker': 'getFundingManagerAddress(bytes32)'
        }

        for contract_type, function_name in functions.items():
            function_sig = Web3.keccak(text=function_name)[:4]
            call_data = function_sig + bytes.fromhex(pricefeed_id[2:])

            result = self.w3_helper.w3.eth.call({
                'to': self.market_registry,
                'data': call_data.hex()
            })

            address = '0x' + result[-20:].hex()
            quartet[contract_type] = address.lower()

        return quartet

    def verify_market(self, event: Dict[str, Any], market_number: int) -> Dict[str, Any]:
        """Verify complete quartet for a single market"""
        topics = event['topics']
        pricefeed_id = topics[1]
        block = int(event['blockNumber'], 16)
        tx_hash = event['transactionHash']

        # Get position manager from event
        position_manager_from_event = '0x' + topics[2][-40:]

        print(f"\n{'='*80}")
        print(f"MARKET #{market_number}")
        print(f"{'='*80}")
        print(f"Block: {block:,}")
        print(f"TX: {tx_hash}")
        print(f"PriceFeed ID: {pricefeed_id}")

        # Query complete quartet from MarketRegistry
        print(f"\nQuerying MarketRegistry getter functions...")
        quartet = self.get_quartet_for_market(pricefeed_id)

        # Verify position manager matches event
        pm_match = quartet['position_manager'] == position_manager_from_event.lower()

        print(f"\n  Contract Addresses (from MarketRegistry state):")
        print(f"  ├─ PositionManager: {quartet['position_manager']}")
        print(f"  │  └─ Matches event: {'✅' if pm_match else '❌'}")
        print(f"  ├─ Orders:          {quartet['orders']}")
        print(f"  ├─ Vault:           {quartet['vault']} ⚠️  HOLDS USER FUNDS")
        print(f"  └─ FundingTracker:  {quartet['funding_tracker']}")

        # Check for complete quartet (no zero addresses)
        has_all = all(
            addr != '0x0000000000000000000000000000000000000000'
            for addr in quartet.values()
        )

        if has_all:
            print(f"\n  ✅ COMPLETE QUARTET VERIFIED")
            self.results["statistics"]["complete_quartets"] += 1
            self.results["statistics"]["vaults_verified"] += 1
            self.results["statistics"]["orders_verified"] += 1
            self.results["statistics"]["funding_trackers_verified"] += 1
        else:
            print(f"\n  ⚠️  Incomplete quartet (contains zero addresses)")

        market_data = {
            "market_number": market_number,
            "block": block,
            "tx_hash": tx_hash,
            "pricefeed_id": pricefeed_id,
            "position_manager": quartet['position_manager'],
            "orders": quartet['orders'],
            "vault": quartet['vault'],
            "funding_tracker": quartet['funding_tracker'],
            "complete_quartet": has_all,
            "position_manager_matches_event": pm_match
        }

        return market_data

    def verify_all_markets(self):
        """Verify all markets"""
        print("="*80)
        print("TRADESTA ASSOCIATED CONTRACTS VERIFICATION V2")
        print("="*80)
        print("\nMethod: MarketRegistry getter functions (authoritative)")
        print("Source: Contract state queries via RPC")

        # First verify collateral token
        self.verify_collateral_token()

        # Get all market deployments
        events = self.get_market_created_events()

        if self.sample_size:
            events = events[:self.sample_size]
            print(f"\n⚠️  Sample mode: Verifying first {self.sample_size} markets only")

        # Verify each market
        print("\n" + "="*80)
        print("VERIFYING MARKET QUARTETS")
        print("="*80)

        for i, event in enumerate(events, 1):
            market_data = self.verify_market(event, i)
            self.results["markets"].append(market_data)
            self.results["statistics"]["total_markets"] += 1

    def generate_report(self):
        """Generate summary report"""
        print("\n" + "="*80)
        print("VERIFICATION SUMMARY")
        print("="*80)

        stats = self.results["statistics"]

        print(f"\n📊 Markets Verified: {stats['total_markets']}")
        print(f"   Complete Quartets: {stats['complete_quartets']}/{stats['total_markets']}")

        print(f"\n🏗️  Contracts Verified:")
        print(f"   Vaults: {stats['vaults_verified']}")
        print(f"   Orders: {stats['orders_verified']}")
        print(f"   FundingTrackers: {stats['funding_trackers_verified']}")

        print(f"\n🔐 Security Verification:")
        if stats['collateral_token_verified']:
            print(f"   ✅ Collateral token confirmed (USDC)")
        else:
            print(f"   ❌ Collateral token mismatch")

        if stats['vaults_verified'] > 0:
            print(f"   ✅ {stats['vaults_verified']} Vault addresses verified")
            print(f"   ✅ Users can verify where their USDC is held")
        else:
            print(f"   ⚠️  No Vaults verified")

        print(f"\n✨ Methodology:")
        print(f"   ✅ MarketCreated events for market discovery")
        print(f"   ✅ MarketRegistry getter functions for quartet addresses")
        print(f"   ✅ Direct contract state queries (authoritative)")
        print(f"   ✅ No transaction parsing required")
        print(f"   ✅ No source code queries required")

        print(f"\n🎯 Overall Assessment:")
        if stats['complete_quartets'] == stats['total_markets']:
            print(f"   ✅ ALL MARKETS HAVE COMPLETE QUARTETS")
            print(f"   ✅ All Vault addresses verified")
            print(f"   ✅ Full protocol architecture confirmed")
        else:
            incomplete = stats['total_markets'] - stats['complete_quartets']
            print(f"   ⚠️  {incomplete} market(s) have incomplete quartets")

    def save_results(self, filename: str = "associated_contracts_v2_verified.json"):
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
        description='Verify TradeSta associated contracts using MarketRegistry getters'
    )
    parser.add_argument(
        '--sample',
        type=int,
        help='Verify only first N markets (for testing)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Verify all 24 markets (default)'
    )

    args = parser.parse_args()

    sample_size = args.sample if args.sample else None

    verifier = AssociatedContractsVerifierV2(sample_size=sample_size)
    verifier.run()


if __name__ == "__main__":
    main()
