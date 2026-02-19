from __future__ import annotations

from functools import lru_cache

from .preprocess import preprocess_for_ocr


@lru_cache(maxsize=1)
def get_reader():
    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError(
            "easyocr is not installed. Install dependencies from requirements.txt"
        ) from exc
    return easyocr.Reader(["en", "fr"], gpu=False)


def extract_text_from_image(image_path: str) -> str:
    processed = preprocess_for_ocr(image_path)
    results = get_reader().readtext(processed)
    return "\n".join(item[1] for item in results)
