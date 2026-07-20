# Alpha Vantage 每日預算護欄

Alpha Vantage 免費方案目前限制每日 25 次請求。JEAC 將它視為美股最後備援，不作為主要資料來源；每次 HTTP 請求在發送前先保留一次預算，HTTP 失敗也會計入，避免重試把供應商配額用完。

## 預設行為

- `ALPHAVANTAGE_MAX_REQUESTS_PER_DAY=25`（Variable 只能調低，程式硬上限仍為 25）
- `ALPHAVANTAGE_BUDGET_TIMEZONE=UTC`
- `ALPHAVANTAGE_BUDGET_FILE=data/provider_budget/alphavantage.json`
- `ALPHAVANTAGE_NAME_LOOKUP_ENABLED=false`

日線、即時報價與名稱查詢共用同一個計數器。達到 25 次後，Alpha Vantage fetcher 會安全降級，讓 Finnhub、Yahoo、Nasdaq/Stooq 等來源繼續嘗試。

GitHub Actions 的三個 JEAC 報告 workflow 會以台北日期快取 `provider_budget/`，並以共用 concurrency group 避免日報、週報與月報同時更新計數器。預算檔不是報告資料，也不包含 API key。

## 可選 Repository Variables

一般不需要新增 Variable，預設值已經符合免費方案。若要調整，可設定：

- `ALPHAVANTAGE_MAX_REQUESTS_PER_DAY`：可調低；目前免費方案的程式硬上限為 25。
- `ALPHAVANTAGE_BUDGET_TIMEZONE`：通常維持 `UTC`；只有確認供應商日切換時區後才修改。
- `ALPHAVANTAGE_NAME_LOOKUP_ENABLED`：只有在需要且願意消耗額外請求時才設為 `true`。

`ALPHAVANTAGE_API_KEY` 必須放在 GitHub Repository Secret，不能放 Variable 或提交到程式碼。

