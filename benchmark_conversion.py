#!/usr/bin/env python3
"""
Output conversion benchmark for comfyui-modal.

Measures latency and size impact of each output mode using real
generated PNG images.  Takes one or more PNG files from a local
input folder, converts each using every supported output mode,
and writes results to CSV/JSON.
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

# Add the current directory to path so we can import output_converter
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from output_converter import convert_image_bytes


MODES = [
    # (output_format, quality, webp_lossless_compression, label)
    ("original",         75,  "balanced", "Original / PNG"),
    ("webp_lossless",    None, "fast",     "WebP Lossless (Fast)"),
    ("webp_lossless",    None, "balanced", "WebP Lossless (Balanced)"),
    ("webp_lossless",    None, "max",      "WebP Lossless (Max Compression)"),
    ("webp_lossy",       25,   None,       "WebP Lossy (Q25)"),
    ("webp_lossy",       50,   None,       "WebP Lossy (Q50)"),
    ("webp_lossy",       75,   None,       "WebP Lossy (Q75)"),
    ("webp_lossy",       90,   None,       "WebP Lossy (Q90)"),
    ("jpeg",             25,   None,       "JPEG (Q25)"),
    ("jpeg",             50,   None,       "JPEG (Q50)"),
    ("jpeg",             75,   None,       "JPEG (Q75)"),
    ("jpeg",             90,   None,       "JPEG (Q90)"),
]


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark output format conversion for comfyui-modal",
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default=".",
        help="Directory containing PNG files to benchmark (default: current dir)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to save converted files and results (default: <input_dir>/_benchmark_output)",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json", "both"],
        default="both",
        help="Output format for results (default: both)",
    )
    args = parser.parse_args()

    input_path = Path(args.input_dir)
    if not input_path.is_dir():
        print(f"ERROR: not a directory: {input_path}")
        sys.exit(1)

    if args.output_dir:
        out_base = Path(args.output_dir)
    else:
        out_base = input_path / "_benchmark_output"
    images_out = out_base / "images"
    _ensure_dir(str(images_out))

    png_files = sorted(input_path.glob("*.png"))
    if not png_files:
        png_files = sorted(input_path.glob("*.PNG"))
    if not png_files:
        print(f"No PNG files found in {input_path}")
        sys.exit(1)

    print(f"Found {len(png_files)} PNG file(s) in {input_path}")
    print(f"Output directory: {out_base}")
    print()

    try:
        from PIL import Image as PILImage
    except ImportError:
        print("WARNING: Pillow not installed. Only 'original' mode will work.")
        PILImage = None

    results: list[dict] = []

    for fp in png_files:
        raw = fp.read_bytes()
        name = fp.stem
        ext_in = fp.suffix.lower()

        if PILImage:
            try:
                img = PILImage.open(fp)
                w, h = img.size
            except Exception:
                w, h = 0, 0
        else:
            w, h = 0, 0

        for fmt, qual, wlc, label in MODES:
            result = convert_image_bytes(
                raw,
                output_format=fmt,
                quality=qual or 75,
                webp_lossless_compression=wlc or "balanced",
            )

            out_ext = result["file_ext"].lstrip(".")
            safe_label = label.replace(" ", "_").replace("/", "-").replace("(", "").replace(")", "")
            out_name = f"{name}_{safe_label}.{out_ext}"
            out_path = images_out / out_name

            # Avoid overwriting
            counter = 1
            while out_path.exists():
                out_name = f"{name}_{safe_label}_{counter}.{out_ext}"
                out_path = images_out / out_name
                counter += 1

            with open(out_path, "wb") as f:
                f.write(result["bytes"])

            ratio = (
                round(result["returned_size_bytes"] / max(1, result["original_size_bytes"]), 4)
                if result["original_size_bytes"] > 0
                else 0
            )

            row = {
                "filename": fp.name,
                "width": w,
                "height": h,
                "input_size_bytes": result["original_size_bytes"],
                "mode": fmt,
                "quality": result.get("quality"),
                "webp_lossless_compression": result.get("webp_lossless_compression"),
                "label": label,
                "output_size_bytes": result["returned_size_bytes"],
                "compression_ratio": ratio,
                "conversion_time_ms": result["conversion_time_ms"],
                "fallback": result.get("fallback", False),
                "error": result.get("error") or "",
                "output_path": str(out_path),
            }
            results.append(row)

            status = "OK"
            if result.get("fallback"):
                status = "FALLBACK"
            elif result.get("error"):
                status = f"ERR: {result['error']}"
            print(
                f"  {label:40s}  "
                f"in={result['original_size_bytes']:>8d}B  "
                f"out={result['returned_size_bytes']:>8d}B  "
                f"ratio={ratio:.3f}  "
                f"time={result['conversion_time_ms']:>6.1f}ms  "
                f"{status}"
            )

    # Write CSV
    if args.format in ("csv", "both"):
        csv_path = out_base / "benchmark_results.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys() if results else [])
            writer.writeheader()
            writer.writerows(results)
        print(f"\nCSV written: {csv_path}")

    # Write JSON
    if args.format in ("json", "both"):
        json_path = out_base / "benchmark_results.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"JSON written: {json_path}")

    # Summary
    if results:
        modes_seen: dict[str, list[float]] = {}
        for r in results:
            modes_seen.setdefault(r["mode"], []).append(r["conversion_time_ms"])
        print("\nAverage conversion time by mode:")
        for mode, times in sorted(modes_seen.items()):
            avg = sum(times) / len(times)
            print(f"  {mode:20s}: {avg:7.1f} ms avg ({len(times)} samples)")

    print("\nDone.")


if __name__ == "__main__":
    main()
