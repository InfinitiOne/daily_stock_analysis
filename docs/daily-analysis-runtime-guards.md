# 每日股票分析執行時間護欄

每日股票分析以最新一次需求為準：新的手動或排程 run 會取消同一 concurrency group 內舊的排隊／執行 run，避免舊報告佔住資源。整個 job 固定最多 25 分鐘。

日報預設以單一 worker 串行處理持倉，因此工作流設定以下護欄：單次 LLM 請求 45 秒、限流僅重試一次且最多等待 20 秒、完整性重試預設關閉，基本面階段 25 秒且單來源 6 秒。可用同名 Repository Variable 在安全範圍內調整；程式仍會將單次 LLM timeout 限制在 10–180 秒。

若日報被取消，請先確認新的 run 是否已啟動；不要同時反覆手動觸發。若 job 仍超時，下載 `analysis-diagnostics-*` artifact，搜尋最後一個 `LLM調用`、`rate limit` 或資料源 timeout 訊息。
