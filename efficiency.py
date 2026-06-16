#!/usr/bin/env python3
"""
Claude Code Message Efficiency Analyzer

Compares the overhead of different interaction methods:
- Telegram plugin: each reply requires an MCP tool call (~477 chars overhead/msg)
- PWA / Terminal: direct stdout, zero tool call overhead

Reads session JSONL files and calculates the effective content ratio.
"""

import json
import glob
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEFAULT_SESSION_DIR = os.path.expanduser("~/.claude/projects")


def find_session_files(session_dir: str) -> list[str]:
    """Find top-level session JSONL files (excludes subagent/tool-result subdirs)."""
    return glob.glob(os.path.join(session_dir, "*.jsonl"))


def analyze_session(filepath: str) -> dict:
    """Analyze a single session for tool call overhead."""
    tg_reply_calls = 0
    other_tool_calls = 0
    total_output_tokens = 0
    total_input_tokens = 0

    tg_reply_content_chars = 0
    tg_reply_overhead_chars = 0
    text_output_chars = 0

    with open(filepath) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = obj.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", [])
            usage = msg.get("usage", {})

            if usage:
                total_output_tokens += usage.get("output_tokens", 0)
                total_input_tokens += usage.get("input_tokens", 0)

            if role == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        if "telegram" in name and "reply" in name:
                            tg_reply_calls += 1
                            actual_text = block.get("input", {}).get("text", "") or ""
                            block_json = json.dumps(block, ensure_ascii=False)
                            tg_reply_content_chars += len(actual_text)
                            tg_reply_overhead_chars += len(block_json) - len(actual_text)
                        else:
                            other_tool_calls += 1

                    elif block.get("type") == "text":
                        text_output_chars += len(block.get("text", ""))

    return {
        "tg_reply_calls": tg_reply_calls,
        "other_tool_calls": other_tool_calls,
        "total_output_tokens": total_output_tokens,
        "total_input_tokens": total_input_tokens,
        "tg_reply_content_chars": tg_reply_content_chars,
        "tg_reply_overhead_chars": tg_reply_overhead_chars,
        "text_output_chars": text_output_chars,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze message delivery efficiency in Claude Code sessions."
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_SESSION_DIR,
        help=f"Session directory (default: {DEFAULT_SESSION_DIR})",
    )
    parser.add_argument(
        "--tz-offset",
        type=int,
        default=None,
        help="UTC offset in hours for display",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_out", help="Output as JSON"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.tz_offset is not None:
        tz = timezone(timedelta(hours=args.tz_offset))
    else:
        tz = datetime.now().astimezone().tzinfo

    files = find_session_files(args.dir)
    if not files:
        print(f"No session files found in {args.dir}")
        sys.exit(1)

    daily: dict = {}

    for f in files:
        mtime = datetime.fromtimestamp(os.path.getmtime(f), tz=tz)
        day = mtime.strftime("%Y-%m-%d")

        stats = analyze_session(f)
        if stats["total_output_tokens"] == 0:
            continue

        if day not in daily:
            daily[day] = {
                "tg_reply_calls": 0,
                "other_tool_calls": 0,
                "total_output_tokens": 0,
                "tg_reply_content_chars": 0,
                "tg_reply_overhead_chars": 0,
                "text_output_chars": 0,
            }

        for key in daily[day]:
            daily[day][key] += stats[key]

    if args.json_out:
        print(json.dumps(daily, indent=2))
        return

    # Per-message overhead breakdown
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   Claude Code Message Efficiency Report      ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()

    # Explain overhead
    print("  Per-message overhead (Telegram MCP plugin):")
    print("  ┌──────────────────────────────────────────────┐")
    print("  │  tool_use wrapper:   ~186 chars (output)     │")
    print("  │  tool_result:        ~130 chars (input)      │")
    print("  │  channel flag:       ~161 chars (input)      │")
    print("  │  ────────────────────────────────             │")
    print("  │  Total:              ~477 chars per message   │")
    print("  │                                              │")
    print("  │  Direct stdout (PWA/Terminal): 0 overhead    │")
    print("  └──────────────────────────────────────────────┘")
    print()

    # Daily breakdown
    print("  Date       TG replies  Other tools  Output tokens  TG overhead%")
    print("  ─────────  ──────────  ───────────  ─────────────  ────────────")

    total_tg = 0
    total_other = 0

    for day in sorted(daily.keys()):
        s = daily[day]
        total_calls = s["tg_reply_calls"] + s["other_tool_calls"]
        tg_pct = (
            f"{s['tg_reply_calls'] / total_calls * 100:.0f}%"
            if total_calls > 0
            else "—"
        )

        total_tg += s["tg_reply_calls"]
        total_other += s["other_tool_calls"]

        print(
            f"  {day}  {s['tg_reply_calls']:>10}  {s['other_tool_calls']:>11}"
            f"  {s['total_output_tokens']:>13,}  {tg_pct:>12}"
        )

    print()
    print(f"  Total Telegram reply calls: {total_tg:,}")
    print(f"  Total other tool calls:     {total_other:,}")
    print()

    # Efficiency calculation
    total_tg_content = sum(d["tg_reply_content_chars"] for d in daily.values())
    total_tg_overhead = sum(d["tg_reply_overhead_chars"] for d in daily.values())
    total_text = sum(d["text_output_chars"] for d in daily.values())

    if total_tg_content + total_tg_overhead > 0:
        tg_efficiency = total_tg_content / (total_tg_content + total_tg_overhead) * 100
    else:
        tg_efficiency = 0

    print("  Effective Content Ratio:")
    print(f"    Telegram replies:  {tg_efficiency:.1f}% useful content")
    print(f"    Direct stdout:     100.0% useful content")
    print()

    if total_tg > 0:
        avg_overhead_per_msg = total_tg_overhead / total_tg
        daily_avg_tg = total_tg / len(daily)
        daily_wasted_tokens = daily_avg_tg * avg_overhead_per_msg / 4
        print(f"  Estimated daily overhead from Telegram:")
        print(f"    ~{daily_avg_tg:.0f} reply calls/day")
        print(f"    ~{avg_overhead_per_msg:.0f} chars overhead/call")
        print(f"    ~{daily_wasted_tokens:,.0f} wasted tokens/day")
        print()


if __name__ == "__main__":
    main()
