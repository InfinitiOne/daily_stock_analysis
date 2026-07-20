# JEAC Skills 與 SEPA 回測

本專案提供五個可攜式協作 Skills：資料品質、SEPA 波段、新聞情報、回測驗證與組合風險。它們位於 `.claude/skills/jeac-*/SKILL.md`，可複製到相容的 agent 專案中使用；不包含任何密鑰、交易執行或專案路徑依賴。

## 跨 Agent 單向同步

`.claude/skills/` 是唯一版本控管真源。以 `scripts/sync_agent_skills.py` 將五個 `jeac-*` Skills **單向複製**至目標 Agent；它不會讀取目標作為來源，也不會反向覆寫 repository。

先預覽，再明確套用：

```bash
# Claude 個人 Skills：~/.claude/skills
python scripts/sync_agent_skills.py --target claude
python scripts/sync_agent_skills.py --target claude --apply

# Codex 個人 Skills：~/.agents/skills
python scripts/sync_agent_skills.py --target codex --apply

# 同步兩者；或部署到其他相容 Agent 的 Skills 目錄
python scripts/sync_agent_skills.py --target all --apply
python scripts/sync_agent_skills.py --target directory --destination /path/to/skills --apply
```

`--check` 會以內容雜湊驗證目標是否與真源一致，適合升級後確認。`--prune --apply` 只會移除先前由此腳本寫入 manifest 且已不在真源的 `jeac-*` 目錄，不會刪除其他 Agent 自有 Skills。可使用 `JEAC_CLAUDE_SKILLS_DIR` 或 `JEAC_CODEX_SKILLS_DIR` 覆寫預設目標路徑。

## 網頁版與行動版一般 ChatGPT

一般 Chat mode 與手機 App 不支援安裝 repository Skill 或 Plugin。若要讓 JEAC 核心規則在網頁、桌面與 iOS／Android 的一般對話都生效，請使用 `docs/chatgpt/JEAC_CUSTOM_INSTRUCTIONS.md`：將其中「可直接貼入」區塊填入 ChatGPT 的自訂指令。它只保留必要的資料品質、SEPA、新聞、組合風控與回測約束；完整報告、持股或資料檔仍應於需要時附加到對話或 Project。

`src.core.sepa_backtest.SepaBacktest` 是獨立的長多 SEPA pivot 驗證器。它要求完整、遞增的日 OHLCV；以 Stage 2、近高 SEPA、波動與成交量收斂、以及樞紐帶量突破產生訊號；訊號確認後的下一交易日開盤才進場。停損與目標在同一日同時觸及時，採保守的停損優先處理。

回測輸出包含每筆訊號/進出場日期、成本與滑價後報酬、退出原因，以及交易數、勝率、平均/中位數報酬、期望值、profit factor、最大回撤和曝險。輸入不足或不一致時回傳 `blocked`，不會以補值產生結論。

這是歷史規則驗證，不是績效保證或自動下單功能。正式使用時應依市場、標的池和資料可得性進行樣本外或 walk-forward 驗證，並揭露存活者偏差限制。

## 日報 DOCX

本地日報儲存時會在 `reports/` 同時產生同名 `.md` 與 `.docx`。Markdown 維持通知與機器可讀的原始格式；DOCX 使用相同的標題、段落、清單與表格轉譯，適合以 Word 閱讀或轉寄。DOCX 轉譯失敗不會丟失 Markdown 日報，日誌會保留失敗原因。
