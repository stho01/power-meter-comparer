#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from fitparse import FitFile


@dataclass
class PowerSeries:
    label: str
    timestamps: list[datetime]
    elapsed_seconds: list[float]
    power_watts: list[float]


def parse_fit_power_series(file_path: Path, label: str | None = None) -> PowerSeries:
    fit_file = FitFile(str(file_path))

    points: list[tuple[datetime, float]] = []
    for message in fit_file.get_messages("record"):
        fields = {field.name: field.value for field in message}
        timestamp = fields.get("timestamp")
        power = fields.get("power")

        if timestamp is None or power is None:
            continue

        try:
            points.append((timestamp, float(power)))
        except (TypeError, ValueError):
            continue

    if not points:
        raise ValueError(f"No record messages with timestamp and power in {file_path}")

    points.sort(key=lambda item: item[0])
    start_time = points[0][0]

    elapsed_seconds = [(timestamp - start_time).total_seconds() for timestamp, _ in points]
    timestamps = [timestamp for timestamp, _ in points]
    power_watts = [power for _, power in points]
    return PowerSeries(
        label=label or file_path.stem,
        timestamps=timestamps,
        elapsed_seconds=elapsed_seconds,
        power_watts=power_watts,
    )


def truncate_series_to_duration(series: PowerSeries, max_elapsed_seconds: float) -> PowerSeries:
    truncated_points = [
        (timestamp, elapsed, power)
        for timestamp, elapsed, power in zip(series.timestamps, series.elapsed_seconds, series.power_watts)
        if elapsed <= max_elapsed_seconds
    ]

    if not truncated_points:
        raise ValueError(f"No samples remain for {series.label} after truncation")

    timestamps, elapsed_seconds, power_watts = zip(*truncated_points)
    return PowerSeries(
        label=series.label,
        timestamps=list(timestamps),
        elapsed_seconds=list(elapsed_seconds),
        power_watts=list(power_watts),
    )


def align_series_by_timestamp(first: PowerSeries, second: PowerSeries) -> tuple[PowerSeries, PowerSeries, float]:
    overlap_start = max(first.timestamps[0], second.timestamps[0])
    overlap_end = min(first.timestamps[-1], second.timestamps[-1])

    if overlap_start >= overlap_end:
        raise ValueError("FIT files do not overlap in time; cannot align by timestamp")

    def trim_to_overlap(series: PowerSeries) -> PowerSeries:
        aligned_points = [
            (timestamp, power)
            for timestamp, power in zip(series.timestamps, series.power_watts)
            if overlap_start <= timestamp <= overlap_end
        ]

        if not aligned_points:
            raise ValueError(f"No overlapping samples remain for {series.label}")

        timestamps, power_watts = zip(*aligned_points)
        elapsed_seconds = [(timestamp - overlap_start).total_seconds() for timestamp in timestamps]
        return PowerSeries(
            label=series.label,
            timestamps=list(timestamps),
            elapsed_seconds=list(elapsed_seconds),
            power_watts=list(power_watts),
        )

    aligned_first = trim_to_overlap(first)
    aligned_second = trim_to_overlap(second)
    common_duration_seconds = (overlap_end - overlap_start).total_seconds()
    return aligned_first, aligned_second, common_duration_seconds


def plot_power_series(first: PowerSeries, second: PowerSeries, output: Path | None = None) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(
        [seconds / 60.0 for seconds in first.elapsed_seconds],
        first.power_watts,
        label=first.label,
        linewidth=1.1,
    )
    ax.plot(
        [seconds / 60.0 for seconds in second.elapsed_seconds],
        second.power_watts,
        label=second.label,
        linewidth=1.1,
    )

    ax.set_title("Power Meter Comparison")
    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Power (watts)")
    ax.grid(True, alpha=0.25)
    ax.legend()

    plt.tight_layout()

    if output is None:
        plt.show()
    else:
        fig.savefig(output, dpi=150)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two Garmin FIT files by plotting power over time.",
    )
    parser.add_argument("fit_a", nargs="?", type=Path, help="Path to first .fit file")
    parser.add_argument("fit_b", nargs="?", type=Path, help="Path to second .fit file")
    parser.add_argument("--label-a", help="Legend label for first file")
    parser.add_argument("--label-b", help="Legend label for second file")
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Open a file-picker UI to choose FIT files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="If provided, write chart to this image file instead of opening a window",
    )
    return parser


def validate_fit_path(file_path: Path) -> None:
    if not file_path.exists():
        raise ValueError(f"File does not exist: {file_path}")
    if file_path.suffix.lower() != ".fit":
        raise ValueError(f"Expected a .fit file: {file_path}")


def compare_fit_files(
    fit_a: Path,
    fit_b: Path,
    label_a: str | None = None,
    label_b: str | None = None,
    output: Path | None = None,
) -> Path | None:
    validate_fit_path(fit_a)
    validate_fit_path(fit_b)

    series_a = parse_fit_power_series(fit_a, label_a)
    series_b = parse_fit_power_series(fit_b, label_b)

    series_a, series_b, common_duration_seconds = align_series_by_timestamp(series_a, series_b)

    # Keep exact common duration endpoint even when one side has a trailing sample past overlap_end.
    series_a = truncate_series_to_duration(series_a, common_duration_seconds)
    series_b = truncate_series_to_duration(series_b, common_duration_seconds)

    print(f"Loaded {len(series_a.power_watts)} points from {fit_a}")
    print(f"Loaded {len(series_b.power_watts)} points from {fit_b}")
    print(f"Using common duration: {common_duration_seconds / 60.0:.2f} minutes")

    plot_power_series(series_a, series_b, output)
    if output is not None:
        print(f"Saved chart to {output}")
    return output


def browse_fit_file(target_var) -> None:
    from tkinter import filedialog

    selected_path = filedialog.askopenfilename(
        title="Select FIT file",
        filetypes=[("FIT files", "*.fit"), ("All files", "*.*")],
    )
    if selected_path:
        target_var.set(selected_path)


def browse_output_file(target_var) -> None:
    from tkinter import filedialog

    selected_path = filedialog.asksaveasfilename(
        title="Save comparison image",
        defaultextension=".png",
        filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg;*.jpeg"), ("All files", "*.*")],
    )
    if selected_path:
        target_var.set(selected_path)


def launch_ui() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ModuleNotFoundError as exc:
        raise RuntimeError("Tkinter is not available. Use CLI arguments instead of --ui.") from exc

    root = tk.Tk()
    root.title("PMCompare")
    root.resizable(False, False)
    root.columnconfigure(1, weight=1)

    fit_a_var = tk.StringVar()
    fit_b_var = tk.StringVar()
    label_a_var = tk.StringVar()
    label_b_var = tk.StringVar()
    output_var = tk.StringVar()

    tk.Label(root, text="First FIT file").grid(row=0, column=0, padx=8, pady=6, sticky="w")
    tk.Entry(root, textvariable=fit_a_var, width=52).grid(row=0, column=1, padx=8, pady=6, sticky="ew")
    tk.Button(root, text="Browse...", command=lambda: browse_fit_file(fit_a_var)).grid(
        row=0,
        column=2,
        padx=8,
        pady=6,
    )

    tk.Label(root, text="Second FIT file").grid(row=1, column=0, padx=8, pady=6, sticky="w")
    tk.Entry(root, textvariable=fit_b_var, width=52).grid(row=1, column=1, padx=8, pady=6, sticky="ew")
    tk.Button(root, text="Browse...", command=lambda: browse_fit_file(fit_b_var)).grid(
        row=1,
        column=2,
        padx=8,
        pady=6,
    )

    tk.Label(root, text="Label A (optional)").grid(row=2, column=0, padx=8, pady=6, sticky="w")
    tk.Entry(root, textvariable=label_a_var, width=52).grid(row=2, column=1, padx=8, pady=6, sticky="ew")

    tk.Label(root, text="Label B (optional)").grid(row=3, column=0, padx=8, pady=6, sticky="w")
    tk.Entry(root, textvariable=label_b_var, width=52).grid(row=3, column=1, padx=8, pady=6, sticky="ew")

    tk.Label(root, text="Output image (optional)").grid(row=4, column=0, padx=8, pady=6, sticky="w")
    tk.Entry(root, textvariable=output_var, width=52).grid(row=4, column=1, padx=8, pady=6, sticky="ew")
    tk.Button(root, text="Save as...", command=lambda: browse_output_file(output_var)).grid(
        row=4,
        column=2,
        padx=8,
        pady=6,
    )

    def run_comparison() -> None:
        fit_a_input = fit_a_var.get().strip()
        fit_b_input = fit_b_var.get().strip()
        if not fit_a_input or not fit_b_input:
            messagebox.showerror("Comparison failed", "Please choose both FIT files.")
            return

        fit_a = Path(fit_a_input)
        fit_b = Path(fit_b_input)
        label_a = label_a_var.get().strip() or None
        label_b = label_b_var.get().strip() or None
        output = Path(output_var.get().strip()) if output_var.get().strip() else None

        try:
            compare_fit_files(
                fit_a=fit_a,
                fit_b=fit_b,
                label_a=label_a,
                label_b=label_b,
                output=output,
            )
            if output is not None:
                messagebox.showinfo("Comparison complete", f"Saved chart to {output}")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Comparison failed", str(exc))

    tk.Button(root, text="Compare", command=run_comparison, width=18).grid(
        row=5,
        column=1,
        padx=8,
        pady=12,
        sticky="e",
    )

    root.mainloop()
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.ui or (args.fit_a is None and args.fit_b is None):
        return launch_ui()

    if args.fit_a is None or args.fit_b is None:
        parser.error("Please provide both FIT files, or run with --ui")

    try:
        compare_fit_files(
            fit_a=args.fit_a,
            fit_b=args.fit_b,
            label_a=args.label_a,
            label_b=args.label_b,
            output=args.output,
        )
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
