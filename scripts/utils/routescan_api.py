"""
Routescan API wrapper for TradeSta verification

Provides high-level functions for querying Routescan API with:
- Automatic pagination support
- Rate limiting
- Error handling
- Result caching
"""

import requests
import time
import json
from typing import Dict, List, Any, Optional
from pathlib import Path

class RoutescanAPI:
    """Wrapper for Routescan API with pagination and rate limiting"""

    def __init__(self, base_url: str = None, cache_dir: str = None):
        self.base_url = base_url or "https://api.routescan.io/v2/network/mainnet/evm/43114/etherscan/api"
        self.cache_dir = Path(cache_dir) if cache_dir else Path("cache")
        self.cache_dir.mkdir(exist_ok=True)

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 2 req/sec = 0.5s interval

    def _rate_limit(self):
        """Enforce rate limiting"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make HTTP request with rate limiting"""
        self._rate_limit()

        response = requests.get(self.base_url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        if data.get("status") != "1":
            # Handle "No records found" as empty result, not error
            message = data.get('message', '')
            if 'No records found' in message or message == 'NOTOK':
                return {"status": "1", "result": []}
            raise Exception(f"API error: {message if message else 'Unknown error'}")

        return data

    def get_contract_abi(self, address: str) -> Dict[str, Any]:
        """
        Fetch contract ABI from Routescan

        Returns:
            {
                "address": "0x...",
                "abi": [...],
                "name": "ContractName",
                "compiler_version": "v0.8.29+commit...",
                "optimization": true,
                "runs": 200
            }
        """
        cache_file = self.cache_dir / f"abi_{address.lower()}.json"

        # Check cache
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        # Fetch from API
        params = {
            "module": "contract",
            "action": "getabi",
            "address": address
        }

        data = self._make_request(params)
        abi = json.loads(data["result"])

        result = {
            "address": address.lower(),
            "abi": abi,
            "cached": False
        }

        # Cache result
        with open(cache_file, 'w') as f:
            json.dump(result, f, indent=2)

        return result

    def get_contract_source(self, address: str) -> Dict[str, Any]:
        """
        Fetch contract source code from Routescan

        Returns:
            {
                "address": "0x...",
                "source_code": "contract Foo { ... }",
                "contract_name": "PositionManager",
                "compiler_version": "v0.8.29+commit.ab55807c",
                "optimization_used": "1",
                "runs": "200",
                "constructor_arguments": "...",
                "evm_version": "Default",
                "library": "",
                "license_type": "MIT",
                "proxy": "0",
                "implementation": "",
                "swarm_source": ""
            }
        """
        cache_file = self.cache_dir / f"source_{address.lower()}.json"

        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address
        }

        data = self._make_request(params)
        result = data["result"][0] if data["result"] else {}

        result["address"] = address.lower()
        result["cached"] = False

        with open(cache_file, 'w') as f:
            json.dump(result, f, indent=2)

        return result

    def get_contract_creation(self, addresses: List[str], batch_size: int = 5) -> List[Dict[str, Any]]:
        """
        Get contract creation transaction and deployer

        Args:
            addresses: List of contract addresses
            batch_size: Max addresses per API call (default 5 to avoid errors)

        Returns:
            [{
                "contractAddress": "0x...",
                "contractCreator": "0x...",
                "txHash": "0x..."
            }, ...]
        """
        # If few addresses, try single request first
        if len(addresses) <= batch_size:
            cache_key = "_".join(sorted([a.lower() for a in addresses]))
            cache_file = self.cache_dir / f"creation_{cache_key[:32]}.json"

            if cache_file.exists():
                with open(cache_file) as f:
                    return json.load(f)

            params = {
                "module": "contract",
                "action": "getcontractcreation",
                "contractaddresses": ",".join(addresses)
            }

            try:
                data = self._make_request(params)
                result = data.get("result", [])

                with open(cache_file, 'w') as f:
                    json.dump(result, f, indent=2)

                return result
            except Exception as e:
                # If single request fails, fall through to batching
                print(f"  Single request failed ({e}), switching to batch mode...")

        # Batch requests
        all_results = []

        for i in range(0, len(addresses), batch_size):
            batch = addresses[i:i+batch_size]
            cache_key = "_".join(sorted([a.lower() for a in batch]))
            cache_file = self.cache_dir / f"creation_{cache_key[:32]}.json"

            if cache_file.exists():
                with open(cache_file) as f:
                    all_results.extend(json.load(f))
                continue

            params = {
                "module": "contract",
                "action": "getcontractcreation",
                "contractaddresses": ",".join(batch)
            }

            data = self._make_request(params)
            result = data.get("result", [])

            with open(cache_file, 'w') as f:
                json.dump(result, f, indent=2)

            all_results.extend(result)

        return all_results

    def get_logs(
        self,
        address: Optional[str] = None,
        topic0: Optional[str] = None,
        topic1: Optional[str] = None,
        from_block: int = 0,
        to_block: int = 99999999,
        page: int = 1,
        offset: int = 10000
    ) -> List[Dict[str, Any]]:
        """
        Get event logs with pagination support (single page)

        Use get_all_logs() for automatic pagination through all results.
        """
        params = {
            "module": "logs",
            "action": "getLogs",
            "fromBlock": from_block,
            "toBlock": to_block,
            "page": page,
            "offset": offset
        }

        if address:
            params["address"] = address
        if topic0:
            params["topic0"] = topic0
        if topic1:
            params["topic1"] = topic1

        data = self._make_request(params)
        return data.get("result", [])

    def get_all_logs(
        self,
        address: Optional[str] = None,
        topic0: Optional[str] = None,
        topic1: Optional[str] = None,
        from_block: int = 0,
        to_block: int = 99999999,
        offset: int = 10000
    ) -> List[Dict[str, Any]]:
        """
        Get ALL event logs by automatically paginating through results

        This is the recommended method for fetching events.

        Returns:
            List of event log dictionaries
        """
        # Generate cache key
        cache_parts = [
            f"addr_{address[:10] if address else 'all'}",
            f"t0_{topic0[:10] if topic0 else 'none'}",
            f"t1_{topic1[:10] if topic1 else 'none'}",
            f"fb_{from_block}",
            f"tb_{to_block}"
        ]
        cache_key = "_".join(cache_parts)
        cache_file = self.cache_dir / "logs" / f"{cache_key}.json"
        cache_file.parent.mkdir(exist_ok=True)

        # Check cache
        if cache_file.exists():
            with open(cache_file) as f:
                cached = json.load(f)
                print(f"  [Cache hit] Loaded {len(cached['events'])} events from cache")
                return cached['events']

        # Fetch all pages
        all_events = []
        page = 1

        print(f"  Fetching events (offset={offset})...")

        while True:
            events = self.get_logs(
                address=address,
                topic0=topic0,
                topic1=topic1,
                from_block=from_block,
                to_block=to_block,
                page=page,
                offset=offset
            )

            if not events:
                print(f"    Page {page}: No more events")
                break

            print(f"    Page {page}: {len(events)} events")
            all_events.extend(events)

            if len(events) < offset:
                # Last page
                break

            page += 1

        print(f"  Total: {len(all_events)} events")

        # Cache result
        with open(cache_file, 'w') as f:
            json.dump({
                "query": {
                    "address": address,
                    "topic0": topic0,
                    "topic1": topic1,
                    "from_block": from_block,
                    "to_block": to_block
                },
                "total_pages": page,
                "total_events": len(all_events),
                "events": all_events
            }, f)

        return all_events

    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction details"""
        params = {
            "module": "proxy",
            "action": "eth_getTransactionByHash",
            "txhash": tx_hash
        }

        data = self._make_request(params)
        return data.get("result", {})

    def get_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction receipt"""
        params = {
            "module": "proxy",
            "action": "eth_getTransactionReceipt",
            "txhash": tx_hash
        }

        data = self._make_request(params)
        return data.get("result", {})
