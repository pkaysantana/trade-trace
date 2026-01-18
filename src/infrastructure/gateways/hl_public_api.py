import asyncio
import logging
from typing import List, Optional, Any
from decimal import Decimal

# Hyperliquid SDK imports
try:
    from hyperliquid.info import Info
    from hyperliquid.utils import constants
except ImportError:
    # Fallback for local testing without SDK installed
    Info = Any
    constants = Any
    logging.warning("Hyperliquid SDK not found. Install with: pip install hyperliquid-python-sdk")

# Internal imports (Assuming these exist based on your architecture)
from src.core.interfaces.datasource import IDataSource
from src.core.entities.trade import TradeResponse  # Assuming this entity exists

logger = logging.getLogger(__name__)

class HLPublicGateway(IDataSource):
    """
    Implementation of IDataSource for the Hyperliquid Public Info API.
    Uses the official Python SDK wrapped in asyncio threads for non-blocking execution.
    """

    def __init__(self, use_testnet: bool = False):
        """
        Initialize the Hyperliquid Info client.
        
        :param use_testnet: Boolean to toggle between Mainnet and Testnet.
        """
        api_url = constants.TESTNET_API_URL if use_testnet else constants.MAINNET_API_URL
        
        # 'skip_ws=True' is crucial here as we only need REST endpoints for history
        # and don't want to spawn background WS threads for this worker.
        self.info = Info(base_url=api_url, skip_ws=True)
        logger.info(f"HLPublicGateway initialized. URL: {api_url}")

    async def get_trades(
        self, 
        user: str, 
        coin: str, 
        start_time: Optional[int] = None, 
        end_time: Optional[int] = None
    ) -> List[TradeResponse]:
        """
        Fetches historical trades using the 'userFillsByTime' endpoint.
        """
        # Default to epoch 0 if no start time provided (fetch all history)
        safe_start_time = start_time if start_time is not None else 0
        
        payload = {
            "type": "userFillsByTime",
            "user": user,
            "coin": coin,
            "startTime": safe_start_time
        }

        if end_time:
            payload["endTime"] = end_time

        try:
            # The SDK is synchronous, so we run it in a separate thread to stay async
            raw_fills = await asyncio.to_thread(self.info.post, "/info", payload)
            
            return self._map_fills_to_trades(raw_fills)

        except Exception as e:
            logger.error(f"Failed to fetch trades for {user}: {str(e)}")
            # In production, you might want to raise a custom DataSourceException here
            return []

    def _map_fills_to_trades(self, fills: List[dict]) -> List[TradeResponse]:
        """
        Maps raw Hyperliquid JSON fills to your internal Domain Entity.
        """
        trades = []
        for fill in fills:
            try:
                # Map 'B' (Bid) to Long, 'A' (Ask) to Short for simplified direction
                # Note: This refers to the side of the taker order, not necessarily position impact.
                # Your position reconstruction logic handles the net_size math.
                side = "Long" if fill.get("side") == "B" else "Short"
                
                # Builder attribution parsing
                # Hyperliquid returns builder info in the 'builder' field if present
                builder_info = fill.get("builder", None)
                builder_address = None
                
                if isinstance(builder_info, dict):
                    builder_address = builder_info.get("b")  # 'b' key holds the address
                elif isinstance(builder_info, str):
                    builder_address = builder_info # Legacy handling

                trade = TradeResponse(
                    time_ms=fill.get("time"),
                    coin=fill.get("coin"),
                    side=side,
                    sz=float(fill.get("sz", 0)),
                    px=float(fill.get("px", 0)),
                    fee=float(fill.get("fee", 0)),
                    closed_pnl=float(fill.get("closedPnl", 0)),
                    builder_id=builder_address,
                    hash=fill.get("hash")
                )
                trades.append(trade)
            except Exception as map_err:
                logger.warning(f"Skipping malformed trade: {map_err}")
                continue
                
        # API returns most recent first; sort by time ASC for easier position reconstruction
        trades.sort(key=lambda x: x.time_ms)
        return trades

    async def get_active_users(self, coin: str, start_time: int) -> List[str]:
        """
        Fetches active users. For now, fetches allMids to verify connectivity 
        and returns a focused list of test users as requested.
        """
        try:
            # The user requested to use allMids.
            # Note: allMids returns price data, not user lists. 
            # This call confirms API connectivity.
            _ = await asyncio.to_thread(self.info.post, "/info", {"type": "allMids"})
        except Exception as e:
            logger.warning(f"Failed to fetch allMids: {e}")

        # Return the specific test users requested for Phase 3
        return [
            "0x31ca8395cf837de08b24da3f660e77761dfb974b", # Test user
            "0xdfc7170a41764724040e34c9c11816f19934145c", # Whale
            "0x2c98d6693a980287754b51a5113d092d64f0b09d"
        ]

    async def get_historical_equity(self, user: str, timestamp: int) -> float:
        """
        STUB: Historical equity is hard to query perfectly without a full archive node.
        For now, we return a default to prevent division-by-zero in ROI calc.
        """
        # In a real implementation, you might snapshot 'clearinghouseState' daily
        return 1000.0

    async def get_user_deposits(
        self, 
        user: str, 
        from_ms: Optional[int] = None, 
        to_ms: Optional[int] = None
    ) -> List[dict]:
        """
        Fetches user deposit/withdrawal history using userNonFundingLedgerUpdates.
        This enables fair competition filtering by tracking capital inflows.
        """
        from src.core.entities.deposit import DepositResponse
        
        payload = {
            "type": "userNonFundingLedgerUpdates",
            "user": user
        }
        
        try:
            raw_updates = await asyncio.to_thread(self.info.post, "/info", payload)
            
            deposits = []
            for update in raw_updates:
                try:
                    # Filter for deposit/withdrawal types
                    delta = update.get("delta", {})
                    update_type = delta.get("type", "")
                    
                    # Include deposits, withdrawals, and transfers
                    if update_type in ["deposit", "withdraw", "internalTransfer"]:
                        timestamp = update.get("time", 0)
                        
                        # Apply time filters
                        if from_ms and timestamp < from_ms:
                            continue
                        if to_ms and timestamp > to_ms:
                            continue
                        
                        amount = float(delta.get("usdc", 0))
                        if update_type == "withdraw":
                            amount = -abs(amount)  # Withdrawals are negative
                        
                        deposits.append(DepositResponse(
                            timestamp_ms=timestamp,
                            asset="USDC",
                            amount=amount,
                            tx_hash=delta.get("hash")
                        ))
                except Exception as e:
                    logger.warning(f"Skipping malformed deposit update: {e}")
                    continue
            
            # Sort by timestamp
            deposits.sort(key=lambda x: x.timestamp_ms)
            return deposits
            
        except Exception as e:
            logger.error(f"Failed to fetch deposits for {user}: {e}")
            return []

    async def get_current_position(self, user: str, coin: str) -> Optional[dict]:
        """
        Fetches current open position for risk metrics (liqPx, marginUsed).
        Uses clearinghouseState endpoint.
        """
        try:
            state = await asyncio.to_thread(
                self.info.post, "/info", 
                {"type": "clearinghouseState", "user": user}
            )
            
            # Find position for the specified coin
            asset_positions = state.get("assetPositions", [])
            for asset_pos in asset_positions:
                pos = asset_pos.get("position", {})
                if pos.get("coin") == coin:
                    return {
                        "netSize": float(pos.get("szi", 0)),
                        "entryPx": float(pos.get("entryPx", 0)),
                        "liqPx": float(pos.get("liquidationPx", 0)) if pos.get("liquidationPx") else None,
                        "unrealizedPnl": float(pos.get("unrealizedPnl", 0)),
                        "marginUsed": float(pos.get("marginUsed", 0)),
                        "leverage": float(pos.get("leverage", {}).get("value", 1))
                    }
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch position for {user}/{coin}: {e}")
            return None

    async def get_account_value(self, user: str) -> float:
        """
        Fetches current account value for margin calculations.
        """
        try:
            state = await asyncio.to_thread(
                self.info.post, "/info",
                {"type": "clearinghouseState", "user": user}
            )
            
            margin_summary = state.get("marginSummary", {})
            return float(margin_summary.get("accountValue", 1000))
            
        except Exception as e:
            logger.error(f"Failed to fetch account value for {user}: {e}")
            return 1000.0

    async def get_mid_price(self, coin: str) -> float:
        """
        Fetches current mid price for a coin.
        """
        try:
            mids = await asyncio.to_thread(
                self.info.post, "/info",
                {"type": "allMids"}
            )
            return float(mids.get(coin, 0))
        except Exception as e:
            logger.error(f"Failed to fetch mid price for {coin}: {e}")
            return 0.0
