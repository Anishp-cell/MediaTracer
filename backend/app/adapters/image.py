from __future__ import annotations

from pathlib import Path
from typing import Iterator

from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import Settings
from .base import Adapter, AdapterError, Unit, thumbnail

# Cap decoding size to avoid decompression bombs on huge files.
Image.MAX_IMAGE_PIXELS = 120_000_000


class ImageAdapter(Adapter):
    family = "image"
    formats = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WebP"}
    needs = ("image",)

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        try:
            with Image.open(path) as im:
                im.load()
                img = ImageOps.exif_transpose(im).convert("RGB")
        except UnidentifiedImageError as e:
            raise AdapterError("Could not decode image: the file is not a valid JPEG/PNG/WebP image") from e
        except Image.DecompressionBombError as e:
            raise AdapterError("Image is too large to process safely") from e
        except OSError as e:
            raise AdapterError(f"Could not decode image: {getattr(e, 'strerror', None) or 'truncated or corrupt file'}") from e
        yield Unit(
            kind="image",
            modality="image",
            locator={"type": "image", "width": img.width, "height": img.height},
            image=img,
            preview=thumbnail(img),
        )
