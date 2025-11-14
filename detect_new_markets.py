#!/usr/bin/env python3
"""
TradeSta New Market Detection Script

Detects new TradeSta markets by monitoring MarketCreated events from the
MarketRegistry contract.

This script uses ONLY public blockchain data:
- Routescan API for event logs
- No MongoDB or private infrastructure required

Usage:
    python3 detect_new_markets.py

Output:
    - Prints new markets to stdout
    - Updates last_checked_block.txt with latest block
    - Saves new_markets.json with discovery details
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent / "scripts"))

from utils.routescan_api import RoutescanAPI
from utils.web3_helpers import Web3Helper

# Constants
MARKET_REGISTRY = '0x60f16b09a15f0c3210b40a735b19a6baf235dd18'
MARKET_CREATED_SIG = '0x5eb977f82e9d0d89f65f05a56a99ab87e2ebb3909780e0b3642bec962789ba7a'
LAST_CHECKED_FILE = Path(__file__).parent / "last_checked_block.txt"
OUTPUT_FILE = Path(__file__).parent / "new_markets.json"

def load_last_checked_block() -> int:
    """Load the last checked block number from file"""
    if LAST_CHECKED_FILE.exists():
        with open(LAST_CHECKED_FILE, 'r') as f:
            return int(f.read().strip())
    else:
        # Default: Start from TradeSta deployment
        return 63_000_000

def save_last_checked_block(block: int):
    """Save the last checked block number to file"""
    with open(LAST_CHECKED_FILE, 'w') as f:
        f.write(str(block))

def detect_new_markets(from_block: int = None):
    """
    Detect new TradeSta markets deployed since from_block

    Args:
        from_block: Start searching from this block (default: last checked)

    Returns:
        List of new market dictionaries
    """
    api = RoutescanAPI(cache_dir='cache')
    w3 = Web3Helper()

    if from_block is None:
        from_block = load_last_checked_block()

    current_block = w3.get_latest_block()

    print("="*80)
    print("TRADESTA NEW MARKET DETECTION")
    print("="*80)
    print(f"\nMarketRegistry: {MARKET_REGISTRY}")
    print(f"Searching: Block {from_block:,} → {current_block:,}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print()

    # Query MarketCreated events
    print("Querying MarketCreated events...")
    events = api.get_all_logs(
        address=MARKET_REGISTRY,
        topic0=MARKET_CREATED_SIG,
        from_block=from_block,
        to_block=current_block,
        offset=10000
    )

    if not events:
        print("✅ No new markets found since last check")
        print(f"\nLast checked block: {from_block:,}")
        return []

    print(f"🎉 FOUND {len(events)} NEW MARKET(S)!\n")
    print("="*80)

    new_markets = []

    for i, event in enumerate(events, 1):
        # Parse event data
        block = int(event['blockNumber'], 16)
        tx_hash = event['transactionHash']
        topics = event['topics']

        pricefeed_id = topics[1]
        position_manager = '0x' + topics[2][-40:]
        order_manager = '0x' + topics[3][-40:]

        market = {
            'market_number': i,
            'block': block,
            'tx_hash': tx_hash,
            'position_manager': position_manager,
            'order_manager': order_manager,
            'pricefeed_id': pricefeed_id,
            'discovered_at': datetime.utcnow().isoformat()
        }

        new_markets.append(market)

        # Display
        print(f"\nMarket #{i}")
        print(f"  Block: {block:,}")
        print(f"  PositionManager: {position_manager}")
        print(f"  OrderManager: {order_manager}")
        print(f"  Pyth Feed ID: {pricefeed_id}")
        print(f"  Deployment TX: {tx_hash}")
        print(f"  Explorer: https://snowtrace.io/tx/{tx_hash}")

        # Try to get complete quartet
        print(f"\n  Finding complete quartet...")
        try:
            # Load factory deployments if available
            factory_file = Path(__file__).parent.parent / "analysis" / "factory_deployments.json"
            if factory_file.exists():
                with open(factory_file, 'r') as f:
                    deployments = json.load(f)

                quartet = [d['contract'] for d in deployments if d['tx_hash'] == tx_hash]

                if quartet:
                    print(f"  ✅ Found {len(quartet)} contracts in deployment:")

                    # Identify each contract type
                    for contract_addr in quartet:
                        try:
                            source_info = api.get_contract_source(contract_addr)
                            contract_type = source_info.get('ContractName', 'Unknown')
                            print(f"     {contract_type}: {contract_addr}")

                            # Add to market data
                            if contract_type not in market:
                                market[contract_type.lower()] = contract_addr
                        except:
                            print(f"     Unknown: {contract_addr}")
                else:
                    print(f"  ⚠️  Quartet not found in factory_deployments.json")
            else:
                print(f"  ℹ️  factory_deployments.json not available")
                print(f"  ℹ️  To get complete quartet, parse deployment transaction")

        except Exception as e:
            print(f"  ⚠️  Error retrieving quartet: {e}")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"New Markets: {len(new_markets)}")
    print(f"Current Block: {current_block:,}")
    print(f"Last Checked: {from_block:,}")

    # Save results
    if new_markets:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump({
                'timestamp': datetime.utcnow().isoformat(),
                'from_block': from_block,
                'to_block': current_block,
                'total_new_markets': len(new_markets),
                'markets': new_markets
            }, f, indent=2)

        print(f"\n✅ Results saved to: {OUTPUT_FILE}")

        # Update last checked block to highest block found
        latest_block = max(m['block'] for m in new_markets)
        save_last_checked_block(latest_block)
        print(f"✅ Updated last checked block to: {latest_block:,}")

    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    if new_markets:
        print("1. Update verification scripts with new market addresses")
        print("2. Re-run verification suite: python3 scripts/verify_all.py")
        print("3. Update TRADESTA_CONTRACTS.md with new market details")
    else:
        print("No action needed - no new markets found")

    return new_markets


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Detect new TradeSta markets via MarketCreated events'
    )
    parser.add_argument(
        '--from-block',
        type=int,
        help='Start searching from this block (default: last checked)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Query all markets from genesis (block 63,000,000)'
    )

    args = parser.parse_args()

    if args.all:
        from_block = 63_000_000
        print("Querying ALL markets from genesis...")
    elif args.from_block:
        from_block = args.from_block
    else:
        from_block = None  # Use last checked

    try:
        new_markets = detect_new_markets(from_block)

        if new_markets:
            sys.exit(0)  # Success - new markets found
        else:
            sys.exit(0)  # Success - no new markets

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
