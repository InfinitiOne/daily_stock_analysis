# -*- coding: utf-8 -*-

from data_provider.finmind_fetcher import FinMindFetcher


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


def test_finmind_daily_data_normalizes_taiwan_stock_price():
    session = FakeSession(FakeResponse({
        "status": 200,
        "data": [{
            "date": "2026-07-17",
            "Trading_Volume": 1000,
            "Trading_money": 105000,
            "open": 103,
            "max": 106,
            "min": 102,
            "close": 105,
            "spread": 3,
            "Trading_turnover": 100,
        }],
    }))
    fetcher = FinMindFetcher(api_token="token", session=session)

    frame = fetcher.get_daily_data("2330.TW", start_date="2026-07-17", end_date="2026-07-17")

    assert frame.iloc[0]["code"] == "2330.TW"
    assert frame.iloc[0]["high"] == 106
    assert frame.iloc[0]["low"] == 102
    assert frame.iloc[0]["volume"] == 1000
    assert round(frame.iloc[0]["pct_chg"], 2) == round(3 / 102 * 100, 2)
    assert session.calls[0]["headers"]["Authorization"] == "Bearer token"
    assert session.calls[0]["params"]["dataset"] == "TaiwanStockPrice"
