#!/usr/bin/env python3
"""
TradeSta Complete Verification Suite Runner

Runs all verification scripts in sequence:
1. Contract verification (MarketRegistry + 23 PositionManagers)
2. Governance verification (admin roles, keepers)
3. Event statistics verification (position activity)

This is the main entry point for the verification package.
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone

def run_script(script_name: str, description: str) -> bool:
    """Run a verification script and return success status"""
    print(f"\n{'='*80}")
    print(f"Running: {description}")
    print(f"{'='*80}\n")

    script_path = Path(__file__).parent / script_name

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            capture_output=False
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {script_name} failed with exit code {e.returncode}")
        return False

def main():
    print("="*80)
    print("TRADESTA COMPLETE VERIFICATION SUITE")
    print("="*80)
    print(f"\nStarted: {datetime.now(timezone.utc).isoformat()}")
    print("\nThis suite will verify the entire TradeSta protocol using ONLY public APIs:")
    print("- Routescan API (contract info, events)")
    print("- Avalanche RPC (state reading)")
    print("\nNo MongoDB or private infrastructure required.\n")

    scripts = [
        ("verify_contracts.py", "Contract Verification (addresses, deployers)"),
        ("verify_associated_contracts.py", "Associated Contracts (Orders, Vault, FundingTracker)"),
        ("verify_governance.py", "Governance Verification (admin roles, keepers)"),
        ("verify_events.py", "Event Statistics Verification (position activity)")
    ]

    results = []

    for script_name, description in scripts:
        success = run_script(script_name, description)
        results.append((description, success))

    # Print final summary
    print("\n" + "="*80)
    print("VERIFICATION SUITE SUMMARY")
    print("="*80)

    all_passed = True
    for description, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {description}")
        if not success:
            all_passed = False

    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL VERIFICATIONS PASSED")
    else:
        print("❌ SOME VERIFICATIONS FAILED")
    print("="*80)

    print(f"\nCompleted: {datetime.now(timezone.utc).isoformat()}")
    print("\nResults saved to:")
    print("- results/contracts_verified.json")
    print("- results/associated_contracts_verified.json")
    print("- results/governance_verified.json")
    print("- results/events_verified.json")

    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
