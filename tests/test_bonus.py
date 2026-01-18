"""
Tests for Bonus Features - Hyperliquid Challenge

Tests the high-impact bonus endpoints:
- /v1/deposits
- /v1/pnl (portfolio mode)
- /v1/positions/current
- /v1/leaderboard/fair
"""
import pytest
from httpx import AsyncClient, ASGITransport
from src.api.main import app

TEST_USER = "0x31ca8395cf837de08b24da3f660e77761dfb974b"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_deposits_endpoint(client: AsyncClient):
    """Test /v1/deposits returns expected structure."""
    resp = await client.get(f"/v1/deposits?user={TEST_USER}")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "total_deposits" in data
    assert "total_withdrawals" in data
    assert "net_transfers" in data
    assert "deposit_count" in data
    assert "withdrawal_count" in data
    assert "deposits" in data
    assert isinstance(data["deposits"], list)


@pytest.mark.anyio
async def test_deposits_with_time_filter(client: AsyncClient):
    """Test /v1/deposits with time range filter."""
    resp = await client.get(
        f"/v1/deposits?user={TEST_USER}&fromMs=1700000000000&toMs=1710000000000"
    )
    assert resp.status_code == 200
    
    data = resp.json()
    # Verify all deposits are within range
    for deposit in data["deposits"]:
        assert deposit["timestamp_ms"] >= 1700000000000
        assert deposit["timestamp_ms"] <= 1710000000000


@pytest.mark.anyio
async def test_pnl_single_coin(client: AsyncClient):
    """Test /v1/pnl for single coin."""
    resp = await client.get(f"/v1/pnl?user={TEST_USER}&coin=BTC")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "user" in data
    assert "coin" in data
    assert "realized_pnl" in data
    assert "fees" in data
    assert "net_pnl" in data


@pytest.mark.anyio
async def test_pnl_portfolio(client: AsyncClient):
    """Test /v1/pnl for portfolio aggregation."""
    resp = await client.get(f"/v1/pnl?user={TEST_USER}&coin=portfolio")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "user" in data
    assert "total_realized_pnl" in data
    assert "total_unrealized_pnl" in data
    assert "total_fees" in data
    assert "net_pnl" in data
    assert "coins" in data
    assert isinstance(data["coins"], dict)


@pytest.mark.anyio
async def test_pnl_no_coin_defaults_to_portfolio(client: AsyncClient):
    """Test /v1/pnl without coin parameter defaults to portfolio."""
    resp = await client.get(f"/v1/pnl?user={TEST_USER}")
    assert resp.status_code == 200
    
    data = resp.json()
    # Should return portfolio structure
    assert "total_realized_pnl" in data


@pytest.mark.anyio
async def test_current_position(client: AsyncClient):
    """Test /v1/positions/current returns risk metrics."""
    resp = await client.get(f"/v1/positions/current?user={TEST_USER}&coin=BTC")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "user" in data
    assert "coin" in data
    assert "hasPosition" in data
    
    if data["hasPosition"]:
        assert "netSize" in data
        assert "entryPx" in data
        assert "liqPx" in data
        assert "leverage" in data
        assert "marginUsedPct" in data


@pytest.mark.anyio
async def test_fair_leaderboard(client: AsyncClient):
    """Test /v1/leaderboard/fair with deposit adjustment."""
    resp = await client.get("/v1/leaderboard/fair?coin=BTC")
    assert resp.status_code == 200
    
    data = resp.json()
    assert isinstance(data, list)
    
    if len(data) > 0:
        entry = data[0]
        assert "rank" in entry
        assert "user" in entry
        assert "pnl" in entry
        assert "roi" in entry
        assert "starting_equity" in entry
        assert "deposits_during_comp" in entry
        assert "effective_capital" in entry
        assert "had_mid_comp_deposits" in entry


@pytest.mark.anyio
async def test_fair_leaderboard_with_time_range(client: AsyncClient):
    """Test /v1/leaderboard/fair with competition time range."""
    resp = await client.get(
        "/v1/leaderboard/fair?coin=BTC&fromMs=1700000000000&toMs=1710000000000"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_fair_leaderboard_roi_sorting(client: AsyncClient):
    """Test /v1/leaderboard/fair sorts by ROI when requested."""
    resp = await client.get("/v1/leaderboard/fair?coin=BTC&metric=roi")
    assert resp.status_code == 200
    
    data = resp.json()
    if len(data) >= 2:
        # Verify descending ROI order
        assert data[0]["roi"] >= data[1]["roi"]


@pytest.mark.anyio
async def test_health_still_works(client: AsyncClient):
    """Verify health endpoint still works after bonus additions."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.anyio
async def test_existing_endpoints_still_work(client: AsyncClient):
    """Verify existing endpoints weren't broken by bonus additions."""
    # Test trades
    resp = await client.get(f"/v1/trades?user={TEST_USER}&coin=BTC")
    assert resp.status_code == 200
    
    # Test positions history
    resp = await client.get(f"/v1/positions/history?user={TEST_USER}&coin=BTC")
    assert resp.status_code == 200
    
    # Test leaderboard
    resp = await client.get("/v1/leaderboard?coin=BTC")
    assert resp.status_code == 200
