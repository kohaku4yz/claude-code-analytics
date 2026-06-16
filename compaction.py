#!/usr/bin/env python3
"""
Claude Code Compaction Cost Analyzer

When a conversation gets too long, Claude Code automatically (or manually)
compacts it — summarizing earlier context to free up space. This costs tokens.

This script finds all compaction events and estimates their cost.
"""

import json
import glob
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEFAULT_SESSION_DIR = os.path.expanduser("~/.claude/projects")

# Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "opus": {"input": 15.0, "output": 75.0},
    "sonnet": {"input": 3.0, "output": 15.0},
    "haiku": {"input": 0.80, "output": 4.0},
    "fable": {"input": 30.0, "output": 150.0},
}

SUMMARY_RATIO = 0.05  # summary output is roughly 5% of input tokens


def find_session_files(session_dir: str) -> list[str]:
    """Find top-level session JSONL files (excludes subagent/tool-result subdirs)."""
    return glob.glob(os.path.join(session_dir, "*.jsonl"))


def find_compactions(filepath: str, tz) -> list[dict]:
    """Find all compact_boundary events in a session file."""
    compactions = []
    prev_input_tokens = 0
    post_compact_input = None
    pending_compact = None

    with open(filepath) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Track input tokens to detect post-compact context size
            usage = obj.get("message", {}).get("usage", {})
            if usage:
                current_input = usage.get("input_tokens", 0)
                if pending_compact and current_input > 0:
                    pending_compact["post_tokens"] = current_input
                    pending_compact["tokens_freed"] = (
                        pending_compact["pre_tokens"] - current_input
                    )
                    compactions.append(pending_compact)
                    pending_compact = None
                prev_input_tokens = current_input

            if obj.get("subtype") == "compact_boundary":
                meta = obj.get("compactMetadata", {})
                ts_str = obj.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(
                        ts_str.replace("Z", "+00:00")
                    ).astimezone(tz)
                except (ValueError, TypeError):
                    dt = None

                pending_compact = {
                    "time": dt,
                    "trigger": meta.get("trigger", "unknown"),
                    "pre_tokens": meta.get("preTokens", 0),
                    "duration_ms": meta.get("durationMs", 0),
                    "post_tokens": None,
                    "tokens_freed": None,
                    "session": Path(filepath).stem,
                }

    # If last compact had no subsequent message
    if pending_compact:
        pending_compact["post_tokens"] = None
        pending_compact["tokens_freed"] = None
        compactions.append(pending_compact)

    return compactions


def estimate_compact_cost(pre_tokens: int, model: str = "opus") -> dict:
    """Estimate the cost of a single compaction."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["opus"])
    est_output = int(pre_tokens * SUMMARY_RATIO)
    cost = (pre_tokens * pricing["input"] + est_output * pricing["output"]) / 1_000_000
    return {"input": pre_tokens, "output": est_output, "cost": cost}


def estimate_tail_cost(
    post_tokens: int, subsequent_turns: int = 50, model: str = "opus"
) -> float:
    """
    Estimate the ongoing cost of the retained context tail.
    The tail is re-sent as input on every subsequent turn.
    Assumes most re-reads hit the prompt cache.
    """
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["opus"])
    cache_read_price = pricing["input"] * 0.1  # cache reads ~10% of input price
    return (post_tokens * cache_read_price * subsequent_turns) / 1_000_000


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze Claude Code compaction events and their costs."
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_SESSION_DIR,
        help=f"Session directory (default: {DEFAULT_SESSION_DIR})",
    )
    parser.add_argument(
        "--model",
        choices=list(MODEL_PRICING.keys()),
        default="opus",
        help="Model used for compaction (default: opus)",
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

    all_compactions = []
    for f in files:
        all_compactions.extend(find_compactions(f, tz))

    all_compactions.sort(key=lambda c: c["time"] or datetime.min.replace(tzinfo=tz))

    if not all_compactions:
        print("No compaction events found.")
        return

    if args.json_out:
        out = []
        for c in all_compactions:
            entry = {
                "time": c["time"].isoformat() if c["time"] else None,
                "trigger": c["trigger"],
                "pre_tokens": c["pre_tokens"],
                "post_tokens": c["post_tokens"],
                "tokens_freed": c["tokens_freed"],
                "duration_ms": c["duration_ms"],
            }
            entry.update(estimate_compact_cost(c["pre_tokens"], args.model))
            out.append(entry)
        print(json.dumps(out, indent=2))
        return

    # Header
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   Claude Code Compaction Report              ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()

    # Event table
    print(
        f"  {'Date':>14}  {'Trigger':>7}  {'Before':>9}  {'After':>9}"
        f"  {'Freed':>9}  {'Duration':>8}  {'Est.Cost':>8}"
    )
    print(f"  {'─'*14}  {'─'*7}  {'─'*9}  {'─'*9}  {'─'*9}  {'─'*8}  {'─'*8}")

    total_cost = 0
    total_duration = 0
    total_freed = 0
    auto_count = 0
    manual_count = 0

    for c in all_compactions:
        time_str = c["time"].strftime("%m/%d %H:%M") if c["time"] else "?"
        pre = f"{c['pre_tokens']:,}"
        post = f"{c['post_tokens']:,}" if c["post_tokens"] else "—"
        freed = f"{c['tokens_freed']:,}" if c["tokens_freed"] else "—"
        dur = f"{c['duration_ms'] / 1000:.0f}s"
        est = estimate_compact_cost(c["pre_tokens"], args.model)
        cost_str = f"${est['cost']:.2f}"

        total_cost += est["cost"]
        total_duration += c["duration_ms"]
        if c["tokens_freed"]:
            total_freed += c["tokens_freed"]
        if c["trigger"] == "auto":
            auto_count += 1
        else:
            manual_count += 1

        print(
            f"  {time_str:>14}  {c['trigger']:>7}  {pre:>9}  {post:>9}"
            f"  {freed:>9}  {dur:>8}  {cost_str:>8}"
        )

    # Summary
    print()
    print("  ─────────────────────────────────────────────────────────")
    print(f"  Total compactions:    {len(all_compactions)}")
    print(f"    Auto:               {auto_count}")
    print(f"    Manual:             {manual_count}")
    print(f"  Total time:           {total_duration / 1000:.0f}s ({total_duration / 60000:.1f} min)")
    print(f"  Avg duration:         {total_duration / len(all_compactions) / 1000:.0f}s")
    print(f"  Total tokens freed:   {total_freed:,}")
    print(f"  ─────────────────────────────────────────────────────────")
    print(f"  Est. compaction cost: ${total_cost:.2f} ({args.model} pricing)")
    print()

    # Insights
    if total_freed > 0:
        avg_compression = total_freed / len(
            [c for c in all_compactions if c["tokens_freed"]]
        )
        print(f"  Avg tokens freed per compaction: {avg_compression:,.0f}")

    auto_compacts = [c for c in all_compactions if c["trigger"] == "auto"]
    if auto_compacts:
        avg_auto_pre = sum(c["pre_tokens"] for c in auto_compacts) / len(auto_compacts)
        print(
            f"  Avg context size at auto-compact: {avg_auto_pre:,.0f} tokens"
        )
        print(
            f"  (this is roughly when Claude Code decides context is too long)"
        )

    print()


if __name__ == "__main__":
    main()
