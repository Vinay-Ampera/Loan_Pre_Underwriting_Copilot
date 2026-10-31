"""Image quality for photos and scans: blur score, page geometry and deskew (OpenCV).

Thresholds are design values calibrated on the synthetic set in Stage 2 (see docs/TESTING.md):
good photos score 120+, mild and poor ones 20-35, the blurry reject fixture about 2.
"""

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

Image = NDArray[Any]

BLUR_REJECT_BELOW = 10.0  # "please re-upload"
BLUR_WARN_BELOW = 60.0  # accepted with a warning
ASPECT_MIN, ASPECT_MAX = 1.30, 1.55  # A4-like documents; outside this the page is cut off
ANALYSIS_WIDTH = 1000  # blur is measured at a fixed width so resolution does not matter


def to_gray(img: Image) -> Image:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def blur_score(img: Image) -> float:
    """Variance of the Laplacian after resizing to a fixed width. Lower means blurrier."""
    gray = to_gray(img)
    h, w = gray.shape
    gray = cv2.resize(gray, (ANALYSIS_WIDTH, max(1, int(h * ANALYSIS_WIDTH / w))),
                      interpolation=cv2.INTER_AREA)  # fmt: skip
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


@dataclass(frozen=True)
class PageGeometry:
    aspect: float  # long side / short side of the page found in the frame
    angle: float  # degrees the page is rotated from upright, in (-45, 45]
    coverage: float  # share of the frame the page occupies
    box: tuple[tuple[float, float], tuple[float, float], float]  # cv2 minAreaRect, full-res units


def find_page(img: Image) -> PageGeometry | None:
    """Locate the bright page against the desk. None when no page-like region exists."""
    gray = to_gray(img)
    h, w = gray.shape
    scale = 800 / max(h, w)
    small = cv2.GaussianBlur(cv2.resize(gray, None, fx=scale, fy=scale), (5, 5), 0)
    _, th = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    coverage = float(cv2.contourArea(biggest) / (small.shape[0] * small.shape[1]))
    if coverage < 0.15:
        return None
    (cx, cy), (rw, rh), angle = cv2.minAreaRect(biggest)
    if min(rw, rh) < 1:
        return None
    if rw < rh:  # make the angle describe the long side, then fold into (-45, 45]
        angle -= 90
    angle = ((angle + 45) % 90) - 45
    box = ((cx / scale, cy / scale), (rw / scale, rh / scale), angle)
    return PageGeometry(
        aspect=max(rw, rh) / min(rw, rh), angle=float(angle), coverage=coverage, box=box
    )


def deskew(img: Image) -> Image:
    """Rotate so the page is upright. Returns the image unchanged when the tilt is under 0.3 deg."""
    geo = find_page(img)
    if geo is None or abs(geo.angle) < 0.3:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), geo.angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def decode(data: bytes) -> Image | None:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return None if img is None else img
