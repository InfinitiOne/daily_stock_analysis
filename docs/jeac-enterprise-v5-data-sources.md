# JEAC Enterprise 5.0 資料來源整合

本文件盤點目前資料來源層，並定義 JEAC 5.0 的來源優先順序、驗證規則與已知缺口。

## 25 份資料來源相關檔案盤點

盤點範圍包含 19 份 `data_provider/` 核心檔案，以及 6 份直接建立或補強來源證據的服務檔案，共 25 份：

| # | 檔案 | 職責 |
| ---: | --- | --- |
| 1 | `data_provider/__init__.py` | Provider 對外匯出與相容入口 |
| 2 | `data_provider/base.py` | 統一路由、fallback、熔斷、基本面彙整與來源鏈 |
| 3 | `data_provider/akshare_fetcher.py` | AkShare 行情與市場資料 |
| 4 | `data_provider/alphavantage_fetcher.py` | Alpha Vantage 美股來源 |
| 5 | `data_provider/baostock_fetcher.py` | Baostock A 股歷史行情 |
| 6 | `data_provider/efinance_fetcher.py` | Efinance 行情來源 |
| 7 | `data_provider/finnhub_fetcher.py` | Finnhub 美股行情 |
| 8 | `data_provider/fundamental_adapter.py` | AkShare 基本面標準化 adapter |
| 9 | `data_provider/jeac_source_policy.py` | JEAC 官方來源、交叉驗證與品質契約 |
| 10 | `data_provider/longbridge_fetcher.py` | Longbridge 美股／港股行情 |
| 11 | `data_provider/pytdx_fetcher.py` | 通達信行情來源 |
| 12 | `data_provider/realtime_types.py` | 即時行情 Schema、品質欄位與熔斷器 |
| 13 | `data_provider/tencent_fetcher.py` | 騰訊 A 股日線 fallback |
| 14 | `data_provider/tickflow_fetcher.py` | TickFlow 行情、批次日線與排行 |
| 15 | `data_provider/tushare_fetcher.py` | Tushare A／港股來源 |
| 16 | `data_provider/tw_institutional_fetcher.py` | TWSE T86／TPEx 三大法人官方資料 |
| 17 | `data_provider/us_index_mapping.py` | 美股指數與 Yahoo symbol 映射 |
| 18 | `data_provider/yfinance_fetcher.py` | Yahoo 全球行情及台股 `.TW`／`.TWO` |
| 19 | `data_provider/yfinance_fundamental_adapter.py` | Yahoo 海外基本面 adapter |
| 20 | `src/search_service.py` | 新聞搜尋、時效與多來源查詢 |
| 21 | `src/services/intelligence_service.py` | RSS／Atom／NewsNow 情報來源 |
| 22 | `src/services/social_sentiment_service.py` | 社群情緒來源彙整 |
| 23 | `src/services/market_hotspot_service.py` | 產業／概念排行來源 |
| 24 | `src/services/market_structure_service.py` | 市場結構與題材證據整合 |
| 25 | `src/services/stock_index_remote_service.py` | 遠端股票索引來源與本地 fallback |

### 能力矩陣

| 類型 | 主要檔案 | 現有能力 | JEAC 判定 |
| --- | --- | --- | --- |
| 統一路由 | `data_provider/base.py` | 市場辨識、來源排序、fallback、熔斷、來源鏈 | 可沿用 |
| 台股日線／即時 | `data_provider/yfinance_fetcher.py` | `.TW`／`.TWO` Yahoo 行情 | 僅輔助來源，未達官方優先 |
| 台股法人 | `data_provider/tw_institutional_fetcher.py` | TWSE T86、TPEx OpenAPI、日期與單位保護 | 符合官方來源原則；單一官方資料集不等於交叉驗證 |
| A 股行情 | `akshare`、`tushare`、`efinance`、`tencent`、`baostock`、`pytdx`、`tickflow` | 多來源日線、即時與 fallback | 保留原路由，另以資料品質契約揭露來源 |
| 美股／港股 | `finnhub`、`alphavantage`、`longbridge`、`yfinance` | 行情與 fallback | 缺交易所官方行情；正式數字需標示來源層級 |
| 基本面 | `fundamental_adapter.py`、`yfinance_fundamental_adapter.py` | AkShare／Yahoo 彙整 | 台股尚未接 MOPS，不能標示為官方驗證 |
| 新聞情報 | `src/search_service.py`、`src/services/intelligence_service.py` | 搜尋、RSS／Atom、SEC／HKEX 範本 | 新聞與公告需區分官方證據與媒體敘述 |

## 新增可執行契約

`data_provider/jeac_source_policy.py` 提供：

- 市場 × 資料集的來源優先序與官方來源清單。
- `official_source_present`：是否真的取得官方來源。
- `cross_validated`：只有呼叫端實際比較相同日期、單位與交易時段後才能為真。
- `limitations`：官方來源缺漏、獨立來源不足、數值未比較、來源衝突與缺欄位。
- `verified`／`partial`／`unavailable` 三段資料品質狀態。

這個契約禁止把「曾嘗試多個 fallback」誤寫成「完成交叉驗證」。

## JEAC 5.0 來源優先順序

### 台股

1. 上市行情與法人：TWSE；上櫃行情與法人：TPEx。
2. 月營收、財報、重大訊息、法說與股利：MOPS。
3. Yahoo／FinMind 等作行情交叉驗證或歷史計算。
4. Goodinfo／WantGoo／HiStock屬輔助人工查核來源，目前未程式化接入。

### 美股

1. 公司 Investor Relations 與 SEC。
2. Nasdaq／NYSE 官方資訊。
3. Finnhub、Alpha Vantage、Longbridge、Yahoo 等行情或聚合來源。
4. 媒體與分析師資料只能作事件與共識輔助。

## 現階段限制

- 台股 OHLCV 目前仍只有 Yahoo 程式路由，尚未達 JEAC 的 TWSE／TPEx 官方行情優先標準。
- 台股基本面尚未接 MOPS，Yahoo 數據不得宣稱為 MOPS 交叉驗證。
- `Goodinfo`、`WantGoo`、`HiStock` 未接入，且接入前需確認授權與網站條款。
- 現有 `get_daily_data()` 維持相容契約；來源品質需由新契約逐步接到分析上下文與報告。

## 後續整合順序

1. 新增 TWSE／TPEx 官方行情 adapter，並與 Yahoo 同日期、同單位比對。
2. 新增 MOPS 月營收、財報、重大訊息 adapter。
3. 將 JEAC 品質物件加入 AnalysisContextPack 與報告「資料限制」。
4. 對價格、成交量、法人與財報分別建立容許差異，不以單一誤差門檻混用。

## 回滾

本階段不改動既有來源路由與回傳 Schema。若需回滾，只要移除 JEAC policy 模組、測試與本文件即可；原有分析與 fallback 行為不受影響。
