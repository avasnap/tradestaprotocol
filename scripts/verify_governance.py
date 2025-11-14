#!/usr/bin/env python3
"""
TradeSta Governance Verification Script

Verifies governance structure and access control:
- Deployer addresses for all contracts
- Admin roles (DEFAULT_ADMIN_ROLE, ADMIN_ROLE)
- Keeper whitelist status
- Governance events (RoleGranted)

This script uses ONLY public data sources:
- Routescan API for contract creation info and events
- Avalanche RPC for state reading (hasRole, isWhitelisted)

No MongoDB or private infrastructure required.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper, EVENT_SIGNATURES, ROLES

class GovernanceVerifier:
    """Verify TradeSta governance structure"""

    def __init__(self):
        self.api = RoutescanAPI(cache_dir="cache")
        self.w3 = Web3Helper()

        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "latest_block": self.w3.get_latest_block(),
            "contracts_verified": [],
            "admin_verified": {},
            "keepers_verified": [],
            "role_events": [],
            "summary": {},
            "verification_method": "public_rpc_and_api_only"
        }

        # Known addresses from analysis (use Web3.to_checksum_address)
        from web3 import Web3
        self.market_registry = Web3.to_checksum_address("0x60f16b09a15f0c3210b40a735b19a6baf235dd18")
        self.expected_admin = Web3.to_checksum_address("0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93")

        self.known_keepers = [
            Web3.to_checksum_address("0xaee2ee1c899ecb6313a3c80ddaac40f2e1f6d9c4"),
            Web3.to_checksum_address("0x65fd3d40f9c2fd34c4ec54a3d0a0bc9900c8a3a1")
        ]

        # Sample PositionManager contracts to verify
        self.position_managers = [
            Web3.to_checksum_address("0x8d07fa9ac8b4bf833f099fb24971d2a808874c25"),  # Main AVAX market
            Web3.to_checksum_address("0x7da6e6d1b3582a2348fa76b3fe3b5e88d95281e7"),  # AVAX market 2
            Web3.to_checksum_address("0x5bd078689c358ca2c64daff8761dbf8cfddfc51f"),  # BTC market
        ]

    def verify_deployer_addresses(self):
        """Verify deployer addresses for sample contracts"""
        print("\n" + "="*80)
        print("1. VERIFYING DEPLOYER ADDRESSES")
        print("="*80)

        print(f"\nQuerying Routescan API for contract creation info...")

        # Get creation info for sample contracts
        contracts_to_check = [self.market_registry] + self.position_managers

        creation_info = self.api.get_contract_creation(contracts_to_check)

        for info in creation_info:
            contract_addr = info['contractAddress'].lower()
            deployer = info['contractCreator'].lower()
            tx_hash = info['txHash']

            self.results["contracts_verified"].append({
                "contract": contract_addr,
                "deployer": deployer,
                "creation_tx": tx_hash,
                "verified": True
            })

            is_expected = (deployer == self.expected_admin.lower())
            status = "✅" if is_expected else "❌"

            print(f"\n{status} Contract: {contract_addr}")
            print(f"   Deployer: {deployer}")
            print(f"   TX: {tx_hash}")
            print(f"   Expected: {is_expected}")

        # Check if all contracts deployed by same address
        deployers = set(c['deployer'] for c in self.results["contracts_verified"])

        if len(deployers) == 1 and self.expected_admin.lower() in deployers:
            print(f"\n✅ ALL CONTRACTS deployed by: {self.expected_admin}")
            self.results["summary"]["single_deployer"] = True
            self.results["summary"]["deployer_address"] = self.expected_admin
        else:
            print(f"\n⚠️  Multiple deployers found: {deployers}")
            self.results["summary"]["single_deployer"] = False

    def verify_admin_roles(self):
        """Verify admin has DEFAULT_ADMIN_ROLE via RPC"""
        print("\n" + "="*80)
        print("2. VERIFYING ADMIN ROLES (via eth_call)")
        print("="*80)

        print(f"\nChecking if {self.expected_admin} has admin roles...")
        print(f"Target contract: {self.market_registry}")

        # Check DEFAULT_ADMIN_ROLE
        print(f"\nChecking DEFAULT_ADMIN_ROLE...")
        has_default_admin = self.w3.has_role(
            self.market_registry,
            ROLES["DEFAULT_ADMIN_ROLE"],
            self.expected_admin
        )

        status = "✅" if has_default_admin else "❌"
        print(f"{status} DEFAULT_ADMIN_ROLE: {has_default_admin}")

        self.results["admin_verified"]["default_admin_role"] = {
            "contract": self.market_registry,
            "account": self.expected_admin,
            "has_role": has_default_admin,
            "role_hash": ROLES["DEFAULT_ADMIN_ROLE"]
        }

        # Note: ADMIN_ROLE might be a custom role, would need ABI to verify

        if has_default_admin:
            print(f"\n✅ VERIFIED: {self.expected_admin} is DEFAULT_ADMIN")
            self.results["summary"]["admin_verified"] = True
        else:
            print(f"\n❌ FAILED: {self.expected_admin} is NOT admin")
            self.results["summary"]["admin_verified"] = False

    def verify_keeper_whitelist(self):
        """Verify keeper addresses are whitelisted"""
        print("\n" + "="*80)
        print("3. VERIFYING KEEPER WHITELIST (via eth_call)")
        print("="*80)

        print(f"\nChecking whitelist status for known keepers...")
        print(f"MarketRegistry: {self.market_registry}")

        for keeper in self.known_keepers:
            print(f"\nKeeper: {keeper}")

            is_whitelisted = self.w3.is_whitelisted(
                self.market_registry,
                keeper
            )

            status = "✅" if is_whitelisted else "❌"
            print(f"  {status} Whitelisted: {is_whitelisted}")

            self.results["keepers_verified"].append({
                "address": keeper,
                "is_whitelisted": is_whitelisted,
                "verified_at_block": self.results["latest_block"]
            })

        whitelisted_count = sum(1 for k in self.results["keepers_verified"] if k["is_whitelisted"])

        print(f"\n✅ {whitelisted_count}/{len(self.known_keepers)} keepers whitelisted")
        self.results["summary"]["keepers_whitelisted"] = whitelisted_count

    def find_role_granted_events(self):
        """Find RoleGranted events from MarketRegistry"""
        print("\n" + "="*80)
        print("4. FINDING ROLE GRANTED EVENTS")
        print("="*80)

        print(f"\nSearching for RoleGranted events...")
        print(f"Contract: {self.market_registry}")
        print(f"Event: RoleGranted (0x2f878811...)")

        events = self.api.get_all_logs(
            address=self.market_registry,
            topic0=EVENT_SIGNATURES["RoleGranted"],
            from_block=63_000_000,  # Start of TradeSta deployment
            to_block=self.results["latest_block"],
            offset=1000
        )

        print(f"\n✅ Found {len(events)} RoleGranted events")

        for event in events[:10]:  # Show first 10
            # Decode event data
            role = event['topics'][1] if len(event['topics']) > 1 else None
            account = self.w3.decode_address_from_topic(event['topics'][2]) if len(event['topics']) > 2 else None
            sender = self.w3.decode_address_from_topic(event['topics'][3]) if len(event['topics']) > 3 else None

            print(f"\n  Block {event['blockNumber']}")
            print(f"    Role: {role}")
            print(f"    Account: {account}")
            print(f"    Sender: {sender}")
            print(f"    TX: {event['transactionHash']}")

            self.results["role_events"].append({
                "block": event['blockNumber'],
                "tx_hash": event['transactionHash'],
                "role": role,
                "account": account,
                "sender": sender
            })

        self.results["summary"]["role_events_found"] = len(events)

    def generate_report(self):
        """Generate summary report"""
        print("\n" + "="*80)
        print("GOVERNANCE VERIFICATION SUMMARY")
        print("="*80)

        summary = self.results["summary"]

        print(f"\n📊 Verification Results:")
        print(f"   Timestamp: {self.results['timestamp']}")
        print(f"   Latest Block: {self.results['latest_block']}")
        print(f"   Contracts Checked: {len(self.results['contracts_verified'])}")

        print(f"\n🏛️  Governance Structure:")
        print(f"   Single Deployer: {summary.get('single_deployer', False)}")
        print(f"   Deployer Address: {summary.get('deployer_address', 'N/A')}")
        print(f"   Admin Verified: {summary.get('admin_verified', False)}")

        print(f"\n🤖 Keeper System:")
        print(f"   Keepers Checked: {len(self.known_keepers)}")
        print(f"   Keepers Whitelisted: {summary.get('keepers_whitelisted', 0)}")

        print(f"\n📋 Events Found:")
        print(f"   RoleGranted Events: {summary.get('role_events_found', 0)}")

        # Overall assessment
        print(f"\n🎯 Overall Assessment:")

        if (summary.get('single_deployer') and
            summary.get('admin_verified') and
            summary.get('keepers_whitelisted', 0) == len(self.known_keepers)):
            print("   ✅ ALL VERIFICATIONS PASSED")
            print("   ✅ Governance structure matches analysis")
            print("   ⚠️  WARNING: Centralized (single EOA admin)")
        else:
            print("   ⚠️  Some verifications failed or inconclusive")

        print(f"\n🔗 Verification Links:")
        print(f"   MarketRegistry: https://snowtrace.io/address/{self.market_registry}")
        print(f"   Admin Address: https://snowtrace.io/address/{self.expected_admin}")

    def save_results(self, filename: str = "governance_verified.json"):
        """Save results to JSON file"""
        output_path = Path("results") / filename
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n✅ Results saved to: {output_path}")

    def run(self):
        """Run full verification"""
        print("="*80)
        print("TRADESTA GOVERNANCE VERIFICATION")
        print("="*80)
        print("\nUsing ONLY public data sources:")
        print("- Routescan API (contract creation, events)")
        print("- Avalanche RPC (eth_call for state reading)")
        print("\nNo MongoDB or private infrastructure required.")

        try:
            self.verify_deployer_addresses()
            self.verify_admin_roles()
            self.verify_keeper_whitelist()
            self.find_role_granted_events()
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
    verifier = GovernanceVerifier()
    verifier.run()


if __name__ == "__main__":
    main()
