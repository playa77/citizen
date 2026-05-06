"""Image standardization — DPI normalization, JPEG conversion, EXIF stripping,
and OCR-optimized preprocessing (greyscale + contrast, black/white threshold).
"""

# Semantic Version: 0.2.0

from __future__ import annotations

import io
from typing import NamedTuple

from PIL import Image, ImageEnhance, ImageFilter

# Standardized output parameters (match settings defaults for consistency)
_STANDARD_DPI = 300
_STANDARD_QUALITY = 84


class PreprocessedPair(NamedTuple):
    """Two preprocessed versions of the same image for dual-OCR."""
    greyscale_contrast: Image.Image  # Greyscale with enhanced contrast
    black_white: Image.Image         # Fully thresholded to black & white


def standardize_to_jpg(image: Image.Image) -> Image.Image:
    """Normalize a Pillow Image to 300 DPI JPEG with EXIF data stripped.

    Pipeline
    --------
    1. Convert to RGB (RGBA → RGB on white background; palette / greyscale → RGB).
    2. Scale to ``_STANDARD_DPI`` (300) if the source image declares a different DPI.
    3. Re-encode as JPEG with quality = ``_STANDARD_QUALITY`` (84) and no EXIF chunk.
    4. Return a fresh :class:`Image.Image` opened from the re-encoded bytes.

    Parameters
    ----------
    image : Image.Image
        Input image (any mode, any DPI).

    Returns
    -------
    Image.Image
        JPEG image at 300 DPI, quality 84, no EXIF metadata.
    """
    # 1. Convert to RGB (JPEG does not support RGBA, palette, greyscale, etc.)
    if image.mode == "RGBA":
        # Composite onto a pure-white background to avoid black halos.
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])  # alpha channel
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    # 2. Normalize DPI to 300 while preserving pixel dimensions.
    #    Pillow stores DPI as (x_dpi, y_dpi) in the ``info`` dict.
    #    We set it to the standard value; no physical resampling is needed
    #    because DPI is metadata that controls how Tesseract interprets scale.
    image.info["dpi"] = (_STANDARD_DPI, _STANDARD_DPI)

    # 3. Re-encode as JPEG with explicit DPI and no EXIF block.
    #    Pillow does not automatically persist ``info["dpi"]`` for JPEG;
    #    DPI must be passed via the ``dpi`` save argument so that it is
    #    written into the JFIF density header.
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=_STANDARD_QUALITY,
        exif=b"",
        dpi=(_STANDARD_DPI, _STANDARD_DPI),
    )
    buffer.seek(0)

    # 4. Decode back to a fresh Image instance.
    return Image.open(buffer)


# ---------------------------------------------------------------------------
# OCR-optimized preprocessing — dual-version pipeline
# ---------------------------------------------------------------------------

# Sensible defaults for contrast enhancement and binarisation.
# These are deliberately chosen to improve OCR on typical scanned documents
# (e.g. Jobcenter letters with low contrast or uneven lighting) without
# blowing out text in high-contrast originals.
_DEFAULT_CONTRAST_FACTOR = 2.0
_DEFAULT_BW_THRESHOLD = 128
_DEFAULT_SHARPEN_RADIUS = 1.0
_DEFAULT_SHARPEN_PERCENT = 80


def preprocess_for_ocr(
    image: Image.Image,
    *,
    contrast_factor: float = _DEFAULT_CONTRAST_FACTOR,
    bw_threshold: int = _DEFAULT_BW_THRESHOLD,
    sharpen_radius: float = _DEFAULT_SHARPEN_RADIUS,
    sharpen_percent: int = _DEFAULT_SHARPEN_PERCENT,
) -> PreprocessedPair:
    """Create two preprocessed versions optimized for Tesseract OCR.

    **Version 1 — Greyscale + contrast:**
        1. Convert to greyscale.
        2. Apply subtle sharpening to improve edge definition.
        3. Enhance contrast by *contrast_factor* (default 2.0×).

    **Version 2 — Black & white (fully thresholded):**
        1. Convert to greyscale.
        2. Apply sharpening and contrast enhancement (same as V1).
        3. Threshold at *bw_threshold* (default 128) to produce a pure 1-bit
           black-and-white image. This removes all grey noise and is
           particularly effective on cleanly printed text.

    The two versions are complementary:
    - V1 preserves subtle grey details that might carry semantic information
      (watermarks, stamps, handwritten notes).
    - V2 eliminates noise completely, which Tesseract handles best for
      cleanly printed machine text.

    Parameters
    ----------
    image : Image.Image
        Input image (any mode; will be converted to greyscale internally).
    contrast_factor : float
        Contrast multiplier passed to :class:`PIL.ImageEnhance.Contrast`
        (default 2.0).
    bw_threshold : int
        Threshold value for binarisation (0-255, default 128).  Pixels with
        intensity >= threshold become white; pixels below become black.
    sharpen_radius : float
        Radius for PIL's ``UnsharpMask`` filter (default 1.0).
    sharpen_percent : int
        Percent for ``UnsharpMask`` (default 80).

    Returns
    -------
    PreprocessedPair
        A named tuple with ``.greyscale_contrast`` and ``.black_white``
        Image instances.
    """
    # Shared preprocessing: convert to greyscale if not already.
    grey = image.convert("L")

    # Sharpen to improve character edges.
    grey = grey.filter(ImageFilter.UnsharpMask(radius=sharpen_radius, percent=sharpen_percent))

    # --- Version 1: Greyscale with enhanced contrast ---
    enhancer = ImageEnhance.Contrast(grey)
    v1 = enhancer.enhance(contrast_factor)

    # --- Version 2: Black & white threshold ---
    # Threshold: all pixels < threshold → 0 (black); >= threshold → 255 (white)
    v2 = grey.point(lambda p: 255 if p >= bw_threshold else 0, mode="1")

    return PreprocessedPair(greyscale_contrast=v1, black_white=v2)
