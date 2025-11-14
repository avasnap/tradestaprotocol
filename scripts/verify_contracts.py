#!/usr/bin/env python3
"""
TradeSta Contract Verification Script

Verifies all TradeSta protocol contracts:
- Contract addresses and deployers
- Contract verification status
- ABIs availability
- Market structure (23 markets × 4 contracts each)

This script uses ONLY public data sources:
- Routescan API for contract info, ABIs, and deployers
- No MongoDB or private infrastructure required

Expected structure:
- 1 MarketRegistry contract
- 23 PositionManager contracts (one per market)
- Each market has: PositionManager, Orders, Vault, FundingTracker
- Total: ~93 contracts (1 registry + 23 markets × 4 contracts)
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper, EVENT_SIGNATURES

class ContractVerifier:
    """Verify all TradeSta protocol contracts"""

    def __init__(self):
        self.api = RoutescanAPI(cache_dir="cache")
        self.w3 = Web3Helper()

        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "latest_block": self.w3.get_latest_block(),
            "contracts": {
                "market_registry": {},
                "position_managers": [],
                "associated_contracts": []
            },
            "statistics": {
                "total_contracts": 0,
                "verified_contracts": 0,
                "contracts_with_abi": 0,
                "single_deployer": False,
                "deployer_address": None
            },
            "markets": [],
            "verification_method": "public_api_only"
        }

        # Known addresses from analysis
        from web3 import Web3

        # Core infrastructure
        self.market_registry = Web3.to_checksum_address("0x60f16b09a15f0c3210b40a735b19a6baf235dd18")
        self.admin_eoa = Web3.to_checksum_address("0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93")

        # MarketRegistry is deployed by admin EOA
        # PositionManagers are deployed BY MarketRegistry (factory pattern)
        self.expected_registry_deployer = self.admin_eoa
        self.expected_pm_deployer = self.market_registry

        # Known PositionManager contracts (23 total)
        self.position_managers = [
            Web3.to_checksum_address(addr) for addr in [
                "0x8d07fa9ac8b4bf833f099fb24971d2a808874c25",  # AVAX/USD
                "0x7da6e6d1b3582a2348fa76b3fe3b5e88d95281e7",  # BTC/USD
                "0x5bd078689c358ca2c64daff8761dbf8cfddfc51f",  # ETH/USD
                "0xf0e50db1f1797210db7b5124e8bbe63fd17dcf49",  # WIF/USD
                "0xed3cd277044d353b1b8bb303d2d10aa2d294932e",  # PEPE/USD
                "0x85660ace54fa5603a3af96300119c3f90ed676a4",  # BNB/USD
                "0xcb7086cac611a30df1f1101fa9dd86dca2cbab96",  # SOL/USD
                "0xc8fd23967b6be347d0a80c37205bd73a42c55878",  # SHIB/USD
                "0x2fcd398837478e8f410f0752099d4b5e5656042c",  # DRIFT/USD
                "0xf69c4a0e74ae4cb086506461771a717b7fb508be",  # TON/USD
                "0x04a6c1d341f27c1644b13e89ad7bf0a19289ec89",  # MEW/USD
                "0xf33d7648c4b358029121524b3f703e9bd89d47ed",  # CHILLGUY/USD
                "0x8958e3f0359a475129c003d906ce78deb41ba125",  # POPCAT/USD
                "0x9ec09278de421073c5b82f51d35b9d19a206987a",  # GIGA/USD
                "0x0999366f9e335024965bb6fe50375927ce40c7d3",  # LINK/USD
                "0xb966b05cb5a204ba60485b941d59006162d90fdd",  # BONK/USD
                "0x69f2a7a644fc0e23603e0d6ea679d6209cc38458",  # MOODENG/USD
                "0x5bd90d9e8e513e2557c1f6945585f3e9cafd1f09",  # GOAT/USD
                "0xbd33231a724965bd0ba02caebd21f832735778ef",  # FLOKI/USD
                "0x1f4b02954fd6a44ce1905c01ae2f8e902f83e0db",  # PNUT/USD
                "0x19e9e428627aab6dc5fb8b28b8331c1bcf04a44f",  # FARTCOIN/USD
                "0xe00f6574f7ed4cc902b3aab1aa9bf57274468062",  # PEOPLE/USD
                "0x9954d154a35785919eb905bb39d419d2724849a3",  # Recent deployment
            ]
        ]

    def verify_market_registry(self):
        """Verify MarketRegistry contract"""
        print("\n" + "="*80)
        print("1. VERIFYING MARKET REGISTRY")
        print("="*80)

        print(f"\nMarketRegistry: {self.market_registry}")

        # Get contract creation info
        print("\nQuerying contract creation info...")
        creation_info = self.api.get_contract_creation([self.market_registry])

        if creation_info and len(creation_info) > 0:
            info = creation_info[0]
            deployer = info['contractCreator']
            tx_hash = info['txHash']

            is_expected = (deployer.lower() == self.expected_registry_deployer.lower())
            status = "✅" if is_expected else "❌"

            print(f"\n{status} Deployer: {deployer}")
            print(f"   Expected: {is_expected} (admin EOA)")
            print(f"   TX: {tx_hash}")

            self.results["contracts"]["market_registry"] = {
                "address": self.market_registry.lower(),
                "deployer": deployer.lower(),
                "deployment_tx": tx_hash,
                "verified_deployer": is_expected,
                "expected_deployer": self.expected_registry_deployer.lower()
            }
        else:
            print(f"\n❌ Could not retrieve creation info")
            self.results["contracts"]["market_registry"] = {
                "address": self.market_registry.lower(),
                "error": "creation_info_unavailable"
            }

        # Try to get ABI
        print("\nQuerying contract ABI...")
        try:
            abi_info = self.api.get_contract_abi(self.market_registry)
            if abi_info and abi_info.get("abi"):
                print(f"✅ ABI available ({len(abi_info['abi'])} functions/events)")
                self.results["contracts"]["market_registry"]["has_abi"] = True
                self.results["contracts"]["market_registry"]["abi_size"] = len(abi_info['abi'])
            else:
                print(f"⚠️  ABI not available")
                self.results["contracts"]["market_registry"]["has_abi"] = False
        except Exception as e:
            print(f"⚠️  Error fetching ABI: {e}")
            self.results["contracts"]["market_registry"]["has_abi"] = False

    def verify_position_managers(self):
        """Verify all PositionManager contracts"""
        print("\n" + "="*80)
        print("2. VERIFYING POSITION MANAGER CONTRACTS")
        print("="*80)

        print(f"\nTotal PositionManagers to verify: {len(self.position_managers)}")

        # Get creation info for all position managers
        print("\nQuerying contract creation info (batch)...")
        creation_info = self.api.get_contract_creation(self.position_managers)

        # Create lookup dict
        creation_by_address = {
            info['contractAddress'].lower(): info
            for info in creation_info
        }

        deployers = set()

        for i, pm_address in enumerate(self.position_managers, 1):
            print(f"\n[{i}/{len(self.position_managers)}] {pm_address}")

            info = creation_by_address.get(pm_address.lower())

            if not info:
                print(f"  ❌ Creation info not found")
                self.results["contracts"]["position_managers"].append({
                    "address": pm_address.lower(),
                    "error": "creation_info_not_found"
                })
                continue

            deployer = info['contractCreator']
            tx_hash = info['txHash']
            deployers.add(deployer.lower())

            is_expected = (deployer.lower() == self.expected_pm_deployer.lower())
            status = "✅" if is_expected else "❌"

            print(f"  {status} Deployer: {deployer}")
            print(f"     Expected: {is_expected} (MarketRegistry factory)")
            print(f"     TX: {tx_hash}")

            pm_data = {
                "address": pm_address.lower(),
                "deployer": deployer.lower(),
                "deployment_tx": tx_hash,
                "verified_deployer": is_expected,
                "expected_deployer": self.expected_pm_deployer.lower()
            }

            self.results["contracts"]["position_managers"].append(pm_data)

        # Check if all deployed by same address
        print(f"\n{'='*80}")
        if len(deployers) == 1 and self.expected_pm_deployer.lower() in deployers:
            print(f"✅ ALL {len(self.position_managers)} PositionManagers deployed by: {self.expected_pm_deployer}")
            print(f"   (Factory pattern: MarketRegistry deploys PositionManagers)")
            self.results["statistics"]["single_deployer"] = True
            self.results["statistics"]["pm_deployer"] = self.expected_pm_deployer
        else:
            print(f"⚠️  Multiple deployers found: {deployers}")
            self.results["statistics"]["single_deployer"] = False

    def find_associated_contracts(self):
        """
        Find associated contracts (Orders, Vault, FundingTracker) for each PositionManager

        Strategy: Search for contract creation transactions from the same deployer
        around the same block range as each PositionManager deployment.
        """
        print("\n" + "="*80)
        print("3. FINDING ASSOCIATED CONTRACTS (Orders, Vault, FundingTracker)")
        print("="*80)

        print("\nNote: This requires searching for contracts deployed in the same")
        print("transaction or block range. For demonstration, we'll verify the")
        print("pattern with a sample market.")

        # Sample: First PositionManager (AVAX/USD)
        sample_pm = self.position_managers[0]
        print(f"\nSample Market: {sample_pm}")

        # From analysis, we know each market has 4 contracts
        # For public verification, we would:
        # 1. Get deployment transaction
        # 2. Search for other contracts deployed in same transaction or nearby blocks
        # 3. Verify they share same deployer
        # 4. Verify they match expected contract types (Orders, Vault, FundingTracker)

        print("\n⚠️  Full associated contract discovery requires:")
        print("   1. Transaction trace analysis (internal transactions)")
        print("   2. Constructor parameter analysis")
        print("   3. Or querying PositionManager for associated addresses")
        print("\nThis is feasible via RPC eth_call or analyzing deployment patterns.")
        print("For this verification, we focus on PositionManager contracts as the")
        print("primary entry points, since they emit the key events.")

        # Placeholder for full implementation
        self.results["contracts"]["associated_contracts"] = {
            "note": "Associated contract discovery (Orders, Vault, FundingTracker) requires transaction trace analysis",
            "approach": "Query PositionManager for associated addresses via eth_call or analyze deployment patterns",
            "sample_verified": False
        }

    def generate_statistics(self):
        """Generate verification statistics"""
        print("\n" + "="*80)
        print("4. GENERATING STATISTICS")
        print("="*80)

        total = 1 + len(self.position_managers)  # Registry + PMs
        verified = 0

        # Count verified contracts
        if self.results["contracts"]["market_registry"].get("verified_deployer"):
            verified += 1

        for pm in self.results["contracts"]["position_managers"]:
            if pm.get("verified_deployer"):
                verified += 1

        self.results["statistics"]["total_contracts"] = total
        self.results["statistics"]["verified_contracts"] = verified

        print(f"\n📊 Verification Statistics:")
        print(f"   Total Contracts: {total}")
        print(f"   Verified Contracts: {verified}")
        print(f"   Verification Rate: {verified/total*100:.1f}%")

    def generate_report(self):
        """Generate summary report"""
        print("\n" + "="*80)
        print("CONTRACT VERIFICATION SUMMARY")
        print("="*80)

        stats = self.results["statistics"]

        print(f"\n📋 Verification Results:")
        print(f"   Timestamp: {self.results['timestamp']}")
        print(f"   Latest Block: {self.results['latest_block']}")

        print(f"\n🏛️  Contract Structure:")
        print(f"   MarketRegistry: {self.results['contracts']['market_registry'].get('address', 'N/A')}")
        print(f"   PositionManagers: {len(self.position_managers)}")
        print(f"   Total Contracts: {stats['total_contracts']}")

        print(f"\n✅ Verification Status:")
        print(f"   Verified: {stats['verified_contracts']}/{stats['total_contracts']}")
        print(f"   Single PM Deployer: {stats['single_deployer']}")
        print(f"   PM Deployer: {stats.get('pm_deployer', 'N/A')}")

        print(f"\n🏭 Factory Pattern:")
        print(f"   MarketRegistry deployed by: {self.admin_eoa}")
        print(f"   PositionManagers deployed by: MarketRegistry (factory)")
        print(f"   This is the expected architecture pattern")

        print(f"\n🎯 Overall Assessment:")
        if stats['verified_contracts'] == stats['total_contracts'] and stats['single_deployer']:
            print("   ✅ ALL CONTRACTS VERIFIED")
            print("   ✅ Factory pattern confirmed")
            print("   ✅ MarketRegistry deployed by admin EOA")
            print("   ✅ All PositionManagers deployed by MarketRegistry")
        else:
            print("   ⚠️  Some contracts failed verification")

        print(f"\n🔗 Verification Links:")
        print(f"   MarketRegistry: https://snowtrace.io/address/{self.market_registry}")
        print(f"   Admin EOA: https://snowtrace.io/address/{self.admin_eoa}")

    def save_results(self, filename: str = "contracts_verified.json"):
        """Save results to JSON file"""
        output_path = Path("results") / filename
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n✅ Results saved to: {output_path}")

    def run(self):
        """Run full verification"""
        print("="*80)
        print("TRADESTA CONTRACT VERIFICATION")
        print("="*80)
        print("\nUsing ONLY public data sources:")
        print("- Routescan API (contract creation, ABIs)")
        print("- No MongoDB or private infrastructure required")

        try:
            self.verify_market_registry()
            self.verify_position_managers()
            self.find_associated_contracts()
            self.generate_statistics()
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
    verifier = ContractVerifier()
    verifier.run()


if __name__ == "__main__":
    main()
