from src.core.sepa_backtest import SepaBacktest, SepaBacktestConfig


def _bars(count=280):
    bars = []
    for index in range(count):
        close = 100 + index * 0.15
        bars.append({"date": f"2025-01-{index + 1:03d}", "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 100})
    return bars


def _make_vcp(bars):
    """Create the same auditable four-contraction VCP used by rule v2."""
    for width, volume, start in ((8, 500, 232), (5, 320, 244), (3, 180, 256), (1, 80, 268)):
        for index in range(start, start + 12):
            close = bars[index]["close"]
            bars[index].update(high=close + width, low=close - width, volume=volume)


def test_blocks_incomplete_ohlcv():
    result = SepaBacktest.run([{"date": "2025-01-01", "open": 1}])
    assert result["validation_status"] == "blocked"
    assert "缺少" in result["reason"]


def test_enters_only_on_next_session_and_includes_costs():
    bars = _bars()
    _make_vcp(bars)
    bars[279].update(close=144.6, high=144.7, low=143.5, volume=800)
    bars.append({"date": "2025-01-281", "open": 142.5, "high": 166, "low": 142, "close": 165, "volume": 100})
    result = SepaBacktest.run(bars, SepaBacktestConfig(max_holding_bars=1))
    assert result["validation_status"] == "completed"
    assert result["trades"]
    trade = result["trades"][-1]
    assert trade["entry_date"] > trade["signal_date"]
    assert trade["entry_price"] > 142.5


def test_same_day_stop_and_target_uses_conservative_stop():
    bars = _bars()
    _make_vcp(bars)
    bars[279].update(close=144.6, high=144.7, low=143.5, volume=800)
    bars.append({"date": "2025-01-281", "open": 142.5, "high": 180, "low": 120, "close": 150, "volume": 100})
    result = SepaBacktest.run(bars)
    assert result["trades"][-1]["exit_reason"] == "stop_loss"
