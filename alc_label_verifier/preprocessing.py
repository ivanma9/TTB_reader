"""Image preprocessing before OCR."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from alc_label_verifier._constants import MAX_IMAGE_EDGE


def preprocess(image_path: str) -> np.ndarray:
    """Grayscale → autocontrast → resize → return BGR numpy array for PaddleOCR."""
    img = Image.open(image_path).convert("L")
    img = ImageOps.autocontrast(img)

    w, h = img.size
    if max(w, h) > MAX_IMAGE_EDGE:
        scale = MAX_IMAGE_EDGE / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    img = img.convert("RGB")
    arr = np.array(img)
    # PaddleOCR (OpenCV-based) expects BGR channel order
    return arr[:, :, ::-1]
