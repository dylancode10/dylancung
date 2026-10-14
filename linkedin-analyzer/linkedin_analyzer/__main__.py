"""Command-line entry point.

    python -m linkedin_analyzer EXPORT [--analytics FILE.xlsx] [--out report.md] [--chat]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic

from .agent import PostAnalyzer
from .loader import load_analytics, load_shares, merge_analytics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linkedin_analyzer", description="Analyze your LinkedIn posts with Claude.")
    parser.add_argument("export", help="Shares.csv, the unzipped LinkedIn export folder, or the export .zip")
    parser.add_argument("--analytics", help="Creator analytics export (.xlsx) with impressions/engagements")
    parser.add_argument("--out", default="linkedin_report.md", help="Where to save the report (default: %(default)s)")
    parser.add_argument("--chat", action="store_true", help="Ask follow-up questions after the report")
    parser.add_argument("--ask", help="Answer one question instead of writing the full report")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show which tools the agent calls")
    args = parser.parse_args(argv)

    posts = load_shares(args.export)
    if not posts:
        print("No posts found in the export.", file=sys.stderr)
        return 1
    print(f"Loaded {len(posts)} posts ({posts[0].date:%Y-%m-%d} to {posts[-1].date:%Y-%m-%d}).")

    if args.analytics:
        matched = merge_analytics(posts, load_analytics(args.analytics))
        print(f"Matched analytics for {matched} posts.")

    analyzer = PostAnalyzer(posts, verbose=args.verbose)
    try:
        if args.ask:
            print("\n" + analyzer.ask(args.ask))
        else:
            print("Analyzing… (this can take a minute or two)")
            report = analyzer.report()
            Path(args.out).write_text(report + "\n", encoding="utf-8")
            print(f"\n{report}\n\nSaved report to {args.out}")

        if args.chat:
            print("\nAsk follow-up questions (empty line or Ctrl-D to quit).")
            while True:
                try:
                    question = input("\n> ").strip()
                except EOFError:
                    break
                if not question:
                    break
                print("\n" + analyzer.ask(question))
    except anthropic.AuthenticationError:
        print("Authentication failed: set ANTHROPIC_API_KEY (or run `ant auth login`).", file=sys.stderr)
        return 1
    except anthropic.RateLimitError:
        print("Rate limited by the API; wait a bit and try again.", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"API error {e.status_code}: {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError:
        print("Could not reach the Anthropic API; check your network.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
