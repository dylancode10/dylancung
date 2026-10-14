import json
import zipfile
from pathlib import Path

from openpyxl import Workbook

from linkedin_analyzer.loader import load_analytics, load_shares, merge_analytics
from linkedin_analyzer.tools import build_tools

SAMPLE = Path(__file__).parent.parent / "sample_data" / "Shares.csv"


def make_analytics(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "TOP POSTS"
    ws.append(["Maximum of 50 posts available to include in this list"])
    ws.append([])
    ws.append(["Post URL", "Post publish date", "Engagements", None, "Post URL", "Post publish date", "Impressions"])
    act = "https://www.linkedin.com/feed/update/urn:li:activity:{}/"
    ws.append([act.format(7100000000000000003), "3/17/2026", 120, None, act.format(7100000000000000003), "3/17/2026", 4000])
    ws.append([act.format(7100000000000000001), "3/2/2026", 40, None, act.format(7100000000000000001), "3/2/2026", 1000])
    # Different id but a unique post on that day -> matched by date.
    ws.append([act.format(9999999999999999999), "5/6/2026", 1, None, act.format(9999999999999999999), "5/6/2026", 90])
    wb.save(path)


def test_load_shares_parses_multiline_posts():
    posts = load_shares(SAMPLE)
    assert len(posts) == 7
    first = posts[0]
    assert first.id == "7100000000000000001"
    assert "Scope ruthlessly" in first.text
    assert first.hashtags == ["buildinpublic", "sideproject"]
    assert posts[1].has_link and not posts[0].has_media


def test_load_shares_from_zip_and_folder(tmp_path):
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(SAMPLE, "Basic_LinkedInDataExport/Shares.csv")
    assert len(load_shares(zip_path)) == 7
    assert len(load_shares(SAMPLE.parent)) == 7


def test_analytics_merge(tmp_path):
    xlsx = tmp_path / "Content.xlsx"
    make_analytics(xlsx)
    posts = load_shares(SAMPLE)
    assert merge_analytics(posts, load_analytics(xlsx)) == 3
    by_id = {p.id: p for p in posts}
    assert by_id["7100000000000000003"].impressions == 4000
    assert by_id["7100000000000000003"].engagement_rate == 0.03
    assert by_id["7100000000000000006"].impressions == 90


def test_tools(tmp_path):
    xlsx = tmp_path / "Content.xlsx"
    make_analytics(xlsx)
    posts = load_shares(SAMPLE)
    merge_analytics(posts, load_analytics(xlsx))
    tools = {t.name: t for t in build_tools(posts)}

    overview = json.loads(tools["dataset_overview"].call({}))
    assert overview["post_count"] == 7
    assert overview["posts_with_metrics"] == 3

    top = json.loads(tools["list_posts"].call({"sort_by": "impressions", "limit": 1}))
    assert top["posts"][0]["id"] == "7100000000000000003"

    career = json.loads(tools["list_posts"].call({"contains": "#career"}))
    assert career["total_matching"] == 2

    full = json.loads(tools["get_post"].call({"post_id": "7100000000000000005"}))
    assert "Approve small PRs fast" in full["text"]

    stats = json.loads(tools["group_stats"].call({"dimension": "weekday"}))
    assert sum(g["posts"] for g in stats["groups"]) == 7

    assert tools["group_stats"].call({"dimension": "nope"}).startswith("Error")
    assert tools["list_posts"].call({"start_date": "bad"}).startswith("Error")
