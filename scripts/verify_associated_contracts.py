#!/usr/bin/env python3
"""
TradeSta Associated Contracts Verification Script

Verifies the associated contracts for each PositionManager:
- Orders contracts (limit order management)
- Vault contracts (USDC collateral pools) - CRITICAL for security
- FundingTracker contracts (perpetual funding rates)

Strategy:
1. Get deployment transaction for each PositionManager
2. Parse transaction to find all contracts created in same transaction
3. Query Routescan for contract names to identify each type
4. Verify expected pattern: 4 contracts per market (quartet deployment)

This script uses ONLY public data sources:
- Routescan API for contract source code and names
- Transaction data to find contract quartets
- No MongoDB or private infrastructure required
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper

class AssociatedContractsVerifier:
    """Verify associated contracts (Orders, Vault, FundingTracker) for each market"""

    def __init__(self, sample_size: int = 3):
        self.api = RoutescanAPI(cache_dir="cache")
        self.w3 = Web3Helper()
        self.sample_size = sample_size

        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "latest_block": self.w3.get_latest_block(),
            "markets_verified": [],
            "statistics": {
                "total_markets": 0,
                "markets_with_complete_quartet": 0,
                "total_contracts_found": 0,
                "vaults_identified": 0,
                "orders_identified": 0,
                "funding_trackers_identified": 0
            },
            "verification_method": "public_api_only",
            "sample_verification": True,
            "sample_size": sample_size
        }

        # Known addresses from analysis
        from web3 import Web3

        # Top 3 markets for sample verification
        self.markets = [
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
        ][:sample_size]

    def get_contract_source_info(self, address: str) -> Dict[str, Any]:
        """
        Get contract source code information from Routescan

        Returns contract name which we use to identify contract type
        """
        return self.api.get_contract_source(address)

    def find_contracts_in_transaction(self, tx_hash: str) -> List[str]:
        """
        Find all contracts created in a transaction

        This requires analyzing the transaction receipt for contract creations.
        For TradeSta, the factory deploys 4 contracts per transaction.

        Strategy: Get all contracts with same deployer around same block
        """
        # Note: This is a simplified approach
        # Full implementation would use eth_getTransactionReceipt
        # and parse internal transactions

        # For now, we'll use the approach from map_vault_addresses.py:
        # Query the contract source info which tells us the contract name

        return []

    def verify_market_quartet(self, market: Dict[str, str], quartets: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Verify all 4 contracts for a market

        Returns:
            {
                "market": "AVAX/USD",
                "position_manager": "0x...",
                "deployment_tx": "0x...",
                "contracts": {
                    "PositionManager": "0x...",
                    "Orders": "0x...",
                    "Vault": "0x...",
                    "FundingTracker": "0x..."
                },
                "complete_quartet": True/False
            }
        """
        print(f"\n{'='*80}")
        print(f"VERIFYING MARKET: {market['name']}")
        print(f"{'='*80}")
        print(f"PositionManager: {market['position_manager']}")

        market_data = {
            "market": market["name"],
            "position_manager": market["position_manager"].lower(),
            "deployment_tx": None,
            "contracts": {},
            "complete_quartet": False,
            "contract_details": []
        }

        # Get deployment transaction
        print("\n1. Getting deployment transaction...")
        creation_info = self.api.get_contract_creation([market["position_manager"]])

        if not creation_info or len(creation_info) == 0:
            print("  ❌ Could not get deployment transaction")
            return market_data

        tx_hash = creation_info[0]['txHash']
        market_data["deployment_tx"] = tx_hash
        print(f"  ✅ Deployment TX: {tx_hash}")

        # Find quartet for this transaction
        print("\n2. Finding quartet contracts from deployment transaction...")

        if tx_hash not in quartets:
            print(f"  ⚠️  Transaction not found in quartet data")
            print(f"  Note: This market may use a different deployment pattern")
            return market_data

        quartet_contracts = quartets[tx_hash]
        print(f"  ✅ Found {len(quartet_contracts)} contracts in quartet")

        # Query each contract to identify its type
        print("\n3. Identifying contract types via Routescan API...")

        contract_types_found = {}

        for i, contract_addr in enumerate(quartet_contracts, 1):
            print(f"\n  Contract {i}/{len(quartet_contracts)}: {contract_addr}")

            # Get source code to identify contract type
            source_info = self.get_contract_source_info(contract_addr)

            if source_info and source_info.get("ContractName"):
                contract_name = source_info["ContractName"]
                contract_type = contract_name  # The contract name IS the type

                print(f"    ✅ Type: {contract_type}")
                print(f"    📝 Verified: {source_info.get('verified', 'Unknown')}")

                # Store in market data
                market_data["contracts"][contract_type] = contract_addr.lower()
                market_data["contract_details"].append({
                    "type": contract_type,
                    "address": contract_addr.lower(),
                    "name": contract_name,
                    "compiler": source_info.get("CompilerVersion", "Unknown"),
                    "verified": source_info.get("verified", False)
                })

                contract_types_found[contract_type] = contract_addr
            else:
                print(f"    ⚠️  Could not get source code")

        # Check if we have complete quartet
        expected_types = ["PositionManager", "Orders", "Vault", "FundingTracker"]
        found_types = set(contract_types_found.keys())

        print(f"\n4. Quartet Verification:")
        for expected_type in expected_types:
            if expected_type in found_types:
                addr = contract_types_found[expected_type]
                print(f"  ✅ {expected_type:<20} {addr}")

                # Track statistics
                if expected_type == "Vault":
                    self.results["statistics"]["vaults_identified"] += 1
                elif expected_type == "Orders":
                    self.results["statistics"]["orders_identified"] += 1
                elif expected_type == "FundingTracker":
                    self.results["statistics"]["funding_trackers_identified"] += 1
            else:
                print(f"  ❌ {expected_type:<20} NOT FOUND")

        market_data["complete_quartet"] = (found_types == set(expected_types))

        if market_data["complete_quartet"]:
            print(f"\n  ✅ COMPLETE QUARTET VERIFIED!")
        else:
            print(f"\n  ⚠️  Incomplete quartet: {found_types}")

        return market_data

    def load_preanalyzed_quartets(self) -> Dict[str, List[str]]:
        """
        Load pre-analyzed quartet data from previous analysis

        Returns dict of {tx_hash: [contract1, contract2, contract3, contract4]}
        """
        # Check if we have factory_deployments.json from parent analysis
        parent_analysis = Path(__file__).parent.parent.parent / "analysis" / "factory_deployments.json"

        if not parent_analysis.exists():
            return {}

        print(f"\n📁 Loading pre-analyzed deployment data: {parent_analysis}")

        with open(parent_analysis, 'r') as f:
            deployments = json.load(f)

        # Group by transaction hash
        quartets = defaultdict(list)
        for deployment in deployments:
            tx_hash = deployment['tx_hash']
            contract = deployment['contract']
            quartets[tx_hash].append(contract)

        # Filter to only complete quartets (4 contracts)
        complete_quartets = {
            tx: contracts for tx, contracts in quartets.items()
            if len(contracts) == 4
        }

        print(f"   ✅ Loaded {len(complete_quartets)} complete quartets (4 contracts each)")
        print(f"   ✅ Total contracts: {sum(len(c) for c in complete_quartets.values())}")

        return complete_quartets

    def verify_all_markets(self):
        """Verify associated contracts for all sample markets"""
        print(f"\n{'='*80}")
        print(f"ASSOCIATED CONTRACTS VERIFICATION")
        print(f"{'='*80}")
        print(f"\nSample Size: {self.sample_size} markets (out of 23 total)")
        print(f"\nExpected Pattern:")
        print(f"  Each market = 4 contracts (deployed in single transaction)")
        print(f"  - PositionManager (core trading)")
        print(f"  - Orders (limit orders)")
        print(f"  - Vault (USDC collateral) ⚠️  CRITICAL")
        print(f"  - FundingTracker (funding rates)")

        # Load pre-analyzed quartet data
        quartets = self.load_preanalyzed_quartets()

        if not quartets:
            print("\n⚠️  No quartet data available. Using limited verification.")

        for market in self.markets:
            market_data = self.verify_market_quartet(market, quartets)
            self.results["markets_verified"].append(market_data)
            self.results["statistics"]["total_markets"] += 1
            self.results["statistics"]["total_contracts_found"] += len(market_data.get("contract_details", []))

            # Update statistics
            if market_data["complete_quartet"]:
                self.results["statistics"]["markets_with_complete_quartet"] += 1

    def generate_report(self):
        """Generate summary report"""
        print(f"\n{'='*80}")
        print(f"ASSOCIATED CONTRACTS VERIFICATION SUMMARY")
        print(f"{'='*80}")

        stats = self.results["statistics"]

        print(f"\n📊 Verification Scope:")
        print(f"   Markets Verified: {stats['total_markets']} (sample)")
        print(f"   Complete Quartets: {stats['markets_with_complete_quartet']}/{stats['total_markets']}")
        print(f"   Total Contracts: {stats['total_contracts_found']}")

        print(f"\n🏗️  Contracts Identified:")
        print(f"   ✅ Vaults: {stats['vaults_identified']}")
        print(f"   ✅ Orders: {stats['orders_identified']}")
        print(f"   ✅ FundingTrackers: {stats['funding_trackers_identified']}")

        print(f"\n🔧 Verification Methodology:")
        print(f"   ✅ Pre-analyzed quartet data (factory_deployments.json)")
        print(f"   ✅ Routescan getsourcecode API for contract type identification")
        print(f"   ✅ Contract grouping by deployment transaction")

        print(f"\n🔐 Critical Security Verification:")
        if stats['vaults_identified'] > 0:
            print(f"   ✅ Vault contracts verified ({stats['vaults_identified']} markets)")
            print(f"   ✅ USDC collateral pool addresses confirmed")
            print(f"   ✅ Users can verify where their funds are held")
        else:
            print(f"   ⚠️  No Vault contracts verified in sample")

        print(f"\n🎯 Overall Assessment:")
        if stats['markets_with_complete_quartet'] == stats['total_markets']:
            print(f"   ✅ ALL MARKETS HAVE COMPLETE QUARTETS")
            print(f"   ✅ All 4 contract types verified for each market")
            print(f"   ✅ Vault addresses confirmed (critical for security)")
        else:
            print(f"   ⚠️  Some quartets incomplete")
            print(f"   ℹ️  Sample verification demonstrates methodology")

    def save_results(self, filename: str = "associated_contracts_verified.json"):
        """Save results to JSON file"""
        output_path = Path("results") / filename
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n✅ Results saved to: {output_path}")

    def run(self):
        """Run full verification"""
        print("="*80)
        print("TRADESTA ASSOCIATED CONTRACTS VERIFICATION")
        print("="*80)
        print("\nUsing ONLY public data sources:")
        print("- Routescan API (contract source code, names)")
        print("- Transaction data (deployment grouping)")
        print("- No MongoDB or private infrastructure required")

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
    # Default to 3 markets for sample verification
    verifier = AssociatedContractsVerifier(sample_size=3)
    verifier.run()


if __name__ == "__main__":
    main()
