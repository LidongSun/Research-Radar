# Repository Guidelines

## Project Structure & Module Organization

Lab Radar is a small local-first Python application. The entry point is `main.py`, which delegates to `lab_radar/cli.py`. Core modules live in `lab_radar/`: configuration loading, source fetchers, scoring, SQLite persistence, report generation, optional LLM enrichment, and the local web dashboard. Runtime data is stored in `data/lab_radar.db`; generated daily reports are written to `reports/YYYY-MM-DD.md`. User-facing defaults live in `config.yaml`. The `run_dashboard.ps1` script is a Windows helper for starting the dashboard.

## Build, Test, and Development Commands

Run commands from the repository root.

```powershell
python main.py run-daily
python main.py run-daily --date 2026-05-29
python main.py run-daily --use-llm
python main.py show-config
python main.py serve --host 127.0.0.1 --port 8765
.\run_dashboard.ps1 8766
```

`run-daily` fetches, scores, stores, and reports recent research items. `show-config` prints the parsed configuration as JSON. `serve` starts the local dashboard; the PowerShell wrapper starts it on port `8765` unless another port is provided.

## Coding Style & Naming Conventions

Use Python 3 style with four-space indentation, type hints where they clarify public functions, and small modules with focused responsibilities. Follow existing naming: `snake_case` for functions, variables, files, and command names; `PascalCase` for classes such as `RadarStore`. Keep CLI behavior in `lab_radar/cli.py`, persistence in `lab_radar/db.py`, source integrations in `lab_radar/sources.py`, and presentation/reporting in `lab_radar/web.py` or `lab_radar/reporter.py`.

## Testing Guidelines

No test suite is currently checked in. When adding tests, prefer `pytest` and place tests under `tests/` with names like `test_scoring.py` or `test_config.py`. Focus first on deterministic units: config parsing, scoring rules, de-duplication, report formatting, and database writes against a temporary SQLite file. Until tests exist, verify changes with `python main.py show-config`, `python main.py run-daily`, and a dashboard smoke test.

## Commit & Pull Request Guidelines

This folder does not currently include Git history, so use concise, imperative commit subjects such as `Add dashboard filters` or `Fix report date handling`. Pull requests should include a short summary, validation commands run, screenshots for dashboard changes, and notes for any schema, configuration, or environment variable changes.

## Security & Configuration Tips

Do not commit API keys or private research data. LLM support is optional and configured through environment variables: `LAB_RADAR_LLM_BASE_URL`, `LAB_RADAR_LLM_API_KEY`, and `LAB_RADAR_LLM_MODEL`. Treat `data/` and generated `reports/` as local artifacts unless explicitly intended for sharing.
