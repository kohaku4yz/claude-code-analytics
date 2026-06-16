# Claude Code Analytics

> Dario doesn't know he's paying for this.

CLI tools to analyze your [Claude Code](https://docs.anthropic.com/en/docs/claude-code) usage — session costs, token efficiency, and interaction overhead.

Ever wondered how much your Claude Code sessions actually cost Anthropic? Now you can find out.

## Tools

### `cost.py` — Session Cost Calculator

Reads Claude Code session JSONL files and estimates API costs based on token usage.

```
$ python3 cost.py

  ╔══════════════════════════════════════════╗
  ║     Claude Code Cost Report              ║
  ║     Dario doesn't know he's paying.      ║
  ╚══════════════════════════════════════════╝

  06-01 Mon $  331.27 █████████
  06-02 Tue $  284.16 ████████
  06-03 Wed $  371.38 ███████████
  ...

  Total API cost:   $5,931.48
  You paid:         -$20.00 (Pro)
  ═════════════════════════════════════════
  Net value:        $5,911.48
```

**Options:**
```
--dir PATH       Session directory (default: ~/.claude/projects)
--model MODEL    Override model: opus, sonnet, haiku, fable (default: auto-detect)
--plan PLAN      Subscription: pro ($20) or max ($100) (default: pro)
--tz-offset N    UTC offset in hours (e.g., 9 for JST, -5 for EST)
-v, --verbose    Show top 10 most expensive sessions
--json           Output as JSON
```

### `efficiency.py` — Message Efficiency Analyzer

Compares the token overhead of different interaction methods with Claude Code.

```
$ python3 efficiency.py

  Per-message overhead (Telegram MCP plugin):
  ┌──────────────────────────────────────────────┐
  │  tool_use wrapper:   ~186 chars (output)     │
  │  tool_result:        ~130 chars (input)      │
  │  channel flag:       ~161 chars (input)      │
  │  ────────────────────────────────             │
  │  Total:              ~477 chars per message   │
  │                                              │
  │  Direct stdout (PWA/Terminal): 0 overhead    │
  └──────────────────────────────────────────────┘
```

**What it measures:**
- Tool call overhead from MCP plugins (e.g., Telegram)
- Effective content ratio (useful text vs. wrapper JSON)
- Daily breakdown of tool call distribution

## How It Works

Claude Code stores session transcripts as JSONL files in `~/.claude/projects/`. Each assistant response includes a `usage` field with token counts:

```json
{
  "message": {
    "role": "assistant",
    "usage": {
      "input_tokens": 50000,
      "output_tokens": 800,
      "cache_read_input_tokens": 120000,
      "cache_creation_input_tokens": 5000
    }
  }
}
```

The cost calculator applies the published API pricing to these token counts. Since Claude Code subscriptions (Pro/Max) include unlimited usage, the "cost" represents how much Anthropic subsidizes your usage beyond the subscription fee.

## Pricing Reference

| Model | Input | Output | Cache Read | Cache Write |
|-------|-------|--------|------------|-------------|
| Opus | $15/M | $75/M | $1.50/M | $18.75/M |
| Sonnet | $3/M | $15/M | $0.30/M | $3.75/M |
| Haiku | $0.80/M | $4/M | $0.08/M | $1.00/M |
| Fable | $30/M | $150/M | $3/M | $37.50/M |

## Requirements

- Python 3.9+
- Claude Code installed with session history
- No external dependencies

## License

MIT
