# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PMCompare is a single-file Python 3 tool that compares two cycling power meters by reading Garmin `.fit` files and plotting their power-vs-time series. All logic lives in `pm_compare.py`; there is no package layout, no test suite, and no lint config.

## Commands

Setup (creates `.venv` and installs deps):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the CLI:

```bash
python3 pm_compare.py first_meter.fit second_meter.fit [--label-a NAME] [--label-b NAME] [--output chart.png]
```

Run the Tkinter UI (also opens automatically when no positional args are given):

```bash
python3 pm_compare.py --ui
```

`run_pmcompare_ui.sh` is a convenience wrapper that creates `.venv` on first run and launches the UI.

Build a standalone binary locally (matches CI):

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name pmcompare pm_compare.py
```

## Architecture

The pipeline in `compare_fit_files` is the core flow and the place to extend behavior:

1. `parse_fit_power_series` — iterates `record` messages from `fitparse.FitFile`, keeps only entries that have **both** `timestamp` and `power`. Files with zero qualifying records raise `ValueError`.
2. `align_series_by_timestamp` — intersects the two series by absolute timestamp, then re-bases `elapsed_seconds` to the overlap start (`t = 0`). Non-overlapping files raise `ValueError`.
3. `truncate_series_to_duration` — applied after alignment to clip a trailing sample that may sit just past `overlap_end` on one side, so both series end at the same elapsed duration.
4. `plot_power_series` — renders with matplotlib; if `output` is `None` it calls `plt.show()`, otherwise it writes the figure to disk via `fig.savefig`.

The `PowerSeries` dataclass carries `timestamps`, `elapsed_seconds`, and `power_watts` as parallel lists — keep them in lockstep when adding transforms.

The Tkinter UI (`launch_ui`) is a thin wrapper that collects paths/labels into `StringVar`s and calls `compare_fit_files`. `tkinter` is imported lazily inside `launch_ui` / `browse_*` so the CLI path still works on Python builds without Tk.

## Release process

Releases are produced by `.github/workflows/release.yml`, triggered by pushing a tag matching `X.Y.Z`. The workflow:

- Validates the tag format and that the tagged commit is reachable from `origin/main` (release tags must be on main).
- Builds with PyInstaller (`--onefile --windowed`) on `windows-latest` and `ubuntu-latest`, renaming artifacts to `pmcompare-<version>-windows.exe` and `pmcompare-<version>-linux`.
- Publishes a GitHub Release with auto-generated notes and both binaries attached.

When changing build flags or adding runtime data files, update both the workflow and any local build instructions together — the workflow is the source of truth for what ships.

## Conventions

- `*.fit` is gitignored; do not commit recorded ride data. Use small synthetic or local-only files for manual testing.
- Errors that should reach the user are raised as `ValueError`/`OSError` and caught at the CLI/UI boundary (`main`, `run_comparison`) — keep new failure modes in that pattern rather than calling `sys.exit` from inner functions.
