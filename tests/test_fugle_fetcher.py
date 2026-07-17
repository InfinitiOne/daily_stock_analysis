# -*- coding: utf-8 -*-

from data_provider.fugle_fetcher import FugleFetcher


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, headers, params, timeout):
        self.calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return self.response


def test_fugle_daily_candles_normalize_to_jeac_contract():
    session = FakeSession(FakeResponse({"data": [
        {"date": "2026-07-15", "open": 100, "high": 103, "low": 99, "close": 102, "volume": 1000, "turnover": 102000},
        {"date": "2026-07-16", "open": 102, "high": 105, "low": 101, "close": 104, "volume": 1200, "turnover": 124800},
    ]}))
    fetcher = FugleFetcher(api_key="test-key", session=session)

    frame = fetcher.get_daily_data("2330.TW", start_date="2026-07-15", end_date="2026-07-16")

    assert list(frame["code"]) == ["2330.TW", "2330.TW"]
    assert list(frame["amount"]) == [102000, 124800]
    assert round(frame.iloc[-1]["pct_chg"], 2) == round((104 - 102) / 102 * 100, 2)
    assert session.calls[0]["headers"]["X-API-KEY"] == "test-key"
    assert session.calls[0]["params"]["timeframe"] == "D"


def test_fugle_realtime_quote_is_taiwan_only_and_uses_twd():
    session = FakeSession(FakeResponse({"data": {
        "name": "台積電",
        "lastPrice": 1050,
        "previousClose": 1030,
        "change": 20,
        "changePercent": 1.94,
        "openPrice": 1035,
        "highPrice": 1060,
        "lowPrice": 1030,
        "lastUpdated": 1780000000000,
        "total": {"tradeVolume": 3000, "tradeValue": 3150000},
    }}))
    fetcher = FugleFetcher(api_key="test-key", session=session)

    quote = fetcher.get_realtime_quote("2330.TW")

    assert quote is not None
    assert quote.source.value == "fugle"
    assert quote.market == "tw"
    assert quote.currency == "TWD"
    assert quote.volume == 3000
    assert fetcher.get_realtime_quote("AAPL") is None
