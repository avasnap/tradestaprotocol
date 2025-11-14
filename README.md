# TradeSta Protocol - Public Verification Suite

Independent verification package for the TradeSta perpetual trading protocol on Avalanche C-Chain.

**✅ No Database Required** - Uses only public blockchain data sources:
- Routescan API (Snowtrace/RouteScan)
- Avalanche RPC (public endpoints)

---

## Quick Start

### Using Docker (Recommended)

```bash
# Build the verification image
docker build -t tradesta-verify .

# Run complete verification suite
docker run --rm -v $(pwd)/results:/verification/results tradesta-verify

# Results will be saved to ./results/
```

### Using Python Directly

```bash
# Install dependencies
pip install -r requirements.txt

# Run Phase 1 (basic) verification
python3 scripts/verify_all.py

# Run Phase 2 (advanced) verification - RECOMMENDED
python3 scripts/verify_all_phase2.py --sample 3  # Fast (3 markets)
python3 scripts/verify_all_phase2.py --all       # Complete (24 markets)

# Or run individual scripts
python3 scripts/verify_contracts.py
python3 scripts/verify_associated_contracts_v2.py
python3 scripts/verify_governance.py
python3 scripts/verify_events_enhanced.py --sample 3

# Detect new market deployments
python3 detect_new_markets.py
```

---

## What Gets Verified

### 1. Contract Verification (`verify_contracts.py`)

Verifies all TradeSta protocol contracts:

- **MarketRegistry**: Factory contract (deployed by admin EOA)
- **23 PositionManager contracts**: One per market (deployed by MarketRegistry)
- **Deployment verification**: Confirms factory pattern
- **ABI availability**: Checks contract verification status

**Results**: `results/contracts_verified.json`

**Expected Output**:
```
✅ ALL 24 CONTRACTS VERIFIED
✅ Factory pattern confirmed
✅ MarketRegistry deployed by admin EOA
✅ All PositionManagers deployed by MarketRegistry
```

### 2. Governance Verification (`verify_governance.py`)

Verifies governance structure and access control:

- **Admin roles**: DEFAULT_ADMIN_ROLE verification via eth_call
- **Keeper whitelist**: Verifies 2 keeper addresses
- **Role events**: Finds RoleGranted events
- **Deployer addresses**: Confirms single admin EOA

**Results**: `results/governance_verified.json`

**Key Findings**:
- Admin EOA: `0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93`
- MarketRegistry: `0x60f16b09a15f0c3210b40a735b19a6baf235dd18`
- 2 whitelisted keepers

### 3. Event Statistics Verification (`verify_events.py`)

Verifies protocol activity through event analysis:

- **PositionCreated events**: Position counts per market
- **PositionClosed events**: Normal closures
- **PositionLiquidated events**: Liquidation activity
- **Metrics**: Liquidation rates, closure rates, open positions

**Results**: `results/events_verified.json`

**Sample Output** (first 3 markets):
```
AVAX/USD: 5,671 positions (23.93% liquidation rate, 99.72% closure rate)
BTC/USD:  1,234 positions (59.72% liquidation rate, 99.84% closure rate)
ETH/USD:  1,142 positions (54.82% liquidation rate, 99.65% closure rate)
```

### 4. Enhanced Event Statistics (`verify_events_enhanced.py`) ⭐ NEW

Enhanced version with complete liquidation tracking:

- **PositionCreated events**: All position openings
- **PositionClosed events**: Normal closures
- **PositionLiquidated events**: Price-based liquidations
- **CollateralSeized events**: Funding-based liquidations ⭐ NEW
- **Accurate liquidation rates**: Includes BOTH liquidation mechanisms

**Results**: `results/events_enhanced_verified.json`

**Key Improvement**:
```
Old liquidation rate (price only):         23.93%
New liquidation rate (price + funding):    24.15%
Difference: +0.22% (was underreported)
```

**Usage**:
```bash
# Sample verification (3 markets)
python3 scripts/verify_events_enhanced.py --sample 3

# Full verification (all 24 markets)
python3 scripts/verify_events_enhanced.py --all
```

### 5. Position Lifecycle Verification (`verify_position_lifecycle.py`) ⭐ NEW

Verifies complete position accounting:

- **Lifecycle formula**: `created = closed + price_liquidated + funding_liquidated + open`
- **Zombie position detection**: Positions in events but missing from contract
- **Ghost position detection**: Positions in contract but missing creation events
- **Duplicate settlement detection**: Positions in multiple settlement categories

**Results**: `results/position_lifecycle_verified.json`

**What It Verifies**:
- ✅ All created positions are accounted for
- ✅ No stuck or lost positions
- ✅ Contract state matches event history
- ✅ Complete audit trail

**Usage**:
```bash
python3 scripts/verify_position_lifecycle.py --sample 3
```

### 6. Liquidation Cascade Analysis (`analyze_liquidation_cascades.py`) ⭐ NEW

Identifies liquidation risk zones:

- **Cascade zones**: Price levels where multiple positions liquidate
- **Critical zones**: Cascades within 5% of current price
- **Position clustering**: Number of positions per price level
- **Risk assessment**: Maximum cascade size analysis

**Results**: `results/liquidation_cascades_analyzed.json`

**Risk Metrics**:
- Total cascade zones identified
- Critical zones (within 5% of price)
- Largest cascade (most positions at single price)
- Collateral at risk per zone

**Usage**:
```bash
python3 scripts/analyze_liquidation_cascades.py --sample 3
```

**Note**: Uses placeholder prices. Production deployment requires Pyth oracle integration.

### 7. Protocol Solvency Verification (`verify_protocol_solvency.py`) ⭐ NEW

Verifies protocol can cover all user positions:

- **Vault balances**: Actual USDC held via `USDC.balanceOf(vault)`
- **Locked collateral**: Sum of all open position collateral
- **Unrealized PnL**: Total profits/losses on open positions
- **Solvency check**: `vault_balance >= locked_collateral + unrealized_profits`

**Results**: `results/protocol_solvency_verified.json`

**Critical Verification**:
- ✅ Protocol has sufficient funds to cover winning positions
- ✅ Vault security validated
- ⚠️ Detects undercollateralization
- ⚠️ Identifies solvency risks

**Usage**:
```bash
python3 scripts/verify_protocol_solvency.py --sample 3
```

**Limitations**: Uses simplified PnL calculation and placeholder prices. Production requires full position decoding and Pyth oracle.

---

## Phase 2 Verification Scripts Summary

The enhanced verification suite includes 4 new critical scripts:

| Script | Purpose | Critical Finding |
|--------|---------|------------------|
| `verify_events_enhanced.py` | Complete liquidation tracking | Found funding liquidations not tracked before |
| `verify_position_lifecycle.py` | Position accounting audit | Detects zombie/ghost positions |
| `analyze_liquidation_cascades.py` | Risk zone identification | Maps cascade dangers |
| `verify_protocol_solvency.py` | Protocol fund safety | Verifies ability to pay users |

**Run all Phase 2 verifications**:
```bash
# Using master script - Sample mode (fast, 3 markets)
python3 scripts/verify_all_phase2.py --sample 3

# Using master script - Full verification (all 24 markets)
python3 scripts/verify_all_phase2.py --all

# Or run individual scripts
python3 scripts/verify_events_enhanced.py --sample 3
python3 scripts/verify_position_lifecycle.py --sample 3
python3 scripts/analyze_liquidation_cascades.py --sample 3
python3 scripts/verify_protocol_solvency.py --sample 3
```

---

## Verification Strategy

### Public API Usage

**Routescan API** (`api.routescan.io`):
- Contract creation info (deployer addresses)
- Contract ABIs and source code
- Event logs with pagination
- Rate limits: 120 req/min, 10,000 req/day

**Avalanche RPC** (`api.avax.network`):
- Contract state reading via `eth_call`
- Role verification (`hasRole()`)
- Whitelist checking (`isWhitelisted()`)
- Block number queries

### Pagination Strategy

The Routescan API supports pagination for event retrieval:

```python
# Query entire blockchain history at once
events = api.get_all_logs(
    address=contract_address,
    topic0=event_signature,
    from_block=63_000_000,  # TradeSta deployment
    to_block=latest_block,
    offset=10000  # Max events per page
)
# Automatically paginate through all results
```

**Benefits**:
- No block range chunking needed
- Faster than chunking (80-90% time savings)
- Simpler implementation
- Exact event counts

See [PAGINATION_TEST_FINDINGS.md](PAGINATION_TEST_FINDINGS.md) for details.

### Caching

All API results are cached to disk:
- `cache/` directory stores API responses
- Subsequent runs are instant
- Cache keys based on query parameters

---

## Architecture

### Core Utilities

**`scripts/utils/routescan_api.py`**:
- Routescan API wrapper
- Automatic pagination
- Rate limiting (0.5s between requests)
- Result caching

**`scripts/utils/web3_helpers.py`**:
- Web3/RPC helper functions
- Event signature constants
- Role hash constants
- Address decoding utilities

### Verification Scripts

1. **`verify_contracts.py`**: Contract addresses and deployers
2. **`verify_governance.py`**: Admin roles and keepers
3. **`verify_events.py`**: Event statistics (sample: 3 markets)
4. **`verify_all.py`**: Master runner script

---

## Protocol Architecture

### Contracts

- **1 MarketRegistry**: Factory and governance
- **23 PositionManager contracts**: One per market
- **Associated contracts** (per market):
  - Orders contract (limit orders)
  - Vault contract (collateral)
  - FundingTracker contract (funding rates)

**Total**: ~93 contracts (1 registry + 23 markets × 4 contracts)

### Markets

**Open Markets** (9): AVAX, BTC, ETH, SOL, BNB, LINK, etc.
**Closed Markets** (14): Forex (5), Commodities (3), US Equities (6)

### Key Events

```solidity
event PositionCreated(
    bytes32 indexed positionId,
    address indexed owner,
    uint256 collateralAmount,
    uint256 positionSize,
    uint256 leverage,
    uint256 liquidationPrice,
    bool isLong,
    uint256 timestamp
);

event PositionClosed(
    bytes32 indexed positionId,
    address indexed owner,
    int256 pnl,
    uint256 collateralReturned,
    int256 fundingPayment,
    uint256 timestamp
);

event PositionLiquidated(
    bytes32 indexed positionId,
    address indexed liquidator,
    uint256 collateralAmount,
    uint256 liquidationFee,
    uint256 vaultFunds,
    uint256 timestamp
);
```

---

## Results Format

All verification scripts output JSON results:

```json
{
  "timestamp": "2025-01-13T12:34:56.789Z",
  "latest_block": 71884000,
  "verification_method": "public_api_only",
  "contracts": { ... },
  "statistics": { ... },
  "summary": { ... }
}
```

---

## Performance

### Verification Times

- **Contract Verification**: ~30 seconds (24 contracts, batched)
- **Governance Verification**: ~10 seconds (roles + events)
- **Event Verification**: ~20 seconds (3 markets sample)
- **Full Suite**: ~1 minute (with caching)

### Subsequent Runs

With caching enabled: **instant** (~1-2 seconds)

---

## Requirements

- Python 3.11+
- Internet connection (for API access)
- ~100 MB disk space (for cache)

### Dependencies

```
web3==6.20.0
eth-abi==5.0.0
requests==2.31.0
```

---

## Docker Details

### Build

```bash
docker build -t tradesta-verify .
```

### Run with Volume Mount

```bash
# Mount results directory
docker run --rm -v $(pwd)/results:/verification/results tradesta-verify

# Mount cache directory (for persistent caching)
docker run --rm \
  -v $(pwd)/results:/verification/results \
  -v $(pwd)/cache:/verification/cache \
  tradesta-verify
```

### Custom Commands

```bash
# Run specific script
docker run --rm tradesta-verify python3 scripts/verify_contracts.py

# Interactive shell
docker run --rm -it tradesta-verify /bin/bash
```

---

## Troubleshooting

### API Rate Limits

If you hit rate limits:
- Wait 1 minute between runs
- Scripts have built-in rate limiting (0.5s between requests)
- Caching prevents redundant requests

### Network Issues

```bash
# Test Routescan API
curl "https://api.routescan.io/v2/network/mainnet/evm/43114/etherscan/api?module=proxy&action=eth_blockNumber"

# Test Avalanche RPC
curl https://api.avax.network/ext/bc/C/rpc \
  -X POST \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
```

### Cache Issues

```bash
# Clear cache
rm -rf cache/

# Run verification again
python3 scripts/verify_all.py
```

---

## Verification Methodology

This verification package uses ONLY publicly available blockchain data:

1. **Contract Addresses**: Verified via Routescan API contract creation endpoint
2. **Event Counts**: Retrieved via Routescan getLogs with pagination
3. **Admin Roles**: Verified via eth_call to MarketRegistry `hasRole()` function
4. **Keeper Whitelist**: Verified via eth_call to `isWhitelisted()` function

**No Private Data Sources**:
- ❌ No MongoDB required
- ❌ No private APIs
- ❌ No proprietary infrastructure
- ✅ 100% reproducible by anyone

---

## New Market Detection

### Monitoring for New Markets

TradeSta's MarketRegistry emits a `MarketCreated` event when deploying new markets. Use the detection script to monitor for new deployments:

```bash
# Check for new markets since last check
python3 detect_new_markets.py

# Check from specific block
python3 detect_new_markets.py --from-block 71736710

# Query all markets from genesis
python3 detect_new_markets.py --all
```

**What it detects:**
- New market deployments via `MarketCreated` events
- PositionManager and OrderManager addresses
- Pyth price feed IDs
- Deployment transaction hash

**Output:**
- Prints new markets to console
- Saves `new_markets.json` with details
- Updates `last_checked_block.txt` for next run

**Automated Monitoring:**
```bash
# Run daily via cron
0 9 * * * cd /path/to/verification && python3 detect_new_markets.py
```

**Current Status:** 24 markets deployed (latest at block 71,736,710)

For detailed methodology, see [NEW_MARKET_DISCOVERY.md](NEW_MARKET_DISCOVERY.md)

---

## Key Addresses

**MarketRegistry**: `0x60f16b09a15f0c3210b40a735b19a6baf235dd18`
**Admin EOA**: `0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93`

**Top 3 Markets**:
- AVAX/USD: `0x8d07fa9ac8b4bf833f099fb24971d2a808874c25`
- BTC/USD: `0x7da6e6d1b3582a2348fa76b3fe3b5e88d95281e7`
- ETH/USD: `0x5bd078689c358ca2c64daff8761dbf8cfddfc51f`

**Verification Links**:
- [MarketRegistry on Snowtrace](https://snowtrace.io/address/0x60f16b09a15f0c3210b40a735b19a6baf235dd18)
- [Admin EOA on Snowtrace](https://snowtrace.io/address/0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93)

---

## License

This verification package is provided for transparency and independent verification purposes.

---

## Support

For issues or questions:
- Check Snowtrace for contract verification
- Review cached API responses in `cache/`
- Examine JSON results in `results/`

---

**Last Updated**: January 2025
**Blockchain**: Avalanche C-Chain (43114)
**Block Range**: 63,000,000 - latest
