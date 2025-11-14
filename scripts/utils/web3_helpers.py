"""
Web3 helpers for TradeSta verification

Provides functions for:
- RPC calls (eth_call for reading contract state)
- Event decoding
- Address utilities
"""

from web3 import Web3
from eth_abi import decode
from typing import Any, List, Dict, Optional
import json

class Web3Helper:
    """Helper class for Web3/RPC interactions"""

    def __init__(self, rpc_url: str = None):
        self.rpc_url = rpc_url or "https://api.avax.network/ext/bc/C/rpc"
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        if not self.w3.is_connected():
            raise Exception(f"Failed to connect to RPC: {self.rpc_url}")

    def get_latest_block(self) -> int:
        """Get latest block number"""
        return self.w3.eth.block_number

    def call_contract(
        self,
        contract_address: str,
        function_signature: str,
        args: List[Any] = None,
        block: str = "latest"
    ) -> Any:
        """
        Call a contract view function using eth_call

        Args:
            contract_address: Contract address
            function_signature: e.g., "hasRole(bytes32,address)"
            args: Function arguments
            block: Block number or "latest"

        Returns:
            Decoded return value
        """
        # Encode function call
        if args is None:
            args = []

        # Create function selector
        selector = Web3.keccak(text=function_signature)[:4].hex()

        # Encode arguments (simplified - would need full ABI encoding for complex types)
        data = selector

        # Make eth_call
        result = self.w3.eth.call({
            "to": contract_address,
            "data": data
        }, block)

        return result

    def has_role(
        self,
        contract_address: str,
        role: str,
        account: str
    ) -> bool:
        """
        Check if account has role in OpenZeppelin AccessControl contract

        Args:
            contract_address: Contract with AccessControl
            role: Role hash (32 bytes hex)
            account: Address to check

        Returns:
            True if account has role
        """
        # Function signature: hasRole(bytes32,address) returns (bool)
        function_sig = "hasRole(bytes32,address)"
        selector = Web3.keccak(text=function_sig)[:4]

        # Encode parameters
        role_bytes = bytes.fromhex(role[2:] if role.startswith('0x') else role)
        account_bytes = bytes.fromhex(account[2:] if account.startswith('0x') else account.lower())

        # Pad to 32 bytes
        role_padded = role_bytes.rjust(32, b'\x00')
        account_padded = account_bytes.rjust(32, b'\x00')

        data = selector + role_padded + account_padded

        try:
            result = self.w3.eth.call({
                "to": contract_address,
                "data": "0x" + data.hex()
            })

            # Decode bool result
            return int.from_bytes(result, byteorder='big') == 1

        except Exception as e:
            print(f"  Error checking role: {e}")
            return False

    def is_whitelisted(
        self,
        contract_address: str,
        account: str
    ) -> bool:
        """
        Check if account is whitelisted in MarketRegistry

        Function signature: isWhitelisted(address) returns (bool)
        """
        function_sig = "isWhitelisted(address)"
        selector = Web3.keccak(text=function_sig)[:4]

        account_bytes = bytes.fromhex(account[2:] if account.startswith('0x') else account.lower())
        account_padded = account_bytes.rjust(32, b'\x00')

        data = selector + account_padded

        try:
            result = self.w3.eth.call({
                "to": contract_address,
                "data": "0x" + data.hex()
            })

            return int.from_bytes(result, byteorder='big') == 1

        except Exception as e:
            print(f"  Error checking whitelist: {e}")
            return False

    def decode_address_from_topic(self, topic: str) -> str:
        """
        Decode address from event topic (32 bytes)

        Args:
            topic: 32-byte hex string (0x + 64 chars)

        Returns:
            20-byte address (0x + 40 chars)
        """
        if not topic or len(topic) != 66:  # 0x + 64 hex chars
            return None

        # Address is last 20 bytes (40 hex chars)
        address = "0x" + topic[-40:]
        return Web3.to_checksum_address(address)

    def decode_uint256_from_data(self, data: str, offset: int = 0) -> int:
        """
        Decode uint256 from event data field

        Args:
            data: Hex string of event data
            offset: Byte offset (0, 32, 64, ...)

        Returns:
            Integer value
        """
        if not data or data == "0x":
            return None

        data_bytes = bytes.fromhex(data[2:])  # Remove 0x

        start = offset
        end = offset + 32

        if end > len(data_bytes):
            return None

        value_bytes = data_bytes[start:end]
        return int.from_bytes(value_bytes, byteorder='big')

    def decode_int256_from_data(self, data: str, offset: int = 0) -> int:
        """
        Decode int256 (signed) from event data field using two's complement

        Args:
            data: Hex string of event data
            offset: Byte offset (0, 32, 64, ...)

        Returns:
            Signed integer value
        """
        unsigned = self.decode_uint256_from_data(data, offset)
        if unsigned is None:
            return None

        # Two's complement for 256-bit signed integer
        if unsigned >= 2**255:
            return unsigned - 2**256
        else:
            return unsigned

    def decode_bool_from_data(self, data: str, offset: int = 0) -> bool:
        """Decode bool from event data field"""
        value = self.decode_uint256_from_data(data, offset)
        return value == 1 if value is not None else None

    @staticmethod
    def keccak256(text: str) -> str:
        """Calculate keccak256 hash of text"""
        return Web3.keccak(text=text).hex()

    @staticmethod
    def to_checksum(address: str) -> str:
        """Convert address to checksum format"""
        return Web3.to_checksum_address(address)

    @staticmethod
    def is_address(value: str) -> bool:
        """Check if string is valid address"""
        return Web3.is_address(value)


# Event signature constants (for reference)
EVENT_SIGNATURES = {
    # PositionManager
    "PositionCreated": "0x52055f6ec9a38bd7aced9d289a234dc894a9537b635ebca189454066a91c7a36",
    "PositionClosed": "0x258651cd24729ce9fc1923a56102c05cf3e823b253bcf4a281216a12977f2e21",
    "PositionLiquidated": "0xf7b7ee46cb229f84d395ae4c43aa0be56002cb98c70620d034c4260f466b660e",
    "CollateralSeized": "0xced097b0da570807e22b200429af46d69228c4b438d8e9a2d27856dbbacc18b7",

    # Orders
    "LimitOrderCreated": "0x5511d235fbfb12958d439f034ca9a0738e274c73a692b46af3b83689551d19f1",
    "LimitOrderExecuted": "0xc85d1f102cb496b276a9b66500e11f48ac0d3572affca759865380f51c813e88",
    "LimitOrderCancelled": "0x421bffbe425e8b84fdaea1053afe0da97a6e8d858c1eb00c5b44d91e26b775db",

    # Pyth Oracle
    "PriceFeedUpdate": "0xd06a6b7f4918494b37f3069f1e082a962e3cb0d84e0280164427ad6483c2217c",

    # OpenZeppelin AccessControl
    "RoleGranted": "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d",
    "RoleRevoked": "0xf6391f5c32d9c69d2a47ea670b442974b53935d1edc7fd64eb21e047a839171b",
}

# OpenZeppelin role constants
ROLES = {
    "DEFAULT_ADMIN_ROLE": "0x0000000000000000000000000000000000000000000000000000000000000000",
    "ADMIN_ROLE": Web3.keccak(text="ADMIN_ROLE").hex(),
}
