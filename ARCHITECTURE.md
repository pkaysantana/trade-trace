# ARCHITECTURE.md

## Trade Ledger & Leaderboard System Architecture

This document outlines the architecture for a high-frequency trade ledger, position reconstruction engine, and "Builder-Only" leaderboard for Hyperliquid. The system is designed to be agnostic to the underlying data source (Hyperliquid API vs. Insilico) using a Repository Pattern, while enforcing strict state reconstruction to track user performance and platform attribution.

---

## 1. System Overview & Data Flow

The system operates as a pipeline: ingestion, buffering, state reconstruction, and persistence. Raw trade data is transformed into "state snapshots" (positions) which are then aggregated into leaderboards.

### High-Level Data Flow Diagram

```ascii
[ Hyperliquid API ]      [ Insilico / Mock ]
        |                        |
        +----( IDataSource Interface )----+
                        |
              [ Ingestor Service ]
                        |
            (Polls/WS for raw trades)
                        |
               [ Raw Event Buffer ]
          (Redis Stream / NATS Jetstream)
                        |
                        v
             [ Transformer Worker ]
      (Runs Position State Machine & Taint Logic)
                        |
        +---------------+---------------+
        |                               |
        v                               v
[ Postgres (TimescaleDB) ]        [ Redis ]
 - Table: trades                   - Hot Position State
 - Table: position_snapshots       - Real-time PnL
 - Table: leaderboard_cache
        |
        v
    [ API Layer ]
 (REST: /trades, /leaderboard)
```

**Key Connections:**
*   **Ingestor:** Uses the `IDataSource` abstraction to fetch data.
*   **Transformer:** Reads raw trades, applies the **Position Reconstruction Algorithm**, determines **Taint Status**, and writes to **Postgres**.
*   **API:** Queries `leaderboard_cache` and `position_snapshots` to serve users.

---

## 2. Datasource Abstraction (Repository Pattern)

To ensure the business logic remains decoupled from specific Hyperliquid SDKs, we employ a Provider Pattern. This allows swapping data sources (e.g., moving from Hyperliquid Public API to Insilico in the future) without changing core logic.

### Interface Definition
The core logic depends *only* on this contract:

```python
# interfaces/IDataSource.py

from abc import ABC, abstractmethod
from typing import List
from decimal import Decimal
from entities.trade import TradeObject

class IDataSource(ABC):
    @abstractmethod
    def get_trades(self, user: str, coin: str, start_time: int, end_time: int) -> List[TradeObject]:
        """Returns normalized objects: {timestamp, side, size, price, fee, builder_id, closed_pnl}"""
        pass

    @abstractmethod
    def get_active_users(self, coin: str, start_time: int) -> List[str]:
        """Discover users active in a specific window"""
        pass

    @abstractmethod
    def get_historical_equity(self, user: str, timestamp: int) -> Decimal:
        """Returns account value for ROE normalization"""
        pass

# entities/trade.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class TradeObject:
    timestamp: int
    side: str         # "Long" or "Short"
    size: float
    price: float
    fee: float
    builder_id: Optional[str] = None
    closed_pnl: float = 0.0

# __init__.py files (empty):

# interfaces/__init__.py
# entities/__init__.py
```

### Dependency Injection
The application entry point binds the specific implementation.
*   **Current:** `HLPublicDataSource` (Calls userFillsByTime, maps JSON to TradeObject).
*   **Future:** `InsilicoDataSource` (SQL/WS connection).

---

## 3. Position Reconstruction & State Machine

Hyperliquid provides raw trade streams, not historical position states. We must reconstruct the ledger chronologically. A "Position" is defined as a sequence of trades starting from a `net_size` of 0 and ending at 0.

### The Zero-Point Algorithm
The transformer processes trades to calculate the Weighted Average Entry Price and Realized PnL.

**Logic Rules:**
1.  **Increasing Position:** Update price using weighted average.
2.  **Decreasing Position:** Price stays "sticky" (does not change).
3.  **Flipping (Long -> Short):** The "excess" size starts a new position at the new trade price.
4.  **Zero Point:** If `net_size` returns to 0, reset average entry and taint status.

### Pseudocode

```python
# src/core/entities/position.py

from dataclasses import dataclass

@dataclass
class PositionState:
    net_size: float
    avg_entry_px: float
    is_tainted: bool
    timestamp: int

# src/core/use_cases/position_reconstructor.py

from ..entities.position import PositionState
from ..entities.trade import TradeObject

def signs_match(a: float, b: float) -> bool:
    # Returns True if a and b have the same nonzero sign
    return (a > 0 and b > 0) or (a < 0 and b < 0)

def check_taint(current_state: PositionState, trade: TradeObject) -> bool:
    # Stub: always return False for now
    return False

def process_trade(current_state: PositionState, trade: TradeObject) -> PositionState:
    # 1. Determine Signed Sizes
    prev_sz = current_state.net_size
    trade_sz = trade.size if trade.side == "Long" else -trade.size
    new_sz = prev_sz + trade_sz

    # 2. Check Taint (See Section 4)
    is_tainted = check_taint(current_state, trade)

    # 3. Calculate Average Entry Price
    if prev_sz == 0:
        # New Position
        new_avg_px = trade.price
    elif signs_match(prev_sz, trade_sz):
        # Increasing: Weighted Average
        total_cost = (abs(prev_sz) * current_state.avg_entry_px) + (abs(trade_sz) * trade.price)
        new_avg_px = total_cost / abs(new_sz)
    elif abs(trade_sz) > abs(prev_sz):
        # Flipping: Price resets to current trade price
        new_avg_px = trade.price
        # Note: Taint logic might reset here depending on the specific flip
    else:
        # Reducing: Price stays constant
        new_avg_px = current_state.avg_entry_px

    # 4. Handle Zero Reset
    if new_sz == 0:
        new_avg_px = 0
        is_tainted = False

    return PositionState(
        net_size=new_sz,
        avg_entry_px=new_avg_px,
        is_tainted=is_tainted,
        timestamp=trade.timestamp
    )
```

---

## 4. Builder-Only Taint Tracking

To run a "Builder-Only" competition, we must exclude users who hedge or trade via other platforms (e.g., Hyperliquid UI). We use a "Taint" flag that persists for the duration of a position lifecycle.

### Taint Logic
A position is "Clean" only if **every** trade within that lifecycle (0 $\to$ 0) is attributed to our builder ID.

**Attribution Heuristic:**
1.  Check `trade.builder_address`. If it matches `TARGET_BUILDER`, it is valid.
2.  **Fallback:** If `builder_address` is missing but `builderFee > 0`, assume it is a competitor (non-builder trades usually have 0 fee on the UI, but paid builder trades always show fees).

### Taint Pseudocode

```python
def check_taint(current_state, incoming_trade):
    TARGET_BUILDER = "0xMyBuilderAddress..."

    # 1. If already tainted, it stays tainted until position closes (size 0)
    if current_state.is_tainted:
        return True

    # 2. If incoming trade is NOT ours, taint the active position
    if incoming_trade.builder_id != TARGET_BUILDER:
        # Only taint if a position is actually open or opening
        if current_state.net_size != 0 or incoming_trade.sz != 0:
            return True

    return False
```

---

## 5. PnL & Leaderboard Calculation

The leaderboard aggregates the persisted `trades` and `position_snapshots`. It must filter out "Tainted" lifecycles entirely.

### Formulas

1.  **Realized PnL:** $\sum (closed\_pnl) - \sum (fees)$.
2.  **Effective Capital (Capped):**
    $$EffectiveCap = \min(Equity_{start}, Cap_{max})$$
    *Prevents low-balance accounts (e.g., $10) from having 10,000% ROE.*
3.  **Return % (ROE):**
    $$ROE = \frac{RealizedPnL}{EffectiveCap} \times 100$$

### Aggregation & Filtering Logic (SQL)
The connection between **Position Reconstruction** and **Leaderboard** happens here: The leaderboard query checks the `position_snapshots` table. If *any* snapshot in a lifecycle was marked `is_tainted`, that entire lifecycle's PnL is excluded from the ranking.

---

## 6. Database Schema

We use PostgreSQL (optionally with TimescaleDB) to balance write-heavy ingestion and complex analytical reads.

### A. `trades` (Immutable Ledger)
*Source of Truth for all executions.*

| Column | Type | Indexing | Purpose |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT (PK) | | Unique ID |
| `user_address` | CHAR(42) | **(user, coin, time DESC)** | History Fetch |
| `coin` | VARCHAR(12) | | Asset Symbol |
| `sz` | DECIMAL | | Size (Signed) |
| `px` | DECIMAL | | Execution Price |
| `closed_pnl` | DECIMAL | | Raw PnL from API |
| `fee` | DECIMAL | | Fees paid |
| `builder_id` | CHAR(42) | **(builder_id, time)** | Attribution |
| `time_ms` | BIGINT | | Timestamp |
| `lifecycle_id` | UUID | | Groups 0-to-0 trades |

### B. `position_snapshots` (State History)
*Derived from the Transformer/Worker.*

| Column | Type | Indexing | Purpose |
| :--- | :--- | :--- | :--- |
| `id` | SERIAL (PK) | | |
| `trade_id` | BIGINT (FK) | | Link to trigger trade |
| `user_address` | CHAR(42) | | |
| `net_size` | DECIMAL | | Current exposure |
| `avg_entry_px` | DECIMAL | | Current cost basis |
| `is_tainted` | BOOLEAN | **(coin, tainted, lifecycle)** | **Leaderboard Filter** |
| `lifecycle_id` | UUID | | Groups 0-to-0 trades |

### C. `leaderboard_cache` (Materialized View)
*Pre-computed rankings for API speed.*

| Column | Type | Purpose |
| :--- | :--- | :--- |
| `rank_id` | SERIAL | Rank position |
| `user_address` | CHAR(42) | |
| `total_pnl` | DECIMAL | Aggregated Profit |
| `return_pct` | DECIMAL | Calculated ROE |
| `is_clean` | BOOLEAN | True if 0 tainted lifecycles |
| `as_of` | TIMESTAMP | Cache freshness |

---

## 7. Project Folder Structure

Below is the exact folder structure as specified above. 
Empty `__init__.py` files are included to ensure proper Python package structure.

```
/src/
  __init__.py

  /core/
    __init__.py
    /entities/
      __init__.py
    /use_cases/
      __init__.py
    /interfaces/
      __init__.py

  /infrastructure/
    __init__.py
    /gateways/
      __init__.py
      hl_public_api.py
      insilico_api.py
      local_mock.py
    /persistence/
      __init__.py
      postgres_repo.py
      redis_cache.py

  /workers/
    __init__.py
    ingestor.py
    transformer.py

  /api/
    __init__.py
    main.py
    routes.py
```

_Note: You should create these folders and files in your project root. All `__init__.py` files can be empty. Implementation files (e.g. `hl_public_api.py`, `main.py`) should be created as empty files if you are scaffolding the project directory structure._