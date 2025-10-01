"""Tests for fill simulator."""

from __future__ import annotations

import pytest

from backtest.fill_simulator import FillSimulator, OHLCVBar


@pytest.fixture
def simulator() -> FillSimulator:
    """Create fill simulator with standard fees."""
    return FillSimulator(commission_rate=0.001, slippage_bps=5)


@pytest.fixture
def zero_cost_simulator() -> FillSimulator:
    """Create fill simulator with zero fees."""
    return FillSimulator(commission_rate=0.0, slippage_bps=0)


@pytest.fixture
def sample_bar() -> OHLCVBar:
    """Create sample OHLCV bar."""
    return OHLCVBar(
        open=100.0,
        high=102.0,
        low=98.0,
        close=101.0,
        volume=1000.0,
    )


# Market order tests


def test_market_buy_with_slippage(simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test market buy order applies positive slippage."""
    result = simulator.simulate_market_order("buy", 10.0, sample_bar)

    assert result.filled is True
    assert result.qty == 10.0
    # Close price: 101.0, slippage: 5 bps = 0.05%
    expected_fill_price = 101.0 * 1.0005
    assert abs(result.fill_price - expected_fill_price) < 1e-6
    # Commission: 10 * fill_price * 0.001
    expected_commission = 10.0 * expected_fill_price * 0.001
    assert abs(result.commission - expected_commission) < 1e-6


def test_market_sell_with_slippage(simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test market sell order applies negative slippage."""
    result = simulator.simulate_market_order("sell", 10.0, sample_bar)

    assert result.filled is True
    assert result.qty == 10.0
    # Close price: 101.0, slippage: 5 bps = 0.05%
    expected_fill_price = 101.0 * 0.9995
    assert abs(result.fill_price - expected_fill_price) < 1e-6
    # Commission: 10 * fill_price * 0.001
    expected_commission = 10.0 * expected_fill_price * 0.001
    assert abs(result.commission - expected_commission) < 1e-6


def test_market_order_zero_slippage(
    zero_cost_simulator: FillSimulator, sample_bar: OHLCVBar
) -> None:
    """Test market order with zero slippage fills at close."""
    result = zero_cost_simulator.simulate_market_order("buy", 10.0, sample_bar)

    assert result.filled is True
    assert result.fill_price == sample_bar.close
    assert result.commission == 0.0


# Limit order tests


def test_limit_buy_fills_when_low_crosses(simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test limit buy fills when bar low touches limit price."""
    # Bar low is 98.0, so limit at 98.5 should fill
    result = simulator.simulate_limit_order("buy", 10.0, 98.5, sample_bar)

    assert result.filled is True
    assert result.fill_price == 98.5  # Fill at limit
    assert result.qty == 10.0
    expected_commission = 10.0 * 98.5 * 0.001
    assert abs(result.commission - expected_commission) < 1e-6


def test_limit_buy_no_fill_when_price_too_high(
    simulator: FillSimulator, sample_bar: OHLCVBar
) -> None:
    """Test limit buy does not fill when price stays above limit."""
    # Bar low is 98.0, so limit at 97.0 should NOT fill
    result = simulator.simulate_limit_order("buy", 10.0, 97.0, sample_bar)

    assert result.filled is False
    assert result.fill_price == 0.0
    assert result.qty == 0.0
    assert result.commission == 0.0


def test_limit_sell_fills_when_high_crosses(simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test limit sell fills when bar high touches limit price."""
    # Bar high is 102.0, so limit at 101.5 should fill
    result = simulator.simulate_limit_order("sell", 10.0, 101.5, sample_bar)

    assert result.filled is True
    assert result.fill_price == 101.5  # Fill at limit
    assert result.qty == 10.0
    expected_commission = 10.0 * 101.5 * 0.001
    assert abs(result.commission - expected_commission) < 1e-6


def test_limit_sell_no_fill_when_price_too_low(
    simulator: FillSimulator, sample_bar: OHLCVBar
) -> None:
    """Test limit sell does not fill when price stays below limit."""
    # Bar high is 102.0, so limit at 103.0 should NOT fill
    result = simulator.simulate_limit_order("sell", 10.0, 103.0, sample_bar)

    assert result.filled is False
    assert result.fill_price == 0.0
    assert result.qty == 0.0
    assert result.commission == 0.0


def test_limit_buy_fills_at_exact_low(simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test limit buy fills when limit equals bar low."""
    # Bar low is 98.0
    result = simulator.simulate_limit_order("buy", 10.0, 98.0, sample_bar)

    assert result.filled is True
    assert result.fill_price == 98.0


def test_limit_sell_fills_at_exact_high(simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test limit sell fills when limit equals bar high."""
    # Bar high is 102.0
    result = simulator.simulate_limit_order("sell", 10.0, 102.0, sample_bar)

    assert result.filled is True
    assert result.fill_price == 102.0


# Edge cases


def test_zero_commission_baseline(zero_cost_simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test limit order with zero commission."""
    result = zero_cost_simulator.simulate_limit_order("buy", 10.0, 99.0, sample_bar)

    assert result.filled is True
    assert result.commission == 0.0


def test_large_slippage(sample_bar: OHLCVBar) -> None:
    """Test market order with large slippage."""
    # 100 bps = 1%
    large_slippage_sim = FillSimulator(commission_rate=0.001, slippage_bps=100)
    result = large_slippage_sim.simulate_market_order("buy", 10.0, sample_bar)

    expected_fill_price = 101.0 * 1.01  # 1% slippage
    assert abs(result.fill_price - expected_fill_price) < 1e-6


def test_fractional_quantity(simulator: FillSimulator, sample_bar: OHLCVBar) -> None:
    """Test limit order with fractional quantity."""
    result = simulator.simulate_limit_order("buy", 0.5, 99.0, sample_bar)

    assert result.filled is True
    assert result.qty == 0.5
    expected_commission = 0.5 * 99.0 * 0.001
    assert abs(result.commission - expected_commission) < 1e-9


def test_high_commission_rate(sample_bar: OHLCVBar) -> None:
    """Test market order with high commission."""
    # 5% commission
    high_commission_sim = FillSimulator(commission_rate=0.05, slippage_bps=0)
    result = high_commission_sim.simulate_market_order("buy", 10.0, sample_bar)

    expected_commission = 10.0 * 101.0 * 0.05
    assert abs(result.commission - expected_commission) < 1e-6
