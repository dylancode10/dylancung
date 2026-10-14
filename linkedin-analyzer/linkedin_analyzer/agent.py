"""The Claude agent that analyzes LinkedIn posts using the tools in tools.py."""

from __future__ import annotations

import anthropic

from .loader import Post
from .tools import build_tools

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are a LinkedIn content strategist analyzing one creator's own posts.

You have tools that read their exported posts and compute exact statistics. Ground every
claim in tool output: quote numbers you got from the tools, cite specific posts (date plus a
short quote), and say how many posts a finding rests on. When a group has only a handful of
posts, say the pattern is tentative rather than presenting it as fact. Correlation in this
data is not causation; phrase findings accordingly.

If impressions/engagement metrics are missing, analyze content, themes, voice, format and
cadence, and tell the user that loading the Creator analytics export would unlock
performance analysis.

Read the full text of the strongest and weakest posts before drawing conclusions about
content. Recommendations should be specific and actionable for this creator, not generic
LinkedIn advice."""

REPORT_PROMPT = """Analyze my LinkedIn posts and write a report in Markdown with these sections:

1. **Snapshot** - volume, date range, cadence, and (if available) typical reach and engagement.
2. **What performs best** - top posts and what they have in common (topic, hook, format,
   length, media, timing). Compare against the weakest posts.
3. **Content themes** - the main topics I write about, how often, and how each performs.
4. **Voice & format** - hooks, structure, length, calls to action, hashtags.
5. **Timing & cadence** - day/hour patterns and consistency over time.
6. **Recommendations** - 5-7 concrete, prioritized actions, each tied to evidence above.
7. **Post ideas** - 5 post ideas with a draft opening hook, based on what works for me.

Output only the report."""


def _text_of(message) -> str:
    return "\n".join(b.text for b in message.content if b.type == "text").strip()


class PostAnalyzer:
    """Runs Claude over a fixed set of posts, keeping chat history across questions."""

    def __init__(self, posts: list[Post], client: anthropic.Anthropic | None = None, verbose: bool = False):
        self.client = client or anthropic.Anthropic()
        self.tools = build_tools(posts)
        self.messages: list = []
        self.verbose = verbose

    def ask(self, question: str) -> str:
        """Ask a question (or request a report). Returns Claude's final answer."""
        self.messages.append({"role": "user", "content": question})
        runner = self.client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=self.tools,
            messages=self.messages,
            output_config={"effort": "high"},
            cache_control={"type": "ephemeral"},
            # If a safety classifier declines, the API re-runs on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        last = None
        for message in runner:
            last = message
            # Mirror history so follow-up questions keep the full context.
            self.messages.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                if self.verbose:
                    names = [b.name for b in message.content if b.type == "tool_use"]
                    print(f"  [tools] {', '.join(names)}")
                self.messages.append(tool_response)

        if last is None:
            return ""
        if last.stop_reason == "refusal":
            return "The request was declined. Try rephrasing the question."
        if last.stop_reason == "max_tokens":
            return _text_of(last) + "\n\n[Output truncated: hit max_tokens]"
        return _text_of(last)

    def report(self) -> str:
        return self.ask(REPORT_PROMPT)
