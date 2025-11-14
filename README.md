# TradeSta Protocol - Verification Suite

Independent verification package demonstrating complete understanding of the TradeSta perpetual futures protocol on Avalanche C-Chain.

**✅ No Database Required** - Uses only public blockchain data sources:
- Routescan API (Snowtrace/RouteScan)
- Avalanche RPC (public endpoints)

---

## Understanding TradeSta: How Perpetual Futures Work

TradeSta is a decentralized perpetual futures exchange where traders can:
- Open leveraged long/short positions on crypto assets (AVAX, BTC, ETH, etc.)
- Trade without expiration dates (perpetual contracts)
- Use USDC as collateral across all markets
- Access up to 50x leverage on some markets

### Protocol Architecture: The Four-Contract System

Each market in TradeSta consists of **four interconnected contracts**:

```
Market (e.g., BTC/USD)
├── PositionManager    → Core trading logic (open, close, liquidate positions)
├── Orders             → Limit order management (create, execute, cancel orders)
├── Vault              → USDC collateral storage (holds user funds)
└── FundingTracker     → Funding rate calculations (balances longs vs shorts)
```

**MarketRegistry** is the factory that deploys and coordinates all markets.

### How a Trade Works: Position Lifecycle

1. **User wants to trade**: Deposit USDC, choose market (e.g., ETH/USD), decide long/short and leverage
2. **Keeper creates position**: Whitelisted keeper calls `PositionManager.createMarketPosition()`
   - USDC collateral moved from user to Vault
   - Position recorded with entry price from Pyth oracle
   - Liquidation price calculated based on leverage
   - `PositionCreated` event emitted
3. **Position stays open**: Funding payments accrue based on long/short imbalance
4. **Position closes** (three ways):
   - **Normal close**: User closes, PnL settled, collateral ± profit returned (`PositionClosed` event)
   - **Price liquidation**: Price hits liquidation level, keeper liquidates (`PositionLiquidated` event)
   - **Funding liquidation**: Funding fees drain collateral (`CollateralSeized` event)

### Critical Mechanism: Dual Liquidation System

TradeSta has **two separate liquidation mechanisms** (discovered during verification):

**1. Price-Based Liquidation** (`PositionLiquidated` event):
- Triggered when mark price reaches liquidation price
- Keeper receives liquidation fee
- Remaining collateral goes to vault (insurance pool)

**2. Funding-Based Liquidation** (`CollateralSeized` event):
- Triggered when cumulative funding fees >= remaining collateral
- Can liquidate **profitable positions** if funding drains collateral
- Less common (zero occurrences found in historical data)

### Funding Rates: Balancing Long/Short Interest

Funding rates incentivize balance between longs and shorts:

**Formula**: `k = K0 + BETA * ln(1 + skew)` where skew = |longs/shorts - 1|

- **More longs than shorts**: Longs pay shorts (discourages longs, encourages shorts)
- **More shorts than longs**: Shorts pay longs (discourages shorts, encourages longs)
- **Balanced**: Minimal funding payments

Rates update periodically (epoch-based) via `FundingTracker.logEpoch()` called by keepers.

---

## What This Verification Package Demonstrates

This package proves complete understanding of TradeSta by **reconstructing the entire protocol state** from public blockchain data.

### 1. Protocol Architecture Understanding

**Contract Verification** (`verify_contracts.py`):
- Identifies all 97 contracts (1 MarketRegistry + 24 markets × 4 contracts each)
- Confirms factory pattern: MarketRegistry deploys PositionManagers
- Validates contract verification on Snowtrace

**Associated Contracts** (`verify_associated_contracts_v2.py`):
- Discovers the four-contract "quartet" for each market
- Uses MarketRegistry getter functions (`getVaultAddress()`, etc.)
- Verifies USDC as collateral token across all markets
- **Proves understanding**: Markets aren't isolated—they're coordinated systems

### 2. Governance & Access Control Understanding

**Governance Verification** (`verify_governance.py`):
- Identifies admin EOA and its permissions
- Verifies keeper whitelist (who can execute trades/liquidations)
- Tracks role changes via `RoleGranted` events
- **Proves understanding**: TradeSta isn't permissionless—keepers mediate user actions

### 3. Trading Mechanics Understanding

**Event Statistics** (`verify_events_enhanced.py`):
- Tracks complete position lifecycle: created → closed/liquidated
- Monitors **both** liquidation mechanisms (price + funding)
- Calculates liquidation rates, closure rates per market
- **Proves understanding**: Can reconstruct all trading activity from events

**Sample Data** (AVAX/USD):
```
5,685 positions created
4,312 normally closed (75.9%)
1,359 price-liquidated (23.9%)
0 funding-liquidated (0%)
14 still open
```

### 4. Position Accounting Understanding

**Lifecycle Verification** (`verify_position_lifecycle.py`):
- Validates: `created = closed + price_liquidated + funding_liquidated + open`
- Detects discrepancies (zombie/ghost positions)
- Compares event history to contract state (`getAllActivePositionIds()`)
- **Proves understanding**: Events + contract state form complete audit trail

### 5. Risk Mechanics Understanding

**Liquidation Cascade Analysis** (`analyze_liquidation_cascades.py`):
- Uses `findLiquidatablePricesLong/Short()` to map liquidation levels
- Identifies "cascade zones" where multiple positions liquidate at same price
- Calculates distance from current price to cascade zones
- **Proves understanding**: Protocol has built-in cascade detection functions

**Protocol Solvency** (`verify_protocol_solvency.py`):
- Verifies vaults can cover all winning positions
- Calculates: `vault_balance >= locked_collateral + unrealized_profits`
- Monitors each market's solvency independently
- **Proves understanding**: Each market's Vault must be independently solvent

### 6. Market Discovery Understanding

**New Market Detection** (`detect_new_markets.py`):
- Monitors `MarketCreated` events from MarketRegistry
- Discovers new markets as they deploy
- Extracts pricefeed IDs, manager addresses
- **Proves understanding**: Markets deploy via single event, fully discoverable on-chain

---

## Quick Start

### Using Docker (Recommended)

```bash
# Build the verification image
docker build -t tradesta-verify .

# Run complete verification
docker run --rm -v $(pwd)/results:/verification/results tradesta-verify
```

### Using Python Directly

```bash
# Install dependencies
pip install -r requirements.txt

# Run all verifications
python3 scripts/verify_all.py              # Core protocol verification
python3 scripts/verify_all_phase2.py --all # Advanced analytics

# Or run individual verifications
python3 scripts/verify_contracts.py
python3 scripts/verify_associated_contracts_v2.py
python3 scripts/verify_governance.py
python3 scripts/verify_events_enhanced.py --sample 3
python3 scripts/verify_position_lifecycle.py --sample 3
python3 scripts/analyze_liquidation_cascades.py --sample 3
python3 scripts/verify_protocol_solvency.py --sample 3

# Monitor for new markets
python3 detect_new_markets.py
```

---

## Verification Scripts Explained

### Core Protocol Verification

**`verify_contracts.py`** - Contract Architecture
- Discovers all 97 contracts via `MarketCreated` events
- Verifies factory pattern (MarketRegistry → PositionManagers)
- Proves: Understanding of deployment structure

**`verify_associated_contracts_v2.py`** - Four-Contract System
- Gets quartet for each market (PositionManager, Orders, Vault, FundingTracker)
- Uses `getPositionManagerAddress(pricefeedId)` and similar getters
- Proves: Understanding of market composition

**`verify_governance.py`** - Access Control
- Identifies admin and keeper addresses
- Verifies roles via `hasRole(bytes32, address)`
- Proves: Understanding of permission system

### Trading Activity Verification

**`verify_events_enhanced.py`** - Complete Position Tracking
- Tracks all position lifecycle events
- Monitors both liquidation types (price + funding)
- Calculates accurate statistics per market
- Proves: Understanding of dual liquidation mechanism

**`verify_position_lifecycle.py`** - Accounting Audit
- Validates position accounting: created = settled + open
- Detects anomalies (zombie/ghost positions)
- Compares events to contract state
- Proves: Understanding of complete lifecycle

### Risk & Analytics

**`analyze_liquidation_cascades.py`** - Cascade Risk
- Maps liquidation price levels
- Identifies concentration risks
- Uses built-in cascade functions
- Proves: Understanding of systemic liquidation risk

**`verify_protocol_solvency.py`** - Fund Safety
- Checks vault balances vs obligations
- Calculates unrealized PnL
- Verifies protocol can pay winners
- Proves: Understanding of solvency requirements

**`detect_new_markets.py`** - Market Monitoring
- Watches for `MarketCreated` events
- Alerts on new market deployments
- Proves: Understanding of market discovery

---

## Key Discoveries

### 1. Dual Liquidation Mechanisms
Found through ABI analysis: TradeSta has **two** liquidation paths, not one.
- Most protocols: price-based liquidation only
- TradeSta: price-based **and** funding-based
- Historical data: 0 funding liquidations (mechanism exists but unused)

### 2. Four-Contract Market Architecture
Each market isn't a single contract—it's four coordinated contracts:
- PositionManager: trading logic
- Orders: limit order book
- Vault: USDC storage (security-critical)
- FundingTracker: funding rate calculations

### 3. Keeper-Mediated Trading
Users don't directly call contract functions. Instead:
- Whitelisted keepers execute on behalf of users
- Prevents MEV/frontrunning attacks
- Requires trust in keeper infrastructure

### 4. Vault Security Model
Each market has independent Vault holding USDC collateral:
- Must be solvent to cover all winning positions
- Emergency withdrawal function exists (admin-only)
- Internal accounting broken (shows zero inflows despite holding USDC)
- **Verification uses actual USDC balances, not internal counters**

### 5. Funding Rate Mechanism Status
FundingTracker implementation discovered:
- Formula: `k = K0 + BETA * ln(1 + skew)`
- Transparent and verifiable
- However: only 1 epoch recorded since deployment (mechanism not actively updating)

---

## Data Sources & Methodology

### Public Data Sources Only

**Routescan API** (`api.routescan.io`):
- Contract creation info (deployers, timestamps)
- Contract ABIs and source code
- Event logs with pagination (10,000 events per page)
- Rate limits: 120 req/min, 10,000 req/day

**Avalanche RPC** (`api.avax.network`):
- Contract state reading via `eth_call`
- Role verification (`hasRole()`)
- Position queries (`getAllActivePositionIds()`)
- Block number queries

### Verification Methodology

1. **Event-Driven Discovery**: Find contracts via events (not hardcoded addresses)
2. **Contract State Queries**: Read current state via RPC calls
3. **ABI Analysis**: Understand functions/events by examining contract ABIs
4. **Cross-Verification**: Compare events to contract state for consistency
5. **Statistical Analysis**: Calculate rates, distributions from event data

**Caching**: All API responses cached locally for instant re-runs

---

## Protocol Statistics (as of November 2025)

**Protocol Scale**:
- 24 markets deployed
- 97 total contracts (1 registry + 24 markets × 4 contracts)
- 8,062 positions created (sample: AVAX, BTC, ETH markets)
- $43,810.82 USDC held in vaults across all markets

**Market Activity** (sample markets):
- AVAX/USD: 5,685 positions, 23.9% liquidation rate
- BTC/USD: 1,235 positions, 60.0% liquidation rate
- ETH/USD: 1,142 positions, 54.8% liquidation rate

**Liquidation Breakdown**:
- Price-based liquidations: 2,726 (100% of liquidations)
- Funding-based liquidations: 0 (0%)
- Normal closures: 5,320
- Currently open: 16 positions

**Governance**:
- 1 admin EOA
- 2 whitelisted keepers
- 0 governance changes since deployment

---

## Technical Architecture

### Contract ABI Analysis

Complete ABI analysis for all contract types documented in `ABI_ANALYSIS_FINDINGS.md` (2,429 lines):

**MarketRegistry** (Factory):
- `MarketCreated` event: Discover new markets
- `getPositionManagerAddress(pricefeedId)`: Get quartet components
- `collateralTokenAddress()`: Verify USDC

**PositionManager** (Trading):
- `PositionCreated`, `PositionClosed`, `PositionLiquidated`, `CollateralSeized` events
- `getAllActivePositionIds()`: Get open positions
- `calculatePnL(positionId, price)`: Compute unrealized PnL
- `findLiquidatablePricesLong/Short()`: Cascade detection

**Orders** (Limit Orders):
- `LimitOrderCreated`, `LimitOrderExecuted` events
- `getAllLimitOrdersForSpecificUser()`: Enumerate orders

**Vault** (Collateral Storage):
- USDC balance via `balanceOf(vault)`
- **Security note**: Emergency withdrawal function exists

**FundingTracker** (Funding Rates):
- `epochToFundingRates(epoch)`: Historical rate data
- `getCurrentFundingRate()`: Current rate
- Formula: `k = K0 + BETA * ln(1 + skew)`

### Utility Modules

**`scripts/utils/routescan_api.py`**:
- API wrapper with automatic pagination
- Handles "No records found" gracefully
- Built-in rate limiting (0.5s between requests)
- Result caching for performance

**`scripts/utils/web3_helpers.py`**:
- Web3/RPC helper functions
- Event signature constants
- Role hash constants (OpenZeppelin AccessControl)
- Address utilities

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

## Performance

**Verification Times** (with caching):
- Contract verification: ~30 seconds (24 contracts)
- Governance verification: ~10 seconds
- Event statistics (3 markets): ~20 seconds
- Position lifecycle (3 markets): ~30 seconds
- Cascade analysis (3 markets): ~40 seconds
- Protocol solvency (3 markets): ~60 seconds

**Full Suite** (all verifications, all 24 markets): ~10-15 minutes first run, ~1-2 minutes with cache

---

## Documentation

- **`ABI_ANALYSIS_FINDINGS.md`** (2,429 lines): Complete ABI analysis for all 5 contract types
- **`PHASE2_IMPLEMENTATION_SUMMARY.md`**: Detailed implementation guide
- **`NEW_MARKET_DISCOVERY.md`**: Market discovery methodology
- **`PAGINATION_TEST_FINDINGS.md`**: API pagination strategy
- **`SHIPPING_CHECKLIST.md`**: Pre-flight verification checklist

---

## Key Addresses

**MarketRegistry**: `0x60f16b09a15f0c3210b40a735b19a6baf235dd18`
**Admin EOA**: `0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93`

**Top Markets** (by volume):
- AVAX/USD: `0x8d07fa9ac8b4bf833f099fb24971d2a808874c25`
- BTC/USD: `0x7da6e6d1b3582a2348fa76b3fe3b5e88d95281e7`
- ETH/USD: `0x5bd078689c358ca2c64daff8761dbf8cfddfc51f`

**Verification Links**:
- [MarketRegistry on Snowtrace](https://snowtrace.io/address/0x60f16b09a15f0c3210b40a735b19a6baf235dd18)
- [Admin EOA on Snowtrace](https://snowtrace.io/address/0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93)

---

## License

MIT License - Copyright (c) 2025 Avasnap

---

## Understanding Demonstrated

This verification package demonstrates complete understanding of:

✅ **Protocol Architecture**: Four-contract system, factory pattern, market coordination
✅ **Trading Mechanics**: Position lifecycle, dual liquidation system, keeper model
✅ **Funding Rates**: Skew-based formula, epoch system, long/short balancing
✅ **Risk Management**: Liquidation cascades, vault solvency, collateral requirements
✅ **Access Control**: Admin roles, keeper whitelist, permission structure
✅ **Event System**: Complete lifecycle tracking, position accounting, audit trail
✅ **Data Discovery**: Event-driven contract discovery, on-chain verification

**This isn't just verification—it's a blueprint for how TradeSta actually works.**

---

**Last Updated**: November 2025
**Blockchain**: Avalanche C-Chain (43114)
**Block Range**: 63,000,000 - latest
