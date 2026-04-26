#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
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


SMOOTHING_CHOICES = [0, 3, 5, 10]


def smooth_power_series(series: PowerSeries, window_seconds: int) -> PowerSeries:
    if window_seconds <= 0:
        return series

    smoothed_powers: list[float] = []
    window_start_index = 0
    for current_index, current_elapsed in enumerate(series.elapsed_seconds):
        window_start = current_elapsed - window_seconds
        while series.elapsed_seconds[window_start_index] < window_start:
            window_start_index += 1
        window_powers = series.power_watts[window_start_index : current_index + 1]
        smoothed_powers.append(sum(window_powers) / len(window_powers))

    return PowerSeries(
        label=series.label,
        timestamps=series.timestamps,
        elapsed_seconds=series.elapsed_seconds,
        power_watts=smoothed_powers,
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

    first_minutes = [seconds / 60.0 for seconds in first.elapsed_seconds]
    second_minutes = [seconds / 60.0 for seconds in second.elapsed_seconds]

    (line_a,) = ax.plot(first_minutes, first.power_watts, label=first.label, linewidth=1.1)
    (line_b,) = ax.plot(second_minutes, second.power_watts, label=second.label, linewidth=1.1)

    ax.set_title("Power Meter Comparison")
    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Power (watts)")
    ax.grid(True, alpha=0.25)
    ax.legend()

    plt.tight_layout()

    if output is None:
        attach_hover_crosshair(fig, ax, first, second, line_a, line_b)
        plt.show()
    else:
        fig.savefig(output, dpi=150)


def linear_interp_sorted(x: float, xs: list[float], ys: list[float]) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    upper = bisect.bisect_left(xs, x)
    x0, x1 = xs[upper - 1], xs[upper]
    y0, y1 = ys[upper - 1], ys[upper]
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def attach_hover_crosshair(
    fig,
    ax,
    first: PowerSeries,
    second: PowerSeries,
    line_a,
    line_b,
) -> None:
    first_minutes = [seconds / 60.0 for seconds in first.elapsed_seconds]
    second_minutes = [seconds / 60.0 for seconds in second.elapsed_seconds]
    first_powers = list(first.power_watts)
    second_powers = list(second.power_watts)

    vline = ax.axvline(
        first_minutes[0],
        color="gray",
        linewidth=0.8,
        alpha=0.6,
        visible=False,
        animated=True,
    )

    def make_label(line):
        return ax.annotate(
            "",
            xy=(0, 0),
            xytext=(8, 0),
            textcoords="offset points",
            color=line.get_color(),
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": line.get_color(), "alpha": 0.9},
            visible=False,
            animated=True,
        )

    label_a = make_label(line_a)
    label_b = make_label(line_b)
    artists = (vline, label_a, label_b)

    background: list = [None]

    def on_draw(_event) -> None:
        background[0] = fig.canvas.copy_from_bbox(ax.bbox)

    def render() -> None:
        if background[0] is None:
            return
        fig.canvas.restore_region(background[0])
        for artist in artists:
            if artist.get_visible():
                ax.draw_artist(artist)
        fig.canvas.blit(ax.bbox)

    def hide() -> None:
        if any(artist.get_visible() for artist in artists):
            for artist in artists:
                artist.set_visible(False)
            render()

    def on_move(event) -> None:
        if event.inaxes is not ax or event.xdata is None:
            hide()
            return

        x_minutes = event.xdata
        power_a = linear_interp_sorted(x_minutes, first_minutes, first_powers)
        power_b = linear_interp_sorted(x_minutes, second_minutes, second_powers)

        vline.set_xdata([x_minutes, x_minutes])
        vline.set_visible(True)

        label_a.xy = (x_minutes, power_a)
        label_a.set_text(f"{first.label}: {power_a:.0f} W")
        label_a.set_visible(True)

        label_b.xy = (x_minutes, power_b)
        label_b.set_text(f"{second.label}: {power_b:.0f} W")
        label_b.set_visible(True)

        render()

    def on_leave(_event) -> None:
        hide()

    fig.canvas.mpl_connect("draw_event", on_draw)
    fig.canvas.mpl_connect("motion_notify_event", on_move)
    fig.canvas.mpl_connect("axes_leave_event", on_leave)


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
    parser.add_argument(
        "--smoothing",
        type=int,
        choices=SMOOTHING_CHOICES,
        default=0,
        help="Apply N-second trailing rolling average to both series (0 disables smoothing)",
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
    smoothing_seconds: int = 0,
) -> Path | None:
    validate_fit_path(fit_a)
    validate_fit_path(fit_b)

    if smoothing_seconds not in SMOOTHING_CHOICES:
        raise ValueError(f"Smoothing must be one of {SMOOTHING_CHOICES}, got {smoothing_seconds}")

    series_a = parse_fit_power_series(fit_a, label_a)
    series_b = parse_fit_power_series(fit_b, label_b)

    series_a, series_b, common_duration_seconds = align_series_by_timestamp(series_a, series_b)

    # Keep exact common duration endpoint even when one side has a trailing sample past overlap_end.
    series_a = truncate_series_to_duration(series_a, common_duration_seconds)
    series_b = truncate_series_to_duration(series_b, common_duration_seconds)

    series_a = smooth_power_series(series_a, smoothing_seconds)
    series_b = smooth_power_series(series_b, smoothing_seconds)

    print(f"Loaded {len(series_a.power_watts)} points from {fit_a}")
    print(f"Loaded {len(series_b.power_watts)} points from {fit_b}")
    print(f"Using common duration: {common_duration_seconds / 60.0:.2f} minutes")
    if smoothing_seconds > 0:
        print(f"Applied {smoothing_seconds}s rolling average smoothing")

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
    smoothing_var = tk.StringVar(value="None")
    smoothing_options = {"None": 0, "3 seconds": 3, "5 seconds": 5, "10 seconds": 10}

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

    tk.Label(root, text="Smoothing").grid(row=5, column=0, padx=8, pady=6, sticky="w")
    tk.OptionMenu(root, smoothing_var, *smoothing_options.keys()).grid(
        row=5,
        column=1,
        padx=8,
        pady=6,
        sticky="w",
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
        smoothing_seconds = smoothing_options[smoothing_var.get()]

        try:
            compare_fit_files(
                fit_a=fit_a,
                fit_b=fit_b,
                label_a=label_a,
                label_b=label_b,
                output=output,
                smoothing_seconds=smoothing_seconds,
            )
            if output is not None:
                messagebox.showinfo("Comparison complete", f"Saved chart to {output}")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Comparison failed", str(exc))

    tk.Button(root, text="Compare", command=run_comparison, width=18).grid(
        row=6,
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
            smoothing_seconds=args.smoothing,
        )
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
