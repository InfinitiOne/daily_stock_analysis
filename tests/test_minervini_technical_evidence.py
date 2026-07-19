import pandas as pd

from src.stock_analyzer import StockTrendAnalyzer

# Regression coverage for the deterministic Minervini evidence payload.

def _rising_vcp_bars():
    bars = []
    for index in range(280):
        close = 100 + index * 0.5
        bars.append(
            {
                "date": f"2025-{index // 28 + 1:02d}-{index % 28 + 1:02d}",
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 400,
            }
        )
    for width, volume, start in ((8, 500, 232), (5, 320, 244), (3, 180, 256), (1, 80, 268)):
        for index in range(start, start + 12):
            close = bars[index]["close"]
            bars[index].update(high=close + width, low=close - width, volume=volume)
    return pd.DataFrame(bars)


def test_minervini_evidence_exposes_stage_vcp_and_prices():
    analyzer = StockTrendAnalyzer()
    evidence = analyzer._build_weekly_technical_evidence(analyzer._calculate_mas(_rising_vcp_bars()))

    assert evidence["stage"] == 2
    assert evidence["trend_template"]["pass_count"] == 6
    assert evidence["vcp"] == "VCP 候選"
    assert evidence["vcp_contraction_count"] >= 2
    assert len(evidence["vcp_contractions"]) == 4
    assert evidence["pivot_buy_zone_low"] == evidence["pivot_price"]
    assert evidence["pivot_buy_zone_high"] > evidence["pivot_price"]
    assert evidence["pivot_structural_stop"] < evidence["pivot_price"]
    assert evidence["sepa_rating"] in {"A+", "A", "A-", "B+", "B", "C"}


def test_declining_long_term_trend_is_stage_four():
    bars = _rising_vcp_bars().iloc[:252].copy()
    bars["close"] = list(reversed(bars["close"].tolist()))
    bars["open"] = bars["close"]
    bars["high"] = bars["close"] + 1
    bars["low"] = bars["close"] - 1

    analyzer = StockTrendAnalyzer()
    evidence = analyzer._build_weekly_technical_evidence(analyzer._calculate_mas(bars))

    assert evidence["stage"] == 4
    assert evidence["stage_label"] == "Stage 4 下降期"
