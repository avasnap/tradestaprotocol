# TradeSta Protocol - Verification Suite

Independent verification package demonstrating complete understanding of the TradeSta perpetual futures protocol on Avalanche C-Chain.

---

## 📖 Understanding TradeSta Protocol

**Before diving into verification**, understand how TradeSta works:

### **[→ Read the Complete Protocol Guide](PROTOCOL_GUIDE.md)**

The Protocol Guide explains (with diagrams):
- **Four-Contract Architecture** - How PositionManager, Orders, Vault, and FundingTracker work together
- **Position Lifecycle** - From creation through settlement or liquidation
- **Dual Liquidation System** - Price-based (active) and funding-based (dormant)
- **Access Control** - Whitelisted keepers vs permissionless liquidators
- **Funding Mechanism** - How it should work vs current reality (disabled)

### Quick Protocol Overview

**What is TradeSta?**
- Decentralized perpetual futures exchange on Avalanche C-Chain
- Trade BTC, ETH, AVAX and other assets with leverage up to 100x
- USDC collateral across all markets
- Keeper-mediated position entry, permissionless liquidations

**Key Architecture Insight**: Each market = 4 interconnected contracts
```
Market (e.g., BTC/USD)
├── PositionManager  → Core trading logic
├── Orders           → Limit order book
├── Vault            → USDC collateral storage
└── FundingTracker   → Funding rate calculations (currently inactive)
```

**Critical Discovery**: Funding mechanism is **disabled** - protocol operates like traditional futures, not perpetual swaps.

---

## 🔍 Key Discoveries

### 1. Funding Rate Mechanism: Built But Disabled ⚠️

**Critical Finding**: TradeSta implements perpetual funding rates, but the mechanism is **completely inactive**:

- ❌ Funding rate frozen at **zero** since deployment (June 2025)
- ❌ Only **1 epoch logged** - `logEpoch()` never called
- ❌ Epoch size: **0 seconds** (not configured)
- ✅ **Effect**: Traders pay/receive zero funding fees regardless of market imbalance

**Implication**: Protocol operates like **traditional futures**, not true perpetual swaps. Positions can be held indefinitely without funding cost.

### 2. Dual Liquidation Mechanisms (One Active, One Dormant)

| Mechanism | Status | Count | Trigger |
|-----------|--------|-------|---------|
| Price-Based (`PositionLiquidated`) | ✅ **ACTIVE** | 2,726 | Mark price reaches liquidation price |
| Funding-Based (`CollateralSeized`) | ❌ **DORMANT** | 0 | Funding fees >= collateral |

**Why Funding Liquidations Can't Occur**: Funding rate is zero, so fees never accumulate.

### 3. Hybrid Permission Model

```mermaid
graph TB
    subgraph Actors
        Trader[👤 Trader]
        Keeper[🔑 Keeper<br/>Whitelisted]
        Anyone[🌐 Anyone]
    end

    subgraph "Operations"
        direction TB
        CreatePos[Open Position<br/>Market Order]
        ExecOrder[Execute Limit Order]
        UpdateFunding[Update Funding Epoch]
        ClosePos[Close Position]
        PriceLiq[Price Liquidation]
        FundingLiq[Funding Liquidation]
    end

    Trader -->|✅ Permissionless| CreatePos
    Trader -->|✅ Permissionless| ClosePos
    Trader -.requests.-> Keeper

    Keeper -->|✅ KEEPER_ROLE required| ExecOrder
    Keeper -->|✅ KEEPER_ROLE required| UpdateFunding

    Anyone -->|✅ No role required| PriceLiq
    Anyone -->|✅ No role required| FundingLiq

    style CreatePos fill:#e1ffe1
    style ClosePos fill:#e1ffe1
    style ExecOrder fill:#fff4e1
    style UpdateFunding fill:#fff4e1
    style PriceLiq fill:#e1ffe1
    style FundingLiq fill:#e1ffe1
    style Keeper fill:#ffd700
```

**Keepers only needed for limit orders** and funding updates. **Market orders and liquidations are permissionless**.

**Key Insight**: Anyone can open/close market order positions directly. Keepers only execute limit orders and update funding epochs.

### 4. Four-Contract Market Architecture

Each market = 4 interconnected contracts:
- **PositionManager** - Core trading logic
- **Orders** - Limit order book
- **Vault** - USDC collateral (security-critical)
- **FundingTracker** - Funding rates (currently inactive)

**→ [Protocol Architecture Guide](PROTOCOL_GUIDE.md#protocol-architecture-the-four-contract-system)** with diagrams

### 5. Vault Security Model

- Each market has independent Vault holding USDC
- Must remain solvent: `balance >= locked_collateral + unrealized_profits`
- ⚠️ Emergency withdrawal function exists (admin-only)
- ⚠️ Internal accounting broken (shows zero inflows despite holding USDC)

**Verification uses actual USDC balances**, not internal counters.

---

## Protocol Statistics (November 14, 2025 05:47 UTC)

| Metric | Value |
|--------|-------|
| **Markets Deployed** | 24 |
| **Total Contracts** | 97 (1 registry + 24 markets × 4) |
| **Positions Created** | 13,551 (all markets) |
| **Price Liquidations** | 6,276 |
| **Funding Liquidations** | 0 |
| **Liquidation Rate** | 46.3% (6,276 of 13,551) |
| **USDC in Vaults** | $43,825.62 |
| **Admin EOAs** | 1 |
| **Whitelisted Keepers** | 2 |

**Top Markets by Activity**:
- AVAX/USD: 5,687 positions (23.9% liquidation rate)
- BTC/USD: 1,236 positions (60.0% liquidation rate)
- ETH/USD: 1,143 positions (54.8% liquidation rate)

---

## 📚 Complete Documentation

### **[→ PROTOCOL_GUIDE.md](PROTOCOL_GUIDE.md)** - How TradeSta Works

**Start here to understand the protocol!** This guide explains:
- Four-Contract Architecture with interaction diagrams
- Position Lifecycle from creation to settlement
- Dual Liquidation System (price vs funding)
- Access Control (keepers vs liquidators)
- Funding Mechanism (how it should work vs reality)
- **5 Mermaid diagrams** visualizing protocol mechanics

**Read this if**: You want to understand how TradeSta actually works before diving into verification

---

### **[→ VERIFICATION_GUIDE.md](VERIFICATION_GUIDE.md)** - Running the Scripts

**Use this to run verifications and understand outputs.** This guide covers:
- All 13 verification scripts with usage examples
- What each script verifies and proves
- Sample outputs and interpretation
- Performance timings and troubleshooting
- Integration patterns for CI/CD

**Read this if**: You want to run the verification scripts yourself

---

### **[→ TECHNICAL_DETAILS.md](TECHNICAL_DETAILS.md)** - Implementation Deep Dive

**Technical reference for developers.** This guide documents:
- Data sources (Routescan API vs Avalanche RPC)
- Verification methodology with flowcharts
- Complete contract ABI documentation
- Utility modules (API wrappers, helpers)
- Performance metrics and optimization
- Known limitations and production fixes

**Read this if**: You want to understand how verification is implemented or extend the code

---

### **[→ ABI_ANALYSIS_FINDINGS.md](ABI_ANALYSIS_FINDINGS.md)** - Contract ABI Reference

**Comprehensive ABI analysis (2,429 lines).** Documents:
- All 5 contract types (MarketRegistry, PositionManager, Orders, Vault, FundingTracker)
- Every function signature and event
- Access control patterns
- Verification opportunities per contract

**Read this if**: You need detailed contract interface documentation

---

### **[→ SHIPPING_CHECKLIST.md](SHIPPING_CHECKLIST.md)** - Pre-Flight Verification

**Quality checklist for deployment.** Includes:
- Testing results for all scripts
- Known limitations and their impact
- Package contents inventory
- Success criteria validation

**Read this if**: You're preparing to deploy or audit the verification package

---

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Build verification image
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

# Or run individual scripts
python3 scripts/verify_contracts.py
python3 scripts/verify_events_enhanced.py --sample 3
```

**→ [Full Verification Guide](VERIFICATION_GUIDE.md)** for detailed script documentation

---

## What This Package Demonstrates

This verification suite proves complete understanding of TradeSta by **reconstructing the entire protocol state** from public blockchain data alone.

### How Verification Works

```mermaid
graph TB
    subgraph "Data Sources"
        RS[Routescan API<br/>Events, ABIs]
        RPC[Avalanche RPC<br/>State Queries]
    end

    subgraph "Verification"
        V1[Event-Driven<br/>Discovery]
        V2[Contract State<br/>Queries]
        V3[Cross-<br/>Verification]
    end

    subgraph "Output"
        R1[JSON Reports]
        R2[Statistics]
        R3[Anomaly Detection]
    end

    RS --> V1
    RPC --> V2
    V1 --> V3
    V2 --> V3
    V3 --> R1
    V3 --> R2
    V3 --> R3

    style RS fill:#e1f5ff
    style V3 fill:#e1ffe1
    style R1 fill:#99ff99
```

### Methodology

1. **Event-Driven Discovery** - Find contracts via `MarketCreated` events (not hardcoded)
2. **Contract State Queries** - Read current state via RPC `eth_call`
3. **ABI Analysis** - Understand capabilities by examining contract ABIs
4. **Cross-Verification** - Compare events to contract state for consistency
5. **Statistical Analysis** - Calculate rates, distributions, anomalies

**→ [Technical Details](TECHNICAL_DETAILS.md#verification-methodology)** for implementation specifics

### Protocol Understanding Demonstrated

✅ **Architecture** - Four-contract system (PositionManager, Orders, Vault, FundingTracker)
✅ **Trading Mechanics** - Position lifecycle, dual liquidation system, keeper model
✅ **Access Control** - Hybrid permission model (whitelisted keepers vs permissionless liquidators)
✅ **Risk Management** - Liquidation cascades, vault solvency, collateral requirements
✅ **Event System** - Complete lifecycle tracking, position accounting, audit trail
✅ **Data Discovery** - Event-driven contract discovery, on-chain verification

---

## Verification Scripts

### Core Protocol (Fast ~1 min)

| Script | What It Verifies | Proves |
|--------|------------------|--------|
| `verify_contracts.py` | 97 contracts via events | Factory pattern understanding |
| `verify_associated_contracts_v2.py` | Four-contract quartets | Market composition knowledge |
| `verify_governance.py` | Admin & keeper roles | Access control model |

### Trading Activity (Medium ~3 min)

| Script | What It Verifies | Proves |
|--------|------------------|--------|
| `verify_events_enhanced.py` | 8,062 positions, dual liquidation | Complete lifecycle tracking |
| `verify_position_lifecycle.py` | Accounting: created = settled + open | Event + state consistency |

### Risk & Analytics (Slower ~5 min)

| Script | What It Verifies | Proves |
|--------|------------------|--------|
| `analyze_liquidation_cascades.py` | Concentration risk at price levels | Cascade risk understanding |
| `verify_protocol_solvency.py` | Vault balances vs obligations | Solvency model knowledge |
| `detect_new_markets.py` | New market deployments | Market discovery capability |

**→ [Complete Script Guide](VERIFICATION_GUIDE.md)** with usage examples and output samples

---

## Performance

| Run Type | Time | API Calls |
|----------|------|-----------|
| **First Run** (cold cache) | 10-15 min | ~365 requests |
| **Cached Run** | 1-2 min | ~0 requests |
| **Sample (3 markets)** | 3-4 min | ~100 requests |

**Caching**: All Routescan responses cached locally (ABIs, source code, event logs)

**API Usage**: ~3.6% of daily limit (10,000 req/day)

**→ [Performance Metrics](TECHNICAL_DETAILS.md#performance-metrics)** for detailed breakdown

---

## Data Sources

**✅ No Database Required** - Uses only public blockchain data sources:

**Routescan API** (`api.routescan.io`) - **Primary Data Source**:
- Event logs, ABIs, contract source code
- Indexed data is **orders of magnitude faster** than querying chain directly
- Event log queries: ~1-2 seconds vs hours of RPC calls
- **Attribution**: This verification package would not be practical without Routescan's infrastructure

**Avalanche RPC** (`api.avax.network`) - **State Queries**:
- Contract state reading via `eth_call`
- Role verification, position queries, balances
- Used for real-time state that indexers don't provide

**🙏 Special Thanks**: This verification package relies heavily on **Routescan's indexed blockchain data API**. Without their infrastructure providing fast access to event logs, ABIs, and contract metadata, this comprehensive verification would require running a full archive node and indexing terabytes of blockchain data - making it impractical for independent verification.

---

## Requirements

- **Python**: 3.11+
- **Dependencies**: `web3`, `eth-abi`, `requests`
- **Disk Space**: ~100 MB (for cache)
- **Network**: Internet connection (Routescan API + Avalanche RPC)

```bash
pip install -r requirements.txt
```

---

## Key Addresses

| Component | Address |
|-----------|---------|
| **MarketRegistry** | `0x60f16b09a15f0c3210b40a735b19a6baf235dd18` |
| **Admin EOA** | `0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93` |
| **AVAX/USD Market** | `0x8d07fa9ac8b4bf833f099fb24971d2a808874c25` |
| **BTC/USD Market** | `0x7da6e6d1b3582a2348fa76b3fe3b5e88d95281e7` |
| **ETH/USD Market** | `0x5bd078689c358ca2c64daff8761dbf8cfddfc51f` |

**Verification Links**:
- [MarketRegistry on Snowtrace](https://snowtrace.io/address/0x60f16b09a15f0c3210b40a735b19a6baf235dd18)
- [Admin EOA on Snowtrace](https://snowtrace.io/address/0xe28bd6b3991f3e4b54af24ea2f1ee869c8044a93)

---

## License

MIT License - Copyright (c) 2025 Avasnap

---

## Understanding Demonstrated

This verification package demonstrates complete understanding of:

✅ **Protocol Architecture** - Four-contract system, factory pattern, market coordination
✅ **Trading Mechanics** - Position lifecycle, dual liquidation system, keeper model
✅ **Funding Rates** - Skew-based formula, epoch system, long/short balancing (currently inactive)
✅ **Risk Management** - Liquidation cascades, vault solvency, collateral requirements
✅ **Access Control** - Admin roles, keeper whitelist, hybrid permission structure
✅ **Event System** - Complete lifecycle tracking, position accounting, audit trail
✅ **Data Discovery** - Event-driven contract discovery, on-chain verification

**This isn't just verification—it's a blueprint for how TradeSta actually works.**

---

**Last Updated**: November 14, 2025 05:47 UTC
**Blockchain**: Avalanche C-Chain (43114)
**Block Range**: 63,000,000 - 71,932,816
