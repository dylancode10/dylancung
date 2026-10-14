# LinkedIn Post Analyzer

A Claude-powered agent that reads your LinkedIn posts and tells you what's working:
top performers and what they share, content themes, voice and format, best timing,
concrete recommendations, and new post ideas. You can also ask it follow-up questions.

It uses LinkedIn's **official data export**, so there's no scraping and no LinkedIn API access needed.

## How it works

```
Shares.csv (+ analytics .xlsx)  ->  loader.py  ->  tools.py  <->  Claude (agent.py)  ->  report.md
```

- `loader.py` parses your posts and (optionally) merges in impressions and engagements.
- `tools.py` gives Claude four tools that compute exact numbers in Python:
  `dataset_overview`, `list_posts` (sort/filter/search), `get_post` (full text),
  and `group_stats` (compare by weekday, hour, month, length, media, links, questions, hashtag).
- `agent.py` runs Claude in a tool-use loop. Claude decides what to look at, reads the
  best and worst posts, and writes up findings backed by the numbers.

## 1. Get your data

**Posts (required).** On LinkedIn, go to *Settings → Data privacy → Get a copy of your data*,
choose *Posts* (or the full archive), and download the `.zip` when it's ready. It contains `Shares.csv`.

**Performance metrics (optional, recommended).** Go to your profile's *Analytics → Content*,
pick the date range (up to 365 days), and click *Export*. You get an `.xlsx` whose
`TOP POSTS` sheet has impressions and engagements per post. Without it the agent can still
analyze content, themes and cadence, but not reach or engagement.

## 2. Install

```bash
cd linkedin-analyzer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## 3. Run

```bash
# Full report -> linkedin_report.md
python -m linkedin_analyzer ~/Downloads/Basic_LinkedInDataExport.zip --analytics ~/Downloads/Content_2026.xlsx

# Report, then keep chatting
python -m linkedin_analyzer path/to/export --analytics Content.xlsx --chat

# One question only
python -m linkedin_analyzer path/to/Shares.csv --ask "Which hooks get the most engagement?"

# Try it on the bundled sample
python -m linkedin_analyzer sample_data -v
```

The export argument can be the `.zip`, the unzipped folder, or `Shares.csv` itself.
Use `-v` to see which tools the agent calls.

## Tests

```bash
pip install pytest
python -m pytest -q
```

The tests cover parsing, analytics merging and the tools; they don't call the API.

## Notes

- Model: `claude-opus-5-5` at `high` effort. Change `MODEL` in `agent.py` if you want a cheaper
  model, such as `claude-sonnet-5-5`.
- Analytics rows are matched to posts by post ID, falling back to the publish date when exactly
  one post was published that day. The CLI prints how many posts it matched.
- Your posts are sent to the Anthropic API for analysis. Nothing is sent anywhere else.
