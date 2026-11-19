"""Upload-time checks (FR-1 to FR-3, SECURITY.md section 6).

Pure functions over bytes: type by file signature, size, password protection, active content,
per-page kind, blur and crop. A rejected file is never read further; the caller deletes it.
The password of a protected PDF is never requested or stored.
"""

import pymupdf

from app.intake import quality
from app.intake.models import PageInfo, PageKind, UploadCheck

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_PAGES = 40
MIN_DOCUMENT_SIDE = 500  # px; smaller images are ID photographs, not photographed pages
DIGITAL_MIN_CHARS = 30  # fewer characters than this on a PDF page means it is an image
_ACTIVE_CONTENT = ("/JavaScript", "/JS ", "/Launch", "/EmbeddedFile", "/OpenAction")

_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)

MESSAGES = {
    "bad_type": "Only PDF, JPG and PNG files are accepted.",
    "too_large": "The file is larger than the size limit. Please upload a smaller file.",
    "empty": "The file is empty.",
    "password_protected": "This PDF is password protected. Please remove the password and upload it again.",
    "corrupt": "The file could not be opened. Please upload it again.",
    "active_content": "The PDF contains scripts or embedded files and cannot be accepted.",
    "too_many_pages": "The PDF has too many pages.",
    "blurry": "The image is too blurry to read. Please re-upload a sharper photo or scan.",
    "cropped": "Part of the document is cut off. Please re-upload a photo showing the whole page.",
}


def sniff_mime(data: bytes) -> str | None:
    for magic, mime in _SIGNATURES:
        if data.startswith(magic):
            return mime
    return None


def _reject(
    code: str, mime: str | None, size: int, message: str | None = None, **extra: object
) -> UploadCheck:
    return UploadCheck(
        accepted=False,
        mime=mime,
        size_bytes=size,
        reject_code=code,
        message=message or MESSAGES[code],
        **extra,
    )


def _quality_verdict(check: UploadCheck, blur: float, aspect: float | None) -> UploadCheck:
    check.blur_score = round(blur, 1)
    check.page_aspect = None if aspect is None else round(aspect, 2)
    if blur < quality.BLUR_REJECT_BELOW:
        return _reject(
            "blurry", check.mime, check.size_bytes, pages=check.pages, blur_score=check.blur_score
        )
    if aspect is not None and not quality.ASPECT_MIN <= aspect <= quality.ASPECT_MAX:
        return _reject("cropped", check.mime, check.size_bytes, pages=check.pages,
                       blur_score=check.blur_score, page_aspect=check.page_aspect)  # fmt: skip
    if blur < quality.BLUR_WARN_BELOW:
        check.warnings.append("borderline_blur")
    return check


def _check_pdf(
    data: bytes, size: int, *, max_pages: int = MAX_PAGES, every_page: bool = False
) -> UploadCheck:
    """`every_page` is the bundle mode (Stage 10, Part D): a larger page limit, and the blur of
    every scanned page is measured, not a sample of three, so a bad page is named."""
    mime = "application/pdf"
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        return _reject("corrupt", mime, size)
    with doc:
        if doc.needs_pass or doc.is_encrypted:
            return _reject("password_protected", mime, size)
        if doc.page_count == 0:
            return _reject("corrupt", mime, size)
        if doc.page_count > max_pages:
            return _reject("too_many_pages", mime, size)
        if doc.embfile_count() or any(
            tok in doc.xref_object(x, compressed=False)
            for x in range(1, doc.xref_length())
            for tok in _ACTIVE_CONTENT
        ):
            return _reject("active_content", mime, size)
        pages: list[PageInfo] = []
        scanned_blur: list[float] = []
        worst_page = 0
        for i in range(doc.page_count):
            page = doc[i]
            chars = len(page.get_text().strip())
            kind = PageKind.DIGITAL if chars >= DIGITAL_MIN_CHARS else PageKind.SCANNED
            pages.append(PageInfo(index=i, kind=kind, chars=chars))
            if kind is PageKind.SCANNED and (every_page or len(scanned_blur) < 3):
                pix = page.get_pixmap(dpi=100, alpha=False)
                img = quality.decode(pix.tobytes("png"))
                if img is not None:
                    score = quality.blur_score(img)
                    if not scanned_blur or score < min(scanned_blur):
                        worst_page = i + 1
                    scanned_blur.append(score)
    check = UploadCheck(accepted=True, mime=mime, size_bytes=size, pages=pages)
    if scanned_blur:
        verdict = _quality_verdict(check, min(scanned_blur), None)
        if every_page and verdict.reject_code == "blurry":
            verdict.message = (
                f"Page {worst_page} of the PDF is too blurry to read. "
                "Please re-scan it and upload the PDF again."
            )
        return verdict
    return check


def _check_image(data: bytes, mime: str, size: int) -> UploadCheck:
    img = quality.decode(data)
    if img is None:
        return _reject("corrupt", mime, size)
    pages = [PageInfo(index=0, kind=PageKind.PHOTO)]
    if min(img.shape[:2]) < MIN_DOCUMENT_SIDE:
        # a passport-size picture (the applicant photo) is not a page: no blur or crop verdict
        return UploadCheck(accepted=True, mime=mime, size_bytes=size, pages=pages,
                           blur_score=round(quality.blur_score(img), 1))  # fmt: skip
    check = UploadCheck(accepted=True, mime=mime, size_bytes=size, pages=pages)
    geo = quality.find_page(img)
    return _quality_verdict(check, quality.blur_score(img), None if geo is None else geo.aspect)


def check_upload(
    data: bytes, filename: str, max_bytes: int, *, bundle_pages: int | None = None
) -> UploadCheck:
    """Run every upload-time check. Never raises on bad input; returns a rejection instead.
    `bundle_pages` switches a PDF to the bundle limits: that many pages, every scanned page
    checked for blur."""
    size = len(data)
    if size == 0:
        return _reject("empty", None, 0)
    if size > max_bytes:
        return _reject("too_large", None, size)
    mime = sniff_mime(data)
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if mime is None or ext not in ALLOWED_EXTENSIONS:
        return _reject("bad_type", mime, size)
    if mime == "application/pdf":
        if bundle_pages is not None:
            return _check_pdf(data, size, max_pages=bundle_pages, every_page=True)
        return _check_pdf(data, size)
    return _check_image(data, mime, size)


def check_case_size(sizes: list[int], max_case_bytes: int) -> bool:
    """True when the whole upload set for a case is within the per-case limit."""
    return sum(sizes) <= max_case_bytes
