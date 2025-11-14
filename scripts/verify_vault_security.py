#!/usr/bin/env python3
"""
Verify Vault Security Across All TradeSta Markets

CRITICAL: Vaults hold all user USDC collateral.
This script verifies vault health, detects underfunding, and monitors for security issues.

Usage:
    python3 scripts/verify_vault_security.py
"""

import sys
import json
from pathlib import Path
from web3 import Web3
from typing import Dict, List

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI

# Avalanche RPC
AVALANCHE_RPC = "https://api.avax.network/ext/bc/C/rpc"

# Contract addresses
MARKET_REGISTRY = "0x60f16b09a15f0c3210b40a735b19a6baf235dd18"
USDC_ADDRESS = "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E"

# MarketRegistry ABI (minimal - just what we need)
REGISTRY_ABI = [
    {
        "inputs": [{"name": "pricefeedId", "type": "bytes32"}],
        "name": "getVaultAddress",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "index", "type": "uint256"}],
        "name": "allPriceOracles",
        "outputs": [
            {"name": "pricefeedId", "type": "bytes32"},
            {"name": "symbol", "type": "string"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Vault ABI
VAULT_ABI = [
    {
        "inputs": [],
        "name": "collateralTokenAddress",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "inflows",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "outflows",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "netFlow",
        "outputs": [{"name": "", "type": "int256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "isUnderFunded",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "marketRegistry",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "positionManager",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "withdrawableAddress",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# USDC ERC20 ABI
USDC_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

def get_all_vaults(w3, registry):
    """Get all vault addresses from MarketRegistry"""
    vaults = []

    # Try up to 30 markets (we know there are 24)
    for i in range(30):
        try:
            pricefeed_id, symbol = registry.functions.allPriceOracles(i).call()
            vault_address = registry.functions.getVaultAddress(pricefeed_id).call()

            vaults.append({
                'index': i,
                'symbol': symbol,
                'pricefeed_id': pricefeed_id.hex(),
                'vault_address': vault_address
            })

        except Exception as e:
            # No more markets
            break

    return vaults

def check_vault_health(w3, vault_address, usdc_contract):
    """Check health of a single vault"""

    vault = w3.eth.contract(
        address=Web3.to_checksum_address(vault_address),
        abi=VAULT_ABI
    )

    # Get vault state
    try:
        collateral_token = vault.functions.collateralTokenAddress().call()
        inflows = vault.functions.inflows().call()
        outflows = vault.functions.outflows().call()
        net_flow = vault.functions.netFlow().call()
        is_underfunded = vault.functions.isUnderFunded().call()
        market_registry = vault.functions.marketRegistry().call()
        position_manager = vault.functions.positionManager().call()
        withdrawable_address = vault.functions.withdrawableAddress().call()

        # Get actual USDC balance
        actual_balance = usdc_contract.functions.balanceOf(
            Web3.to_checksum_address(vault_address)
        ).call()

        # Calculate discrepancy
        expected_balance = inflows - outflows
        discrepancy = actual_balance - expected_balance

        # Determine status
        if is_underfunded:
            status = "CRITICAL"
            message = "Vault flagged as underfunded!"
        elif actual_balance < net_flow:
            status = "ALERT"
            message = f"Emergency withdrawal detected ({abs(discrepancy) / 10**6:.2f} USDC missing)"
        elif discrepancy > 10**6:  # More than 1 USDC difference
            status = "INFO"
            message = f"Vault has surplus ({discrepancy / 10**6:.2f} USDC)"
        else:
            status = "OK"
            message = "Vault is solvent"

        return {
            'status': status,
            'message': message,
            'actual_balance_usdc': actual_balance / 10**6,
            'inflows_usdc': inflows / 10**6,
            'outflows_usdc': outflows / 10**6,
            'net_flow_usdc': net_flow / 10**6,
            'discrepancy_usdc': discrepancy / 10**6,
            'is_underfunded': is_underfunded,
            'collateral_token': collateral_token,
            'collateral_is_usdc': collateral_token.lower() == USDC_ADDRESS.lower(),
            'market_registry': market_registry,
            'position_manager': position_manager,
            'withdrawable_address': withdrawable_address,
            'error': None
        }

    except Exception as e:
        return {
            'status': 'ERROR',
            'message': str(e),
            'error': str(e)
        }

def main():
    print("="*80)
    print("TradeSta Vault Security Verification")
    print("="*80)
    print()

    # Connect to Avalanche
    print("Connecting to Avalanche C-Chain...")
    w3 = Web3(Web3.HTTPProvider(AVALANCHE_RPC))

    if not w3.is_connected():
        print("❌ Failed to connect to Avalanche RPC")
        return

    print(f"✓ Connected (Block: {w3.eth.block_number:,})")
    print()

    # Load contracts
    registry = w3.eth.contract(
        address=Web3.to_checksum_address(MARKET_REGISTRY),
        abi=REGISTRY_ABI
    )

    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_ADDRESS),
        abi=USDC_ABI
    )

    # Get all vaults
    print("Discovering all vaults from MarketRegistry...")
    vaults = get_all_vaults(w3, registry)
    print(f"✓ Found {len(vaults)} vaults")
    print()

    # Check each vault
    results = []
    total_usdc = 0
    critical_count = 0
    alert_count = 0

    print("="*80)
    print("Vault Health Checks")
    print("="*80)

    for vault_info in vaults:
        symbol = vault_info['symbol']
        vault_address = vault_info['vault_address']

        print(f"\n[{vault_info['index']:2d}] {symbol:15s} {vault_address}")
        print("-" * 80)

        health = check_vault_health(w3, vault_address, usdc)

        if health['error']:
            print(f"  ❌ ERROR: {health['message']}")
            results.append({**vault_info, **health})
            continue

        # Status indicator
        status_icons = {
            'OK': '✓',
            'INFO': 'ℹ',
            'ALERT': '⚠',
            'CRITICAL': '🚨',
            'ERROR': '❌'
        }

        icon = status_icons.get(health['status'], '?')

        print(f"  {icon} Status: {health['status']} - {health['message']}")
        print(f"  USDC Balance: {health['actual_balance_usdc']:,.2f} USDC")
        print(f"  Inflows:      {health['inflows_usdc']:,.2f} USDC")
        print(f"  Outflows:     {health['outflows_usdc']:,.2f} USDC")
        print(f"  Net Flow:     {health['net_flow_usdc']:,.2f} USDC")

        if health['discrepancy_usdc'] != 0:
            print(f"  Discrepancy:  {health['discrepancy_usdc']:,.2f} USDC")

        if health['withdrawable_address'] != '0x0000000000000000000000000000000000000000':
            print(f"  Emergency Withdrawals → {health['withdrawable_address']}")

        # Verify configuration
        if not health['collateral_is_usdc']:
            print(f"  ⚠ WARNING: Collateral token is NOT USDC: {health['collateral_token']}")

        # Track totals
        total_usdc += health['actual_balance_usdc']

        if health['status'] == 'CRITICAL':
            critical_count += 1
        elif health['status'] == 'ALERT':
            alert_count += 1

        results.append({**vault_info, **health})

    # Summary
    print()
    print("="*80)
    print("Summary")
    print("="*80)
    print(f"Total Vaults:     {len(vaults)}")
    print(f"Total USDC:       {total_usdc:,.2f} USDC")
    print(f"Critical Vaults:  {critical_count}")
    print(f"Alert Vaults:     {alert_count}")
    print(f"Healthy Vaults:   {len([r for r in results if r.get('status') == 'OK'])}")
    print()

    if critical_count > 0:
        print("🚨 CRITICAL: Some vaults are underfunded!")
        print()

    if alert_count > 0:
        print("⚠ ALERT: Some vaults have balance discrepancies!")
        print()

    # Save results
    output_file = Path("cache/vault_security_check.json")
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': w3.eth.get_block('latest')['timestamp'],
            'block_number': w3.eth.block_number,
            'total_vaults': len(vaults),
            'total_usdc': total_usdc,
            'critical_count': critical_count,
            'alert_count': alert_count,
            'results': results
        }, f, indent=2)

    print(f"✓ Detailed results saved to: {output_file}")
    print()

    # Recommendations
    print("="*80)
    print("Recommendations")
    print("="*80)
    print("1. Monitor vaults continuously for balance changes")
    print("2. Alert on any USDC transfers out of vault addresses")
    print("3. Track 'withdrawableAddress' for emergency withdrawal destination")
    print("4. Verify MarketRegistry access control (who has admin role?)")
    print("5. Monitor 'isUnderFunded' flag for each vault")
    print()

if __name__ == "__main__":
    main()
