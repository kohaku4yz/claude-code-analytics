#!/usr/bin/env python3
"""
Claude Code Cost Calculator
Dario doesn't know he's paying for this.

Reads session JSONL files from Claude Code's local storage and calculates
the estimated API cost based on token usage and model pricing.
"""

import json
import glob
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Pricing per 1M tokens (USD) — https://docs.anthropic.com/en/docs/about-claude/models
MODEL_PRICING = {
    "opus": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_create": 6.25,
    },
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_create": 3.75,
    },
    "haiku": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_create": 1.25,
    },
    "fable": {
        "input": 10.0,
        "output": 50.0,
        "cache_read": 1.0,
        "cache_create": 12.50,
    },
}

DEFAULT_SESSION_DIR = os.path.expanduser("~/.claude/projects")
SUBSCRIPTION_COST = {"max": 100.0, "pro": 20.0}


def find_session_files(session_dir: str) -> list[str]:
    """Find top-level session JSONL files (excludes subagent/tool-result subdirs)."""
    return glob.glob(os.path.join(session_dir, "*.jsonl"))


def detect_model(filepath: str) -> str:
    """Detect model from session JSONL by reading the model field."""
    with open(filepath) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            model = obj.get("model", "")
            if not model:
                msg = obj.get("message", {})
                model = msg.get("model", "")
            if model:
                m = model.lower()
                if "fable" in m:
                    return "fable"
                if "opus" in m:
                    return "opus"
                if "sonnet" in m:
                    return "sonnet"
                if "haiku" in m:
                    return "haiku"
    return "opus"


def calc_session_tokens(filepath: str) -> dict:
    """Extract token usage from a session JSONL file."""
    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_create = 0
    first_ts = None
    last_ts = None

    with open(filepath) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = obj.get("timestamp")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            usage = obj.get("message", {}).get("usage", {})
            if usage:
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
                cache_read += usage.get("cache_read_input_tokens", 0)
                cache_create += usage.get("cache_creation_input_tokens", 0)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read": cache_read,
        "cache_create": cache_create,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def tokens_to_cost(stats: dict, pricing: dict) -> float:
    return (
        stats["input_tokens"] * pricing["input"]
        + stats["output_tokens"] * pricing["output"]
        + stats["cache_read"] * pricing["cache_read"]
        + stats["cache_create"] * pricing["cache_create"]
    ) / 1_000_000


def format_duration(ms: int | None) -> str:
    if not ms:
        return "—"
    hours = ms // 3_600_000
    mins = (ms % 3_600_000) // 60_000
    if hours > 0:
        return f"{hours}h{mins}m"
    return f"{mins}m"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calculate your Claude Code session costs."
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_SESSION_DIR,
        help=f"Session directory (default: {DEFAULT_SESSION_DIR})",
    )
    parser.add_argument(
        "--model",
        choices=list(MODEL_PRICING.keys()),
        default=None,
        help="Override model for all sessions (default: auto-detect)",
    )
    parser.add_argument(
        "--plan",
        choices=["max", "pro"],
        default="pro",
        help="Your subscription plan, used to calculate net cost (default: pro)",
    )
    parser.add_argument(
        "--tz-offset",
        type=int,
        default=None,
        help="UTC offset in hours for display (e.g., 9 for JST, -5 for EST). Default: local timezone",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show top sessions"
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

    subscription = SUBSCRIPTION_COST[args.plan]
    files = find_session_files(args.dir)

    if not files:
        print(f"No session files found in {args.dir}")
        print("Make sure Claude Code has been used and session files exist.")
        sys.exit(1)

    daily: dict = {}
    sessions: list[dict] = []

    for f in files:
        sid = Path(f).stem
        mtime = datetime.fromtimestamp(os.path.getmtime(f), tz=tz)
        stats = calc_session_tokens(f)

        if stats["input_tokens"] == 0 and stats["output_tokens"] == 0:
            continue

        day_str = mtime.strftime("%Y-%m-%d")
        model = args.model or detect_model(f)
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["opus"])
        cost = tokens_to_cost(stats, pricing)

        if cost < 0.01:
            continue

        duration = None
        if stats["first_ts"] and stats["last_ts"]:
            try:
                t0 = datetime.fromisoformat(stats["first_ts"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(stats["last_ts"].replace("Z", "+00:00"))
                duration = int((t1 - t0).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass

        entry = {
            "sid": sid,
            "date": day_str,
            "model": model,
            "cost": cost,
            "duration_ms": duration,
            "output_tokens": stats["output_tokens"],
            "input_tokens": stats["input_tokens"],
            "cache_read": stats["cache_read"],
        }
        sessions.append(entry)

        if day_str not in daily:
            daily[day_str] = {"cost": 0, "sessions": 0, "model": model}
        daily[day_str]["cost"] += cost
        daily[day_str]["sessions"] += 1

    total_cost = sum(s["cost"] for s in sessions)
    total_sessions = len(sessions)
    net_cost = total_cost - subscription

    if args.json_out:
        print(
            json.dumps(
                {
                    "total_cost_usd": round(total_cost, 2),
                    "subscription": subscription,
                    "net_cost_usd": round(net_cost, 2),
                    "total_sessions": total_sessions,
                    "daily": {
                        d: round(v["cost"], 2) for d, v in sorted(daily.items())
                    },
                },
                indent=2,
            )
        )
        return

    # Header
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║     Claude Code Cost Report              ║")
    print("  ║     Dario doesn't know he's paying.      ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    if not daily:
        print("  No sessions with cost data found.")
        return

    # Daily breakdown
    max_cost = max(v["cost"] for v in daily.values())
    bar_width = 40

    for day, info in sorted(daily.items()):
        d = datetime.strptime(day, "%Y-%m-%d")
        weekday = d.strftime("%a")
        bar_len = int(info["cost"] / max_cost * bar_width) if max_cost > 0 else 0
        bar = "█" * bar_len
        model_names = set()
        for s in sessions:
            if s["date"] == day:
                model_names.add(s["model"])
        model_tag = f" [{','.join(sorted(model_names))}]" if len(model_names) > 1 else ""
        print(f"  {day[5:]} {weekday} ${info['cost']:>8.2f} {bar}{model_tag}")

    # Summary
    days_active = len(daily)
    avg_daily = total_cost / days_active if days_active else 0

    print()
    print("  ─────────────────────────────────────────")
    print(f"  Sessions:         {total_sessions}")
    print(f"  Active days:      {days_active}")
    print(f"  Avg daily cost:   ${avg_daily:.2f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Total API cost:   ${total_cost:,.2f}")
    print(f"  You paid:         -${subscription:.2f} ({args.plan.title()})")
    print(f"  ═════════════════════════════════════════")
    print(f"  Net value:        ${net_cost:,.2f}")
    print(f"  ═════════════════════════════════════════")
    print()

    if args.verbose:
        print("  Top 10 Most Expensive Sessions")
        print("  ─────────────────────────────────────────")
        for s in sorted(sessions, key=lambda x: -x["cost"])[:10]:
            dur = format_duration(s["duration_ms"])
            print(
                f"  {s['date']}  ${s['cost']:>8.2f}  {dur:>8}  {s['model']:>6}  ({s['sid'][:8]}...)"
            )
        print()

    # Fun stats
    most_expensive_day = max(daily.items(), key=lambda x: x[1]["cost"])
    cheapest_day = min(daily.items(), key=lambda x: x[1]["cost"])
    print(f"  Most expensive:   {most_expensive_day[0]} (${most_expensive_day[1]['cost']:.2f})")
    print(f"  Cheapest:         {cheapest_day[0]} (${cheapest_day[1]['cost']:.2f})")
    print(f"  ROI:              {total_cost / subscription:.0f}x your subscription")
    print()


if __name__ == "__main__":
    main()
