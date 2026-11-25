"""Guide-based, category-specific crop fitting for final WebP output."""

from __future__ import annotations

from fractions import Fraction
import math

from PIL import Image


# The Girl Packer guide gives recommended minimum image dimensions for these
# Body Images tags. Ratios are derived from the documented pixel dimensions.
BODY_IMAGE_SPECS = {
    "portrait": (350, 350, True),
    "tportrait": (350, 350, True),
    "face": (500, 500, False),
    "boobs": (495, 240, False),
    "ass": (495, 240, False),
    "pussy": (245, 235, False),
    "legs": (245, 235, False),
}
CLOTHING_COVER_AREAS = ("boobs_cover", "ass_cover", "pussy_cover", "leg_cover", "accessory_footwear")
CLOTHING_AREA_BODY_TAG = {
    "boobs_cover": "boobs", "ass_cover": "ass",
    "pussy_cover": "pussy", "leg_cover": "legs",
}
CLOTHING_FAMILY_AREAS = {
    "bra": ("boobs_cover",), "outerwear": ("boobs_cover",),
    "shirt": ("boobs_cover",), "top": ("boobs_cover",),
    "dress": ("boobs_cover", "ass_cover", "pussy_cover"),
    "footwear": ("accessory_footwear",), "socks": ("accessory_footwear",),
    "pants": ("ass_cover", "pussy_cover", "leg_cover"),
    "shorts": ("ass_cover", "pussy_cover"),
    "skirt": ("ass_cover", "pussy_cover"),
    "panty": ("ass_cover", "pussy_cover"),
    "lingerie": ("boobs_cover", "ass_cover", "pussy_cover"),
}


def clothing_cover_rule(family: str, cover_area: str) -> tuple[str | None, str]:
    """Resolve a Clothing family and user-selected body cover into guide rules."""
    family, cover_area = str(family or "").strip(), str(cover_area or "").strip()
    if cover_area not in CLOTHING_FAMILY_AREAS.get(family, ()):
        raise ValueError(f"Choose a valid guide cover area for Clothing family {family!r}.")
    if cover_area == "boobs_cover":
        subfolder = {"bra": "bra", "outerwear": "outer"}.get(family, "upper")
    elif cover_area in {"ass_cover", "pussy_cover"}:
        subfolder = {"panty": "panties", "pants": "lower", "shorts": "lower",
                     "skirt": "lower"}.get(family, "upper")
    elif cover_area == "leg_cover":
        subfolder = "lower"
    else:
        subfolder = {"footwear": "shoes", "socks": "socks"}[family]
        return None, f"accessory_footwear/{subfolder}"
    body_tag = CLOTHING_AREA_BODY_TAG[cover_area]
    return body_tag, f"{cover_area}/{subfolder}"
FULLBODY_MIN_HEIGHT = 1500


def _box_pixels(box: list[float] | tuple[float, ...], width: int, height: int) -> tuple[int, int, int, int]:
    if len(box) != 4:
        raise ValueError("Crop box must contain four source-pixel coordinates.")
    left, top, right, bottom = (int(round(float(value))) for value in box)
    left, top = max(0, left), max(0, top)
    right, bottom = min(width, right), min(height, bottom)
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Selected crop box is empty or outside the source image.")
    return left, top, right, bottom


def _has_transparent_pixels(image: Image.Image) -> bool:
    if "A" not in image.getbands():
        return False
    alpha = image.getchannel("A")
    extrema = alpha.getextrema()
    return bool(extrema and extrema[0] < 255 and extrema[1] > 0)


def _expand_to_ratio(
    box: tuple[int, int, int, int], source_size: tuple[int, int], target_width: int, target_height: int
) -> tuple[int, int, int, int]:
    """Expand around a reviewed box to an exact guide ratio without clipping it."""
    left, top, right, bottom = box
    source_width, source_height = source_size
    ratio = Fraction(target_width, target_height)
    units = max(
        math.ceil((right - left) / ratio.numerator),
        math.ceil((bottom - top) / ratio.denominator),
    )
    crop_width, crop_height = units * ratio.numerator, units * ratio.denominator
    if crop_width > source_width or crop_height > source_height:
        raise ValueError("Source image cannot contain the required crop ratio without cutting the selected region.")

    center_x, center_y = (left + right) / 2, (top + bottom) / 2
    crop_left = int(math.floor(center_x - crop_width / 2))
    crop_top = int(math.floor(center_y - crop_height / 2))
    crop_left = min(max(0, crop_left), source_width - crop_width)
    crop_top = min(max(0, crop_top), source_height - crop_height)
    expanded = (crop_left, crop_top, crop_left + crop_width, crop_top + crop_height)
    if not (expanded[0] <= left and expanded[1] <= top and expanded[2] >= right and expanded[3] >= bottom):
        raise ValueError("Required aspect ratio cannot include the selected region within source boundaries.")
    return expanded


def _fit_inside_box_to_ratio(
    box: tuple[int, int, int, int], target_width: int, target_height: int
) -> tuple[int, int, int, int]:
    """Center the largest exact-ratio crop inside a reviewed box when expansion cannot fit."""
    left, top, right, bottom = box
    ratio = Fraction(target_width, target_height)
    units = min((right - left) // ratio.numerator, (bottom - top) // ratio.denominator)
    if units < 1:
        raise ValueError("Reviewed crop is too small to fit the guide clothing-cover ratio.")
    crop_width, crop_height = units * ratio.numerator, units * ratio.denominator
    crop_left = left + (right - left - crop_width) // 2
    crop_top = top + (bottom - top - crop_height) // 2
    return crop_left, crop_top, crop_left + crop_width, crop_top + crop_height


def _scale_up(image: Image.Image, minimum_width: int, minimum_height: int) -> Image.Image:
    scale = max(1.0, minimum_width / image.width, minimum_height / image.height)
    if scale == 1.0:
        return image
    size = (int(round(image.width * scale)), int(round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _scale_body_image_to_spec(image: Image.Image, minimum_width: int, minimum_height: int) -> Image.Image:
    """Upscale a guide-ratio crop without rounding its width and height apart."""
    divisor = math.gcd(minimum_width, minimum_height)
    ratio_width, ratio_height = minimum_width // divisor, minimum_height // divisor
    units = max(
        divisor,
        math.ceil(image.width / ratio_width),
        math.ceil(image.height / ratio_height),
    )
    size = (ratio_width * units, ratio_height * units)
    if size == image.size:
        return image
    return image.resize(size, Image.Resampling.LANCZOS)


def _resize_to_guide_dimensions(image: Image.Image, width: int, height: int) -> Image.Image:
    """Resize a clothing-cover crop to the guide's exact pixel dimensions."""
    if image.size == (width, height):
        return image
    return image.resize((width, height), Image.Resampling.LANCZOS)


def prepare_export_crop(image: Image.Image, item: dict, *, allow_missing_alpha: bool = False) -> tuple[Image.Image, dict]:
    """Apply the documented crop policy; return derivative and recorded rule."""
    category = item.get("category")
    box = item.get("bbox_xyxy")
    if box is None:
        raise ValueError("A selected crop needs a reviewed bounding box.")
    pixel_box = _box_pixels(box, image.width, image.height)
    main_tag = str(item.get("main_tag") or item.get("tag") or "").strip()

    if category == "fullbody":
        crop = image.crop(pixel_box)
        if not _has_transparent_pixels(crop):
            crop.close()
            raise ValueError("Fullbody export requires an existing transparent background; no background-removal step is configured.")
        alpha_bounds = crop.getchannel("A").getbbox()
        if not alpha_bounds:
            crop.close()
            raise ValueError("Fullbody crop contains no visible subject pixels.")
        trimmed = crop.crop(alpha_bounds)
        crop.close()
        crop = _scale_up(trimmed, 1, FULLBODY_MIN_HEIGHT)
        if crop is not trimmed:
            trimmed.close()
        return crop, {
            "policy": "fullbody_transparent_trim_min_height",
            "minimum_height": FULLBODY_MIN_HEIGHT,
            "bbox_xyxy_source_pixels": list(pixel_box),
            "trimmed_alpha_bounds_xyxy_crop_pixels": list(alpha_bounds),
            "output_size": list(crop.size),
        }

    if category == "body_images":
        spec = BODY_IMAGE_SPECS.get(main_tag)
        if spec is None:
            raise ValueError(f"No guide image-size rule is defined for Body Images tag {main_tag!r}.")
        target_width, target_height, requires_alpha = spec
        crop_box = _expand_to_ratio(pixel_box, image.size, target_width, target_height)
        crop = image.crop(crop_box)
        if requires_alpha and not _has_transparent_pixels(crop) and not allow_missing_alpha:
            crop.close()
            raise ValueError(f"Body Images tag {main_tag!r} requires an existing transparent background.")
        crop = _scale_body_image_to_spec(crop, target_width, target_height)
        return crop, {
            "policy": "body_images_guide_aspect_and_minimum_dimensions",
            "main_tag": main_tag,
            "target_minimum_size": [target_width, target_height],
            "crop_bbox_xyxy_source_pixels": list(crop_box),
            "output_size": list(crop.size),
        }

    if category == "clothing":
        # Professional Review has its own legacy classification form; this
        # guide cover-area picker is specifically part of Normal Processing.
        if "clothing_cover_area" not in item:
            crop = image.crop(pixel_box)
            return crop, {
                "policy": "clothing_reviewed_box_preserve_source_aspect",
                "bbox_xyxy_source_pixels": list(pixel_box),
                "output_size": list(crop.size),
            }
        family = str(item.get("clothing_broad_family") or "").strip()
        cover_area = str(item.get("clothing_cover_area") or "").strip()
        body_tag, cover_folder = clothing_cover_rule(family, cover_area)
        if body_tag is None:
            crop = image.crop(pixel_box)
            return crop, {
                "policy": "clothing_accessory_preserve_reviewed_box",
                "clothing_broad_family": family,
                "cover_folder": cover_folder,
                "bbox_xyxy_source_pixels": list(pixel_box),
                "output_size": list(crop.size),
            }
        target_width, target_height, _requires_alpha = BODY_IMAGE_SPECS[body_tag]
        try:
            crop_box = _expand_to_ratio(pixel_box, image.size, target_width, target_height)
            fit_mode = "expanded_around_reviewed_box"
        except ValueError:
            crop_box = _fit_inside_box_to_ratio(pixel_box, target_width, target_height)
            fit_mode = "centered_within_reviewed_box"
        crop = image.crop(crop_box)
        # Clothing cover images use the exact dimensions listed by the guide.
        # The source crop already has the exact target ratio, so resizing to
        # this fixed canvas preserves that ratio without producing oversized
        # derivatives (e.g. 561x272 instead of 495x240).
        crop = _resize_to_guide_dimensions(crop, target_width, target_height)
        return crop, {
            "policy": "clothing_guide_exact_dimensions_and_aspect",
            "clothing_broad_family": family,
            "cover_folder": cover_folder,
            "body_area_spec": body_tag,
            "fit_mode": fit_mode,
            "target_size": [target_width, target_height],
            "bbox_xyxy_source_pixels": list(pixel_box),
            "crop_bbox_xyxy_source_pixels": list(crop_box),
            "output_size": list(crop.size),
        }

    return image.crop(pixel_box), {
        "policy": "reviewed_box_preserve_source_aspect",
        "bbox_xyxy_source_pixels": list(pixel_box),
        "output_size": [pixel_box[2] - pixel_box[0], pixel_box[3] - pixel_box[1]],
    }
