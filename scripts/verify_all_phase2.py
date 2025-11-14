#!/usr/bin/env python3
"""
TradeSta Phase 2 Advanced Verification Suite Runner

Runs all Phase 2 advanced verification scripts:
1. Enhanced event statistics (complete liquidation tracking)
2. Position lifecycle verification (accounting audit)
3. Liquidation cascade analysis (risk zones)
4. Protocol solvency verification (fund safety)

These scripts provide deep insights into protocol health and security.
"""

import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone

def run_script(script_name: str, description: str, args: list = None) -> bool:
    """Run a verification script and return success status"""
    print(f"\n{'='*80}")
    print(f"Running: {description}")
    print(f"{'='*80}\n")

    script_path = Path(__file__).parent / script_name
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {script_name} failed with exit code {e.returncode}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Run TradeSta Phase 2 advanced verification suite'
    )
    parser.add_argument(
        '--sample',
        type=int,
        default=3,
        help='Number of markets to verify (default: 3 for sample mode)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Verify all 24 markets (overrides --sample)'
    )

    args = parser.parse_args()

    print("="*80)
    print("TRADESTA PHASE 2 ADVANCED VERIFICATION SUITE")
    print("="*80)
    print(f"\nStarted: {datetime.now(timezone.utc).isoformat()}")
    print("\nPhase 2 verifications provide:")
    print("- Complete liquidation tracking (price + funding mechanisms)")
    print("- Position lifecycle accounting audit")
    print("- Liquidation cascade risk analysis")
    print("- Protocol solvency verification")

    if args.all:
        print(f"\nMode: FULL VERIFICATION (all 24 markets)")
        script_args = []
    else:
        print(f"\nMode: SAMPLE VERIFICATION ({args.sample} markets)")
        script_args = ['--sample', str(args.sample)]

    print("\nUsing ONLY public data sources:")
    print("- Routescan API (events, contract info)")
    print("- Avalanche RPC (contract state)")
    print("\n")

    scripts = [
        ("verify_events_enhanced.py", "Enhanced Event Statistics (complete liquidation tracking)"),
        ("verify_position_lifecycle.py", "Position Lifecycle Verification (accounting audit)"),
        ("analyze_liquidation_cascades.py", "Liquidation Cascade Analysis (risk zones)"),
        ("verify_protocol_solvency.py", "Protocol Solvency Verification (fund safety)")
    ]

    results = []

    for script_name, description in scripts:
        success = run_script(script_name, description, script_args)
        results.append((description, success))

    # Print final summary
    print("\n" + "="*80)
    print("PHASE 2 VERIFICATION SUITE SUMMARY")
    print("="*80)

    all_passed = True
    for description, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {description}")
        if not success:
            all_passed = False

    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL PHASE 2 VERIFICATIONS PASSED")
    else:
        print("❌ SOME VERIFICATIONS FAILED")
    print("="*80)

    print(f"\nCompleted: {datetime.now(timezone.utc).isoformat()}")
    print("\nResults saved to:")
    print("- results/events_enhanced_verified.json")
    print("- results/position_lifecycle_verified.json")
    print("- results/liquidation_cascades_analyzed.json")
    print("- results/protocol_solvency_verified.json")

    print("\n💡 Next Steps:")
    print("- Review JSON results for detailed findings")
    print("- For production: integrate Pyth oracle for real-time prices")
    print("- For production: implement full position struct decoding")

    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
