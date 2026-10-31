"""Turn clean PDFs into the messy formats real uploads arrive in."""

import io
import random
from datetime import datetime, timedelta

import cv2
import numpy as np
import pikepdf
import pymupdf as fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

# level -> (gaussian sigma, tilt degrees, shadow strength, noise, jpeg quality)
PHOTO_LEVELS = {
    "good": (0.6, 1.0, 0.10, 2.0, 88),
    "mild": (1.6, 3.0, 0.25, 4.0, 72),
    "poor": (2.6, 5.0, 0.40, 7.0, 50),
}
# design-time quality score assigned to each level (the pipeline measures its own in Stage 2)
LEVEL_QUALITY = {"digital": 95, "good": 90, "mild": 72, "poor": 55}
LEVEL_CONFIDENCE = {"digital": 0.96, "good": 0.93, "mild": 0.82, "poor": 0.70}


def render_page(pdf: bytes, page: int = 0, dpi: int = 150) -> np.ndarray:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        pix = doc[page].get_pixmap(dpi=dpi, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def blur_score(img: np.ndarray) -> float:
    """Variance of the Laplacian: lower means blurrier."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _degrade(img: np.ndarray, rng: random.Random, sigma: float, tilt: float, shadow: float,
             noise: float) -> np.ndarray:  # fmt: skip
    h, w = img.shape[:2]
    canvas = np.full((h + 120, w + 120, 3), (96, 110, 118), dtype=np.uint8)  # desk
    canvas[60 : 60 + h, 60 : 60 + w] = img
    angle = rng.uniform(-tilt, tilt)
    m = cv2.getRotationMatrix2D((canvas.shape[1] / 2, canvas.shape[0] / 2), angle, 1.0)
    canvas = cv2.warpAffine(canvas, m, (canvas.shape[1], canvas.shape[0]),
                            borderValue=(96, 110, 118))  # fmt: skip
    grad = np.linspace(
        1.0, 1.0 - shadow, canvas.shape[1] if rng.random() < 0.5 else canvas.shape[0]
    )
    shade = grad[None, :, None] if len(grad) == canvas.shape[1] else grad[:, None, None]
    canvas = np.clip(canvas * shade, 0, 255).astype(np.uint8)
    if sigma > 0:
        canvas = cv2.GaussianBlur(canvas, (0, 0), sigma)
    if noise > 0:
        n = np.random.default_rng(rng.randrange(2**32)).normal(0, noise, canvas.shape)
        canvas = np.clip(canvas + n, 0, 255).astype(np.uint8)
    return canvas


def photo_variant(pdf: bytes, level: str, rng: random.Random) -> tuple[bytes, float]:
    """First page as a phone-style JPEG. Returns (jpeg bytes, blur score)."""
    sigma, tilt, shadow, noise, q = PHOTO_LEVELS[level]
    img = _degrade(render_page(pdf), rng, sigma, tilt, shadow, noise)
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    assert ok
    return enc.tobytes(), blur_score(img)


def reject_blur_jpg(pdf: bytes, rng: random.Random) -> bytes:
    img = _degrade(render_page(pdf), rng, 9.0, 2.0, 0.2, 3.0)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()


def cropped_jpg(pdf: bytes, rng: random.Random) -> bytes:
    img = render_page(pdf)
    h, w = img.shape[:2]
    img = img[int(h * 0.05) : int(h * 0.38), int(w * 0.25) : int(w * 0.8)]
    img = _degrade(img, rng, 0.8, 2.0, 0.15, 3.0)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()


def scanned_pdf(pdf: bytes, rng: random.Random, dpi: int = 150) -> bytes:
    """Image-only PDF (no text layer), slightly skewed with scanner noise."""
    out = fitz.open()
    with fitz.open(stream=pdf, filetype="pdf") as src:
        for i in range(len(src)):
            img = _degrade(render_page(pdf, i, dpi), rng, 0.7, 0.8, 0.0, 3.0)
            img = img[60:-60, 60:-60]
            ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            assert ok
            page = out.new_page(width=src[i].rect.width, height=src[i].rect.height)
            page.insert_image(page.rect, stream=enc.tobytes())
    data = out.tobytes()
    out.close()
    return data


def set_producer(pdf: bytes, producer: str, creator: str | None = None, created: datetime | None = None,
                 modified: datetime | None = None) -> bytes:  # fmt: skip
    """Rewrite PDF metadata. Used to simulate an editing tool for tamper hints."""
    with pikepdf.open(io.BytesIO(pdf)) as p:
        with p.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta["pdf:Producer"] = producer
            if creator:
                meta["xmp:CreatorTool"] = creator
        p.docinfo["/Producer"] = producer
        if creator:
            p.docinfo["/Creator"] = creator
        if created:
            p.docinfo["/CreationDate"] = created.strftime("D:%Y%m%d%H%M%S")
        if modified:
            p.docinfo["/ModDate"] = modified.strftime("D:%Y%m%d%H%M%S")
        out = io.BytesIO()
        p.save(out)
    return out.getvalue()


def tamper_metadata(pdf: bytes, rng: random.Random, base: datetime) -> bytes:
    tool = rng.choice(["iLovePDF", "Sejda PDF Editor", "Adobe Acrobat Pro 2024", "PDFescape"])
    return set_producer(
        pdf, tool, tool, created=base, modified=base + timedelta(days=rng.randint(3, 40))
    )


def encrypt_pdf(pdf: bytes, password: str) -> bytes:
    with pikepdf.open(io.BytesIO(pdf)) as p:
        out = io.BytesIO()
        p.save(out, encryption=pikepdf.Encryption(user=password, owner=password + "-owner", R=6))
    return out.getvalue()


def avatar_jpg(rng: random.Random, label: str) -> bytes:
    """Passport-style placeholder (flat silhouette, no real face)."""
    img = Image.new("RGB", (300, 380), tuple(rng.randint(170, 230) for _ in range(3)))  # type: ignore[arg-type]
    d = ImageDraw.Draw(img)
    skin = (rng.randint(150, 210), rng.randint(110, 160), rng.randint(80, 120))
    d.ellipse((95, 70, 205, 200), fill=skin)
    d.rounded_rectangle((60, 215, 240, 380), radius=50, fill=(rng.randint(30, 90),) * 3)
    d.text((10, 8), f"SYNTHETIC {label}", fill=(60, 60, 60), font=ImageFont.load_default())
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()
