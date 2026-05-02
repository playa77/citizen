"""Image standardization — DPI normalization, JPEG conversion, EXIF stripping."""

from __future__ import annotations

import io

from PIL import Image

# Standardized output parameters (match settings defaults for consistency)
_STANDARD_DPI = 300
_STANDARD_QUALITY = 84


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
