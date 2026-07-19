from types import SimpleNamespace

from src.services.market_segmented_report import build_taiwan_us_report, split_results_by_market


class _Notifier:
    def generate_aggregate_report(self, results, _report_type):
        return "個股：" + ",".join(item.code for item in results)


def test_split_results_by_market_preserves_order():
    results = [
        SimpleNamespace(code="NVDA"),
        SimpleNamespace(code="2330.TW"),
        SimpleNamespace(code="TSM"),
        SimpleNamespace(code="006208.TW"),
    ]
    taiwan, us = split_results_by_market(results)
    assert [item.code for item in taiwan] == ["2330.TW", "006208.TW"]
    assert [item.code for item in us] == ["NVDA", "TSM"]


def test_build_report_interleaves_each_market_with_its_holdings():
    review = SimpleNamespace(
        market_review_payload={
            "markets": {
                "tw": {"markdown_report": "台股大盤內容"},
                "us": {"markdown_report": "美股大盤內容"},
            }
        }
    )
    result = build_taiwan_us_report(
        title="# 報告",
        notifier=_Notifier(),
        results=[SimpleNamespace(code="NVDA"), SimpleNamespace(code="2330.TW")],
        report_type="full",
        review_result=review,
        evidence_markdown="資料來源內容",
    )
    assert result.index("台股大盤走勢分析") < result.index("個別台股")
    assert result.index("個別台股") < result.index("美股大盤走勢分析")
    assert result.index("美股大盤走勢分析") < result.index("個別美股")
    assert "個股：2330.TW" in result
    assert "個股：NVDA" in result
