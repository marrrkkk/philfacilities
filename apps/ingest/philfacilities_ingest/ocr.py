"""Local OCR for scanned public documents.

Some official releases are published only as page images inside a PDF. The
acquisition layer still stores the original PDF byte-for-byte; this module only
adds a reproducible text extraction step for parsers. It does not fetch, bypass,
or reinterpret access controls.

The OCR stack is intentionally local (Pdfium rendering plus RapidOCR/ONNX). No
document is uploaded to a third-party service.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any


class OcrUnavailable(RuntimeError):
    """The optional local OCR stack is not installed or cannot be initialised."""


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    page_number: int


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    lines: tuple[OcrLine, ...]


@lru_cache(maxsize=1)
def _engine() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # pragma: no cover - depends on optional runtime
        raise OcrUnavailable(
            "Scanned-document OCR requires the 'ocr' dependency group "
            "(rapidocr-onnxruntime and pypdfium2)."
        ) from exc
    return RapidOCR()


def ocr_pdf(
    content: bytes,
    *,
    scale: float = 2.0,
    max_pages: int | None = None,
    min_confidence: float = 0.30,
) -> list[OcrPage]:
    """Render and OCR every page of a PDF, preserving page/line provenance.

    ``scale=2.0`` renders roughly 144 DPI from a 72 DPI PDF page, which is enough
    for the government office documents in the source register without exploding
    memory on long files. OCR is deterministic for a fixed dependency/model
    version; the dependency versions are part of the acquisition notes.
    """

    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # pragma: no cover - depends on optional runtime
        raise OcrUnavailable(
            "Scanned-document OCR requires pypdfium2 for PDF page rendering."
        ) from exc

    engine = _engine()
    document = pdfium.PdfDocument(content)
    pages: list[OcrPage] = []
    try:
        total = len(document)
        limit = total if max_pages is None else min(total, max_pages)
        for index in range(limit):
            page = document[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_numpy()
            result, _elapsed = engine(image)
            lines: list[OcrLine] = []
            for item in result or []:
                # RapidOCR returns (box, text, confidence); tolerate 2-tuples in
                # older model builds while keeping the same output contract.
                if len(item) >= 3:
                    _box, text, confidence = item[0], item[1], item[2]
                else:  # pragma: no cover - defensive compatibility
                    _box, text = item
                    confidence = 1.0
                text = str(text).strip()
                score = float(confidence)
                if text and score >= min_confidence:
                    lines.append(OcrLine(text=text, confidence=score, page_number=index + 1))
            pages.append(OcrPage(page_number=index + 1, lines=tuple(lines)))
    finally:
        document.close()
    return pages
