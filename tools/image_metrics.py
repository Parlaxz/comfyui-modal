#!/usr/bin/env python3
"""Pure local PIL/numpy image quality metrics for two same-size images.

Computes (mean_abs_diff, max_abs_diff, rmse are normalized to [0,1]):
    mean_abs_diff   - mean absolute pixel difference (normalized [0,1])
    max_abs_diff    - maximum absolute pixel difference (normalized [0,1])
    rmse            - root mean square error (normalized [0,1])
    psnr            - peak signal-to-noise ratio in dB (255 peak); null when
                      the images are identical (see 'identical' flag)
    ssim            - structural similarity in [0,1], fixed 11x11 Gaussian win

Also reports image shape/channel checks and produces strict JSON-safe output
(no NaN/Infinity tokens).  No dependency beyond the existing numpy/Pillow
install.

Usage:
    python tools/image_metrics.py --a baseline.png --b candidate.png [--json]
"""

import argparse
import json
import math

import numpy as np
from PIL import Image

PIXEL_MAX = 255.0

SSIM_WIN = 11
SSIM_SIGMA = 1.5
C1 = (0.01 * PIXEL_MAX) ** 2
C2 = (0.03 * PIXEL_MAX) ** 2


def _to_float_grayscale(img: Image.Image) -> np.ndarray:
    """Convert a PIL image to a float 0..255 grayscale array (H, W)."""
    if img.mode == "L":
        arr = np.asarray(img, dtype=np.float32)
    else:
        arr = np.asarray(img.convert("L"), dtype=np.float32)
    return arr


def _to_float_rgb(img: Image.Image) -> np.ndarray:
    """Convert a PIL image to a float 0..255 RGB array (H, W, 3)."""
    if img.mode == "RGB":
        arr = np.asarray(img, dtype=np.float32)
    elif img.mode == "L":
        arr = np.asarray(img, dtype=np.float32)
        arr = np.stack([arr, arr, arr], axis=-1)
    else:
        arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    return arr


def _gaussian_kernel(size: int, sigma: float) -> np.ndarray:
    """Build a 1-D Gaussian kernel, normalized to sum 1.0."""
    ax = np.arange(-(size // 2), size // 2 + 1, dtype=np.float32)
    g = np.exp(-0.5 * (ax / sigma) ** 2)
    g /= g.sum()
    return g


def _ssim(a: np.ndarray, b: np.ndarray, kernel: np.ndarray) -> float:
    """Compute mean SSIM over a grayscale image pair using a fixed window."""
    mu_a = _conv2(a, kernel)
    mu_b = _conv2(b, kernel)
    mu_a_sq = mu_a * mu_a
    mu_b_sq = mu_b * mu_b
    mu_ab = mu_a * mu_b
    sigma_a_sq = _conv2(a * a, kernel) - mu_a_sq
    sigma_b_sq = _conv2(b * b, kernel) - mu_b_sq
    sigma_ab = _conv2(a * b, kernel) - mu_ab
    ssim_map = (
        (2.0 * mu_ab + C1) * (2.0 * sigma_ab + C2)
    ) / ((mu_a_sq + mu_b_sq + C1) * (sigma_a_sq + sigma_b_sq + C2))
    return float(np.mean(ssim_map))


def _conv2(arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable 2-D convolution with edge padding, float32 throughout."""
    a = arr.astype(np.float32, copy=False)
    n = int(kernel.shape[0])
    off = n // 2
    padded = np.pad(a, ((off, off), (off, off)), mode="edge")
    h, w = padded.shape
    temp = np.zeros_like(padded)
    for i in range(h):
        row = padded[i]
        for j in range(w):
            lo = max(0, j - off)
            hi = min(w, j + off + 1)
            k_lo = off - (j - lo)
            temp[i, j] = float(np.dot(row[lo:hi], kernel[k_lo:k_lo + hi - lo]))
    out = np.zeros_like(padded)
    for j in range(w):
        col = temp[:, j]
        for i in range(h):
            lo = max(0, i - off)
            hi = min(h, i + off + 1)
            k_lo = off - (i - lo)
            out[i, j] = float(np.dot(col[lo:hi], kernel[k_lo:k_lo + hi - lo]))
    return out[off:-off, off:-off]


def _shape(a_img: Image.Image, b_img: Image.Image) -> dict:
    return {
        "width": a_img.width,
        "height": a_img.height,
        "a_channels": len(a_img.getbands()),
        "b_channels": len(b_img.getbands()),
        "same_size": (a_img.size == b_img.size),
        "same_channels": (len(a_img.getbands()) == len(b_img.getbands())),
    }


def _is_blank(arr: np.ndarray) -> bool:
    """True when the array has zero variance (uniform image)."""
    return float(np.ptp(arr)) == 0.0


def _finite_ratio(arr: np.ndarray) -> float:
    return float(np.mean(np.isfinite(arr)))


def _nan_ratio(arr: np.ndarray) -> float:
    return float(np.mean(np.isnan(arr)))


def compute_metrics(path_a: str, path_b: str) -> dict:
    """Compute full metrics for two image files.

    Returns a strict JSON-safe dict (no NaN/Infinity).  Never raises for value
    differences; shape mismatches are reported in 'checks' and metrics are
    reported as None when they cannot be meaningfully computed.  Identical
    images yield psnr=None plus 'identical': True.
    """
    with Image.open(path_a) as ia, Image.open(path_b) as ib:
        shape = _shape(ia, ib)
        rgb_a = _to_float_rgb(ia)
        rgb_b = _to_float_rgb(ib)
        gray_a = _to_float_grayscale(ia)
        gray_b = _to_float_grayscale(ib)

    checks = {
        "same_size": shape["same_size"],
        "same_channels": shape["same_channels"],
        "blank_a": _is_blank(rgb_a),
        "blank_b": _is_blank(rgb_b),
        "nan_a": _nan_ratio(rgb_a) > 0.0,
        "nan_b": _nan_ratio(rgb_b) > 0.0,
        "inf_a": _finite_ratio(rgb_a) < 1.0,
        "inf_b": _finite_ratio(rgb_b) < 1.0,
    }

    result = {
        "path_a": path_a,
        "path_b": path_b,
        "shape": shape,
        "checks": checks,
    }

    if not (shape["same_size"] and shape["same_channels"]):
        result.update(
            {
                "mean_abs_diff": None,
                "max_abs_diff": None,
                "rmse": None,
                "psnr": None,
                "ssim": None,
                "identical": False,
            }
        )
        result["valid"] = False
        return result

    diff = np.abs(rgb_a - rgb_b)
    mse = float(np.mean(diff ** 2))
    identical = mse == 0.0

    mean_abs = float(np.mean(diff)) / PIXEL_MAX
    max_abs = float(np.max(diff)) / PIXEL_MAX
    rmse = (math.sqrt(mse) if mse > 0.0 else 0.0) / PIXEL_MAX
    psnr = None if identical else 10.0 * math.log10(PIXEL_MAX ** 2 / mse)
    ssim = _ssim(gray_a, gray_b, _gaussian_kernel(SSIM_WIN, SSIM_SIGMA))

    result.update(
        {
            "mean_abs_diff": mean_abs,
            "max_abs_diff": max_abs,
            "rmse": rmse,
            "psnr": psnr,
            "ssim": ssim,
            "identical": identical,
        }
    )
    result["valid"] = True
    return result


def to_json(result: dict) -> str:
    """Serialize a metrics dict to strict, deterministic JSON (no NaN/Inf)."""
    return json.dumps(result, indent=2, sort_keys=True, allow_nan=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute local image quality metrics for two same-size images."
    )
    parser.add_argument("--a", required=True, help="baseline image path")
    parser.add_argument("--b", required=True, help="candidate image path")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()

    result = compute_metrics(args.a, args.b)
    if args.json:
        print(to_json(result))
        return

    print(f"a: {result['path_a']} ({result['shape']['width']}x{result['shape']['height']})")
    print(f"b: {result['path_b']} ({result['shape']['width']}x{result['shape']['height']})")
    print(f"same_size={result['checks']['same_size']} same_channels={result['checks']['same_channels']}")
    print(f"mean_abs_diff={result['mean_abs_diff']}")
    print(f"max_abs_diff={result['max_abs_diff']}")
    print(f"rmse={result['rmse']}")
    print(f"psnr={result['psnr']}")
    print(f"ssim={result['ssim']}")
    print(f"identical={result['identical']}")
    print(f"valid={result['valid']}")


if __name__ == "__main__":
    main()
