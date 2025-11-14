#!/usr/bin/env python3
"""
Analyze Vault contract ABI for security verification

CRITICAL: Vault contracts hold all user USDC collateral.
This script examines what can be verified about vault state and security.
"""

import sys
import json
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.routescan_api import RoutescanAPI

def categorize_function(func):
    """Categorize function by type and security relevance"""
    name = func.get('name', '')
    state_mutability = func.get('stateMutability', '')

    # View/pure functions (read-only)
    if state_mutability in ['view', 'pure']:
        # Security-critical view functions
        if any(keyword in name.lower() for keyword in [
            'balance', 'reserve', 'collateral', 'total',
            'vault', 'usdc', 'asset', 'inflow', 'outflow',
            'solvency', 'health', 'deficit'
        ]):
            return 'SECURITY_VIEW'

        # General view functions
        return 'VIEW'

    # State-changing functions
    elif func['type'] == 'function':
        # Fund movement functions
        if any(keyword in name.lower() for keyword in [
            'deposit', 'withdraw', 'transfer', 'send',
            'move', 'claim', 'rescue', 'drain'
        ]):
            return 'SECURITY_WRITE'

        # Access control
        if any(keyword in name.lower() for keyword in [
            'owner', 'role', 'grant', 'revoke', 'admin'
        ]):
            return 'ACCESS_CONTROL'

        return 'WRITE'

    return 'OTHER'

def categorize_event(event):
    """Categorize event by security relevance"""
    name = event.get('name', '')

    # Fund movement events
    if any(keyword in name.lower() for keyword in [
        'deposit', 'withdraw', 'transfer', 'send',
        'inflow', 'outflow', 'moved', 'claimed'
    ]):
        return 'SECURITY_EVENT'

    # Underfunding/deficit events
    if any(keyword in name.lower() for keyword in [
        'deficit', 'underfund', 'shortage', 'insolvency'
    ]):
        return 'CRITICAL_EVENT'

    # Access control events
    if any(keyword in name.lower() for keyword in [
        'owner', 'role', 'grant', 'revoke'
    ]):
        return 'ACCESS_EVENT'

    return 'REGULAR_EVENT'

def analyze_vault_abi(address):
    """Fetch and analyze Vault contract ABI"""

    api = RoutescanAPI()

    print(f"\n{'='*80}")
    print(f"Vault Contract ABI Analysis")
    print(f"{'='*80}")
    print(f"Address: {address}")
    print(f"Purpose: Hold user USDC collateral (MOST CRITICAL)")
    print(f"{'='*80}\n")

    # Fetch ABI
    print("Fetching Vault ABI from Routescan...")
    result = api.get_contract_abi(address)
    abi = result['abi']

    if result.get('cached'):
        print("  [Cache hit]")

    print(f"  Found {len(abi)} ABI entries\n")

    # Categorize all items
    categories = {
        'SECURITY_VIEW': [],      # Balance, reserves, health checks
        'SECURITY_WRITE': [],     # Deposit, withdraw, fund movement
        'SECURITY_EVENT': [],     # Fund movement events
        'CRITICAL_EVENT': [],     # Underfunding, deficit events
        'ACCESS_CONTROL': [],     # Owner, role functions
        'ACCESS_EVENT': [],       # Access control events
        'VIEW': [],               # Other view functions
        'WRITE': [],              # Other state-changing functions
        'REGULAR_EVENT': [],      # Other events
        'OTHER': []               # Constructors, fallback, etc.
    }

    for item in abi:
        item_type = item.get('type', '')

        if item_type == 'function':
            category = categorize_function(item)
            categories[category].append(item)

        elif item_type == 'event':
            category = categorize_event(item)
            categories[category].append(item)

        else:
            categories['OTHER'].append(item)

    # Print analysis
    print("\n" + "="*80)
    print("SECURITY-CRITICAL VIEW FUNCTIONS (Query vault health)")
    print("="*80)

    for func in sorted(categories['SECURITY_VIEW'], key=lambda f: f['name']):
        print(f"\n📊 {func['name']}()")
        print(f"   Returns: {format_outputs(func)}")
        if func.get('inputs'):
            print(f"   Inputs: {format_inputs(func)}")

    print("\n" + "="*80)
    print("SECURITY-CRITICAL WRITE FUNCTIONS (Move funds)")
    print("="*80)

    for func in sorted(categories['SECURITY_WRITE'], key=lambda f: f['name']):
        print(f"\n⚠️  {func['name']}()")
        print(f"   Inputs: {format_inputs(func)}")
        print(f"   Mutability: {func.get('stateMutability', 'nonpayable')}")
        print(f"   WHO CAN CALL THIS? (check access control)")

    print("\n" + "="*80)
    print("SECURITY-CRITICAL EVENTS (Monitor fund movements)")
    print("="*80)

    for event in sorted(categories['SECURITY_EVENT'], key=lambda e: e['name']):
        print(f"\n🔔 {event['name']}")
        print(f"   Parameters: {format_inputs(event)}")
        print(f"   Purpose: Track fund movements in/out of vault")

    print("\n" + "="*80)
    print("CRITICAL DEFICIT/UNDERFUNDING EVENTS")
    print("="*80)

    if categories['CRITICAL_EVENT']:
        for event in sorted(categories['CRITICAL_EVENT'], key=lambda e: e['name']):
            print(f"\n🚨 {event['name']}")
            print(f"   Parameters: {format_inputs(event)}")
            print(f"   Purpose: ALERT - Vault may be underfunded!")
    else:
        print("\nNo explicit underfunding events found in ABI")
        print("Must verify solvency by comparing balances to obligations")

    print("\n" + "="*80)
    print("ACCESS CONTROL")
    print("="*80)

    if categories['ACCESS_CONTROL']:
        print("\nAccess Control Functions:")
        for func in sorted(categories['ACCESS_CONTROL'], key=lambda f: f['name']):
            print(f"  • {func['name']}()")

    if categories['ACCESS_EVENT']:
        print("\nAccess Control Events:")
        for event in sorted(categories['ACCESS_EVENT'], key=lambda e: e['name']):
            print(f"  • {event['name']}")

    print("\n" + "="*80)
    print("OTHER VIEW FUNCTIONS")
    print("="*80)

    for func in sorted(categories['VIEW'], key=lambda f: f['name']):
        print(f"  • {func['name']}() → {format_outputs(func)}")

    print("\n" + "="*80)
    print("OTHER WRITE FUNCTIONS")
    print("="*80)

    for func in sorted(categories['WRITE'], key=lambda f: f['name']):
        print(f"  • {func['name']}({format_inputs(func)})")

    print("\n" + "="*80)
    print("OTHER EVENTS")
    print("="*80)

    for event in sorted(categories['REGULAR_EVENT'], key=lambda e: e['name']):
        print(f"  • {event['name']}")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Security View Functions:  {len(categories['SECURITY_VIEW'])}")
    print(f"Security Write Functions: {len(categories['SECURITY_WRITE'])}")
    print(f"Security Events:          {len(categories['SECURITY_EVENT'])}")
    print(f"Critical Events:          {len(categories['CRITICAL_EVENT'])}")
    print(f"Access Control Functions: {len(categories['ACCESS_CONTROL'])}")
    print(f"Access Control Events:    {len(categories['ACCESS_EVENT'])}")
    print(f"Other View Functions:     {len(categories['VIEW'])}")
    print(f"Other Write Functions:    {len(categories['WRITE'])}")
    print(f"Other Events:             {len(categories['REGULAR_EVENT'])}")
    print(f"Other ABI Items:          {len(categories['OTHER'])}")

    print("\n" + "="*80)
    print("KEY SECURITY QUESTIONS TO ANSWER")
    print("="*80)
    print("1. Can we query total USDC held in vault?")
    print("2. Can we track inflows and outflows?")
    print("3. Can we verify vault solvency?")
    print("4. Who can withdraw funds from vault?")
    print("5. Are there emergency withdrawal functions?")
    print("6. Are there any underfunding events?")

    # Save detailed analysis
    output_file = Path("cache") / f"vault_abi_analysis_{address.lower()}.json"
    with open(output_file, 'w') as f:
        json.dump({
            "address": address,
            "analysis_categories": {
                category: [item['name'] for item in items]
                for category, items in categories.items()
            },
            "full_abi": abi,
            "statistics": {
                "total_functions": len([i for i in abi if i['type'] == 'function']),
                "total_events": len([i for i in abi if i['type'] == 'event']),
                "security_view": len(categories['SECURITY_VIEW']),
                "security_write": len(categories['SECURITY_WRITE']),
                "security_events": len(categories['SECURITY_EVENT'])
            }
        }, f, indent=2)

    print(f"\n✅ Detailed analysis saved to: {output_file}")

    return categories, abi

def format_inputs(item):
    """Format function inputs for display"""
    inputs = item.get('inputs', [])
    if not inputs:
        return "none"

    parts = []
    for inp in inputs:
        name = inp.get('name', 'unnamed')
        type_ = inp.get('type', 'unknown')
        indexed = ' indexed' if inp.get('indexed') else ''
        parts.append(f"{type_}{indexed} {name}")

    return ", ".join(parts)

def format_outputs(func):
    """Format function outputs for display"""
    outputs = func.get('outputs', [])
    if not outputs:
        return "void"

    if len(outputs) == 1:
        return outputs[0].get('type', 'unknown')

    return f"({', '.join(o.get('type', 'unknown') for o in outputs)})"

if __name__ == "__main__":
    # Sample Vault address from AVAX/USD market
    VAULT_ADDRESS = "0x8ef35061505842cfb9052312e65b994ba8221cc9"

    categories, abi = analyze_vault_abi(VAULT_ADDRESS)

    print("\n" + "="*80)
    print("Next: Append findings to ABI_ANALYSIS_FINDINGS.md")
    print("="*80)
