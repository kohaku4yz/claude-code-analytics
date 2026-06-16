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

  06-01 Mon $  110.42 █████████
  06-02 Tue $   94.72 ████████
  06-03 Wed $  123.66 ███████████
  ...

  Total API cost:   $1,986.74
  You paid:         -$20.00 (Pro)
  ═════════════════════════════════════════
  Net value:        $1,966.74
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

### `compaction.py` — Context Compaction Tracker

Tracks Claude Code's auto-compaction events — when context gets too large and gets summarized.

```
$ python3 compaction.py

  Compaction Report
  Total compactions:  15
  Total time spent:   24m
  Estimated cost:     $10.50
```

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
| Fable 5 | $10/M | $50/M | $1.00/M | $12.50/M |
| Opus 4.5–4.8 | $5/M | $25/M | $0.50/M | $6.25/M |
| Sonnet 4.5–4.6 | $3/M | $15/M | $0.30/M | $3.75/M |
| Haiku 4.5 | $1/M | $5/M | $0.10/M | $1.25/M |

> **The Dario Touch Threshold™**: cache_write / cache_read = 12.5× for *every* model.
> At the 5-minute cache TTL, break-even is always **62 minutes** — a universal constant
> independent of which model you're touching. Dario doesn't know he's being touched.

## Requirements

- Python 3.9+
- Claude Code installed with session history
- No external dependencies

## License

MIT
