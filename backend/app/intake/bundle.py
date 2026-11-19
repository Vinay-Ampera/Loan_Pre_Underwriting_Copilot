"""Several documents in one PDF (Stage 10, Part D; EDGE_CASES E-44, E-46 and E-61 to E-64).

Pure steps, no database and no files:

1. `propose`: every page of a PDF is classified on its own with the same local classifier the
   single files use. A page with a recognised title starts a new document; a page without one
   continues the previous document; an unrecognised first page is "unrecognised". Nothing is
   guessed beyond that: a page in the middle that belongs to nobody is absorbed by the document
   before it, and the officer sees every boundary and can move it.
2. `validate`: the officer's edited split must cover every page once, in order, with known types.
3. `cut`: each piece becomes a PDF of its own. The original is never touched.

Two kinds of document legitimately repeat their title on a following page: a bank statement
whose pages carry the header again, and the two sides of an Aadhaar card. Consecutive pages of
those types are one document. Two payslips, two ITRs or two statements of different accounts in a
row are told apart by the officer if the titles do not (the proposal splits payslips, which carry
one title per month, and never splits a statement).
"""

from dataclasses import asdict, dataclass

import pymupdf

from app.intake import classifier
from app.intake.models import DocType
from app.intake.reader import PageText

MERGE_SAME_TYPE = {DocType.BANK_STATEMENT, DocType.AADHAAR}  # a repeated title is a continuation
MIN_PAGES = 2


class SplitError(ValueError):
    """The split the officer sent is not usable. The message is plain language."""


@dataclass
class Segment:
    """Pages `page_from` to `page_to` (1-based, inclusive) are one document of this type."""

    page_from: int
    page_to: int
    doc_type: str
    confidence: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def page_labels(pages: list[PageText]) -> list[tuple[DocType, float]]:
    """(type, confidence) of each page by its own title; UNKNOWN when it has none."""
    return [classifier.classify(p.lines) for p in pages]


def propose(pages: list[PageText]) -> list[Segment]:
    segments: list[Segment] = []
    for number, (kind, conf) in enumerate(page_labels(pages), start=1):
        last = segments[-1] if segments else None
        if kind is DocType.UNKNOWN:
            if last is None:  # an unrecognised first page is its own "unrecognised" document
                segments.append(Segment(number, number, DocType.UNKNOWN.value, 0.0))
            else:  # no title: it continues the document before it
                last.page_to = number
        elif last is not None and last.doc_type == kind.value and kind in MERGE_SAME_TYPE:
            last.page_to = number
            last.confidence = min(last.confidence, conf)
        else:
            segments.append(Segment(number, number, kind.value, conf))
    return segments


def is_bundle(segments: list[Segment]) -> bool:
    """More than one document, or one recognised document that starts after an unrecognised page.
    A single multi-page document (a statement, a long ITR) is not a bundle."""
    return len(segments) >= MIN_PAGES


def validate(raw: list[dict[str, object]], page_count: int, allowed: set[str]) -> list[Segment]:
    """The officer's split, checked: whole pages, in order, no gap, no overlap, known types."""
    if not raw:
        raise SplitError("There must be at least one document.")
    out: list[Segment] = []
    expected = 1
    for item in raw:
        try:
            first, last = int(str(item["page_from"])), int(str(item["page_to"]))
            kind = str(item["doc_type"])
        except (KeyError, TypeError, ValueError):
            raise SplitError("Each document needs a first page, a last page and a type.") from None
        if first != expected:
            raise SplitError(
                "The documents must follow each other without a gap or an overlap "
                f"(expected page {expected}, got page {first})."
            )
        if last < first or last > page_count:
            raise SplitError(
                f"Pages {first} to {last} are not inside this PDF ({page_count} pages)."
            )
        if kind not in allowed:
            raise SplitError("Unknown document type for this loan.")
        out.append(Segment(first, last, kind, 0.0))
        expected = last + 1
    if expected != page_count + 1:
        raise SplitError(
            f"Every page must belong to a document: pages {expected} to {page_count} do not."
        )
    return out


def cut(data: bytes, segment: Segment) -> bytes:
    """The PDF of one piece. A split that covers the whole PDF returns it unchanged."""
    with pymupdf.open(stream=data, filetype="pdf") as src:
        if segment.page_from == 1 and segment.page_to == src.page_count:
            return data
        with pymupdf.open() as out:
            out.insert_pdf(src, from_page=segment.page_from - 1, to_page=segment.page_to - 1)
            return bytes(out.tobytes(garbage=3, deflate=True))


def page_accuracy(truth: list[str], predicted: list[Segment]) -> tuple[int, int]:
    """(pages labelled correctly, pages) for a bundle whose true type per page is `truth`."""
    guess: list[str] = []
    for s in predicted:
        guess += [s.doc_type] * (s.page_to - s.page_from + 1)
    guess += ["?"] * (len(truth) - len(guess))
    return sum(a == b for a, b in zip(truth, guess, strict=False)), len(truth)
