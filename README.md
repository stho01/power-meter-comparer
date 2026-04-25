# PMCompare

Small Python 3 tool for comparing two cycling power meters using Garmin `.fit` files.

It extracts `timestamp` + `power` from each file's `record` messages and plots both datasets as line charts:

- x-axis: elapsed time (minutes)
- y-axis: power (watts)

## Install Standalone App (No Python Needed)

Download the latest release assets from GitHub Releases.

### Windows

1. Download `pmcompare-<version>-windows.exe`.
2. Place it in any folder (for example `Downloads` or `Desktop`).
3. Double-click the `.exe` to launch the UI.

If Windows SmartScreen warns about an unknown publisher, click `More info` then `Run anyway`.

### Linux

1. Download `pmcompare-<version>-linux`.
2. Move it to a folder you keep apps in (for example `~/bin/pmcompare`).
3. Make it executable:

```bash
chmod +x pmcompare-<version>-linux
```

4. Run it:

```bash
./pmcompare-<version>-linux
```

Optional: rename it to `pmcompare` and place it in a directory on your `PATH` for easier launching.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python3 pm_compare.py first_meter.fit second_meter.fit
```

Or launch a small file-picker UI and select the two FIT files from your file explorer:

```bash
python3 pm_compare.py --ui
```

In the UI, you can optionally choose an output image path to save the comparison chart directly.

Running with no positional file arguments also opens the UI:

```bash
python3 pm_compare.py
```

Optional flags:

```bash
python3 pm_compare.py first_meter.fit second_meter.fit \
  --label-a "Crank" \
  --label-b "Pedal" \
  --output comparison.png
```

- `--label-a`, `--label-b`: custom legend names
- `--output`: save chart to image instead of opening a window

## Notes

- The script uses FIT `timestamp` values and keeps only the overlapping time window between the two files.
- The x-axis starts at the first overlapping timestamp (`t = 0`) to reduce start/end skew.
- If a FIT file has no `record` entries with both `timestamp` and `power`, the tool exits with an error.
