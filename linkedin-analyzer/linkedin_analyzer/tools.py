"""Tools the agent calls to explore your posts.

The numbers are computed here in Python, so Claude reasons over exact stats
instead of estimating them from raw text.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean, median

from anthropic import beta_tool

from .loader import Post

SORT_KEYS = {
    "date": lambda p: p.date,
    "impressions": lambda p: p.impressions or 0,
    "engagements": lambda p: p.engagements or 0,
    "engagement_rate": lambda p: p.engagement_rate or 0.0,
    "length": lambda p: p.word_count,
}

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _length_bucket(p: Post) -> str:
    if p.word_count < 50:
        return "short (<50 words)"
    if p.word_count < 150:
        return "medium (50-149 words)"
    if p.word_count < 300:
        return "long (150-299 words)"
    return "very long (300+ words)"


DIMENSIONS = {
    "weekday": lambda p: [WEEKDAYS[p.date.weekday()]],
    "hour": lambda p: [f"{p.date.hour:02d}:00"],
    "month": lambda p: [p.date.strftime("%Y-%m")],
    "length_bucket": lambda p: [_length_bucket(p)],
    "has_media": lambda p: ["with media" if p.has_media else "no media"],
    "has_link": lambda p: ["with link" if p.has_link else "no link"],
    "ends_with_question": lambda p: ["question" if p.text.rstrip().endswith("?") else "no question"],
    "hashtag": lambda p: p.hashtags or ["(no hashtags)"],
}


def _summary(p: Post, preview_chars: int = 280) -> dict:
    text = p.text if len(p.text) <= preview_chars else p.text[:preview_chars] + "…"
    return {
        "id": p.id,
        "date": p.date.strftime("%Y-%m-%d %H:%M"),
        "words": p.word_count,
        "impressions": p.impressions,
        "engagements": p.engagements,
        "engagement_rate": round(p.engagement_rate, 4) if p.engagement_rate is not None else None,
        "has_media": p.has_media,
        "hashtags": p.hashtags,
        "preview": text,
    }


def _avg(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def build_tools(posts: list[Post]) -> list:
    """Create the tool functions, bound to this set of posts."""

    def in_range(p: Post, start_date: str, end_date: str) -> bool:
        if start_date and p.date < datetime.fromisoformat(start_date):
            return False
        if end_date and p.date > datetime.fromisoformat(end_date + "T23:59:59"):
            return False
        return True

    @beta_tool
    def dataset_overview() -> str:
        """Get a high-level overview of the post dataset: count, date range,
        posting cadence per month, whether impressions/engagement metrics are
        available, and summary metric statistics. Call this first."""
        if not posts:
            return json.dumps({"post_count": 0})
        with_metrics = [p for p in posts if p.impressions is not None]
        per_month = Counter(p.date.strftime("%Y-%m") for p in posts)
        words = [p.word_count for p in posts]
        overview = {
            "post_count": len(posts),
            "first_post": posts[0].date.strftime("%Y-%m-%d"),
            "last_post": posts[-1].date.strftime("%Y-%m-%d"),
            "posts_per_month": dict(sorted(per_month.items())),
            "median_words": median(words),
            "share_with_media": round(sum(p.has_media for p in posts) / len(posts), 3),
            "top_hashtags": Counter(h for p in posts for h in p.hashtags).most_common(15),
            "posts_with_metrics": len(with_metrics),
        }
        if with_metrics:
            imps = [p.impressions for p in with_metrics]
            engs = [p.engagements for p in with_metrics if p.engagements is not None]
            overview.update(
                {
                    "median_impressions": median(imps),
                    "mean_impressions": round(mean(imps), 1),
                    "median_engagements": median(engs) if engs else None,
                    "mean_engagement_rate": _avg([p.engagement_rate for p in with_metrics]),
                }
            )
        else:
            overview["note"] = (
                "No impressions/engagement data loaded; analysis is limited to content, "
                "timing and cadence. Load the Creator analytics .xlsx for performance data."
            )
        return json.dumps(overview, default=str)

    @beta_tool
    def list_posts(
        sort_by: str = "date",
        descending: bool = True,
        limit: int = 10,
        offset: int = 0,
        start_date: str = "",
        end_date: str = "",
        contains: str = "",
    ) -> str:
        """List posts with a text preview and metrics, sorted and filtered.

        Args:
            sort_by: One of "date", "impressions", "engagements", "engagement_rate", "length".
            descending: Sort highest/newest first when true.
            limit: Max posts to return (1-50).
            offset: Number of posts to skip, for paging.
            start_date: Only posts on/after this date, YYYY-MM-DD. Empty for no bound.
            end_date: Only posts on/before this date, YYYY-MM-DD. Empty for no bound.
            contains: Case-insensitive substring the post text must contain. Empty for all.
        """
        if sort_by not in SORT_KEYS:
            return f"Error: sort_by must be one of {sorted(SORT_KEYS)}"
        try:
            selected = [
                p
                for p in posts
                if in_range(p, start_date, end_date)
                and (not contains or contains.lower() in p.text.lower())
            ]
        except ValueError as e:
            return f"Error: bad date ({e}); use YYYY-MM-DD"
        selected.sort(key=SORT_KEYS[sort_by], reverse=descending)
        limit = max(1, min(limit, 50))
        page = selected[offset : offset + limit]
        return json.dumps(
            {"total_matching": len(selected), "posts": [_summary(p) for p in page]}
        )

    @beta_tool
    def get_post(post_id: str) -> str:
        """Get the full text and all fields of one post.

        Args:
            post_id: The post id from list_posts.
        """
        for p in posts:
            if p.id == post_id:
                data = _summary(p, preview_chars=10**9)
                data["text"] = data.pop("preview")
                data.update({"url": p.url, "shared_url": p.shared_url, "media_url": p.media_url})
                return json.dumps(data)
        return f"Error: no post with id {post_id!r}"

    @beta_tool
    def group_stats(dimension: str, min_posts: int = 1) -> str:
        """Compare post groups: count and average impressions, engagements and
        engagement rate per group. Use it to find what correlates with performance.

        Args:
            dimension: One of "weekday", "hour", "month", "length_bucket", "has_media",
                "has_link", "ends_with_question", "hashtag".
            min_posts: Hide groups with fewer posts than this (small groups are noisy).
        """
        if dimension not in DIMENSIONS:
            return f"Error: dimension must be one of {sorted(DIMENSIONS)}"
        groups: dict[str, list[Post]] = defaultdict(list)
        for p in posts:
            for key in DIMENSIONS[dimension](p):
                groups[key].append(p)
        rows = [
            {
                "group": key,
                "posts": len(ps),
                "avg_impressions": _avg([p.impressions for p in ps]),
                "avg_engagements": _avg([p.engagements for p in ps]),
                "avg_engagement_rate": _avg([p.engagement_rate for p in ps]),
            }
            for key, ps in groups.items()
            if len(ps) >= min_posts
        ]
        rows.sort(key=lambda r: (r["avg_impressions"] or 0, r["posts"]), reverse=True)
        return json.dumps({"dimension": dimension, "groups": rows})

    return [dataset_overview, list_posts, get_post, group_stats]
