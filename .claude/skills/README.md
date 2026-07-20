# Repository Claude Skills

本目录存放仓库级协作 skills，属于版本库资产。

- 规则真源：仓库根目录 `AGENTS.md`
- 兼容入口：根目录 `CLAUDE.md`（应为指向 `AGENTS.md` 的软链接）
- 本目录中的 skill 需要与 `AGENTS.md` 保持一致
- `.claude/reviews/` 属于本地分析产物，不作为规则真源

本目录是唯一真源。要部署五个 `jeac-*` Skills 至 Claude、Codex 或相容 Agent，使用仓库根目录的 `scripts/sync_agent_skills.py`；Codex 使用 `~/.agents/skills`，网页 ChatGPT 使用由 `--target plugin --apply` 生成的 Plugin bundle。脚本只会从本目录单向复制，绝不从目标目录反向覆盖真源。
