# Lab Radar

Lab Radar is a local-first research intelligence assistant for AI and robotics researchers. It watches papers, open-source projects, and model hubs, scores them against your research profile, and generates a compact daily Markdown report.

## Current MVP

- arXiv paper search
- GitHub repository search
- Hugging Face model search
- SQLite cache and de-duplication
- Rule-based relevance, novelty, and action scoring
- Daily Markdown report generation
- Local dashboard with source/category/date filters
- Historical daily report browser
- In-dashboard literature search across open academic indexes
- Saved/read/to-read library views
- Idea backlog for research thoughts and experiment leads
- Save literature search results into a local library
- Optional LLM summarization hook through an OpenAI-compatible API

## Quick Start

```powershell
python main.py run-daily
```

Generated reports are written to:

```text
reports/YYYY-MM-DD.md
```

The default configuration lives in:

```text
config.yaml
```

## Optional LLM Setup

The MVP works without an LLM. To enable LLM summaries, set:

```powershell
$env:LAB_RADAR_LLM_BASE_URL="https://api.openai.com/v1"
$env:LAB_RADAR_LLM_API_KEY="your_api_key"
$env:LAB_RADAR_LLM_MODEL="gpt-4.1-mini"
```

Then run:

```powershell
python main.py run-daily --use-llm
```

## Commands

```powershell
python main.py run-daily
python main.py run-daily --date 2026-05-29
python main.py show-config
python main.py serve
```

## Literature Search

The dashboard includes an integrated literature search panel. It queries open academic indexes directly:

- arXiv
- OpenAlex
- Crossref
- Semantic Scholar
- PubMed
- Europe PMC

It also creates external search links for sources that are useful but restricted or login/API-key dependent:

- Google Scholar
- IEEE Xplore
- ScienceDirect
- ACM Digital Library
- SpringerLink
- Wiley Online Library
- DBLP
- Connected Papers

Open the local dashboard at:

```text
http://127.0.0.1:8765
```

On Windows, you can also keep the dashboard running in a visible terminal:

```powershell
.\run_dashboard.ps1
```

If port `8765` is already occupied, use another port:

```powershell
.\run_dashboard.ps1 8766
```

## Notes

This first version intentionally favors a small, reliable local pipeline over a large dashboard. The next stage is to add a FastAPI + React interface for reading, filtering, saving, and building an idea backlog.
