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

## ChatGPT 網頁版 Plugin

網頁版不會執行本機同步腳本，也不能直接將任意 GitHub repository 當作 Plugin marketplace。它使用已安裝或已分享至 workspace 的 Plugin；因此要先在 ChatGPT Desktop App（Work mode／Codex）從本機 checkout 的 repository marketplace 安裝並分享，再回到網頁版使用。每次修改真源後，由 maintainer 執行下列命令更新可發布 bundle，CI 會拒絕不同步的 PR：

```bash
python scripts/sync_agent_skills.py --target plugin --apply
python scripts/sync_agent_skills.py --target plugin --check
```

每次變更 Plugin bundle 時，也要將 `plugins/jeac-research-skills/.codex-plugin/plugin.json` 的語意版本遞增，讓已安裝的 Plugin 可辨識更新。

合併後，maintainer 先在電腦上 clone repository、以 ChatGPT Desktop App 開啟該 checkout，切至 **Work mode → Plugins**，於 **JEAC Research** marketplace 安裝 **JEAC Research Skills**，再從 **Created by you → Share** 分享給需要使用的 workspace 成員或群組。網頁版使用者再切至 **Work mode → Plugins → Shared with me** 安裝，並開啟新對話。若 workspace 管理員停用 Plugin sharing，必須先由管理員開啟；單純在瀏覽器中無法直接載入 GitHub repo。

Plugin 不含資料抓取、API Key 或交易執行；它只提供 JEAC 的資料品質、新聞、SEPA、組合風控與回測驗證工作流程。

`src.core.sepa_backtest.SepaBacktest` 是獨立的長多 SEPA pivot 驗證器。它要求完整、遞增的日 OHLCV；以 Stage 2、近高 SEPA、波動與成交量收斂、以及樞紐帶量突破產生訊號；訊號確認後的下一交易日開盤才進場。停損與目標在同一日同時觸及時，採保守的停損優先處理。

回測輸出包含每筆訊號/進出場日期、成本與滑價後報酬、退出原因，以及交易數、勝率、平均/中位數報酬、期望值、profit factor、最大回撤和曝險。輸入不足或不一致時回傳 `blocked`，不會以補值產生結論。

這是歷史規則驗證，不是績效保證或自動下單功能。正式使用時應依市場、標的池和資料可得性進行樣本外或 walk-forward 驗證，並揭露存活者偏差限制。

## 日報 DOCX

本地日報儲存時會在 `reports/` 同時產生同名 `.md` 與 `.docx`。Markdown 維持通知與機器可讀的原始格式；DOCX 使用相同的標題、段落、清單與表格轉譯，適合以 Word 閱讀或轉寄。DOCX 轉譯失敗不會丟失 Markdown 日報，日誌會保留失敗原因。
