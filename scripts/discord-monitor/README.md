# Discord Monitor

Standalone polling script. Works **without Claude Code open** — reads the same
bot token the MCP plugin uses.

## 快速啟動

```bash
# 1. 確保 token 已設定（Claude Code 跑過 /discord:configure 就有了）
cat ~/.claude/channels/discord/.env     # 應看到 DISCORD_BOT_TOKEN=...

# 2. 安裝 dependencies（第一次）
pip install -r scripts/discord-monitor/requirements.txt

# 3. 啟動
chmod +x scripts/discord-monitor/start.sh
./scripts/discord-monitor/start.sh
```

## 參數

| 參數 | 預設 | 說明 |
|---|---|---|
| `--channel` | `1241933442434732128` | 要監聽的頻道 ID |
| `--interval` | `30` | Poll 間隔（秒） |
| `--reply` | off | 有人 mention bot 時自動呼叫 Claude API 回覆 |
| `--limit` | `10` | 每次 poll 取幾則訊息 |

### 範例

```bash
# 只看訊息，不自動回覆
./scripts/discord-monitor/start.sh

# 自動回覆（需要 ANTHROPIC_API_KEY 在 .env）
./scripts/discord-monitor/start.sh --reply

# 監聽不同頻道，20 秒 poll
./scripts/discord-monitor/start.sh --channel 123456789 --interval 20
```

## 運作方式

1. 啟動時讀取 `~/.claude/channels/discord/.env` 裡的 `DISCORD_BOT_TOKEN`
2. 記錄最新訊息 ID → 只處理**之後**的新訊息（不重播舊訊息）
3. 每 `--interval` 秒呼叫 Discord REST API 取新訊息
4. 有新訊息 → 印到 terminal
5. `--reply` 模式下，訊息 mention bot ID 時自動呼叫 Claude API 回覆

## 停止

`Ctrl+C`

## 注意事項

- Token 位置：`~/.claude/channels/discord/.env`（git-ignored，不會推上去）
- `.env`（repo 根目錄）也是 git-ignored，可放 `ANTHROPIC_API_KEY`
- 這個腳本本身不含任何 key，安全提交
