from __future__ import annotations

from typing import Final
from PIL import ImageDraw, ImageFont, ImageChops, ImageFilter, Image
from PIL.ImageFont import FreeTypeFont, ImageFont as PILImageFont

import os
import io


DEFAULT_STARTING_SIZE: Final[int] = 46
DEFAULT_MIN_SIZE: Final[int] = 20


def load_font(path: str, size: int) -> FreeTypeFont | PILImageFont:
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        return ImageFont.load_default()

def load_image(response) -> Image.Image | None:
    if response is None:
        return None

    response.raise_for_status()
    return Image.open(
        io.BytesIO(response.content)
    ).convert("RGBA")
    
def get_icon_path(folder, fruit_name):
    for ext in [".png", ".webp", ".jpg", ".jpeg"]:
        candidate = os.path.join(folder, f"{fruit_name}{ext}")
        if os.path.exists(candidate):
            return candidate

    fruit_lower = fruit_name.lower()
    for f in os.listdir(folder):
        name, ext = os.path.splitext(f)
        if name.lower() == fruit_lower and ext.lower() in [".png", ".webp", ".jpg", ".jpeg"]:
            return os.path.join(folder, f)

    return None


def get_text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FreeTypeFont | PILImageFont,
) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    width: int = int(bbox[2] - bbox[0])
    height: int = int(bbox[3] - bbox[1])
    return width, height


def fit_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    max_width: int,
    starting_size: int = DEFAULT_STARTING_SIZE,
    min_size: int = DEFAULT_MIN_SIZE,
) -> FreeTypeFont | PILImageFont:
    font_size: int = starting_size
    font: FreeTypeFont | PILImageFont = load_font(font_path, font_size)

    text_width, _ = get_text_size(draw, text, font)

    while text_width > max_width and font_size > min_size:
        font_size -= 1
        font = load_font(font_path, font_size)
        text_width, _ = get_text_size(draw, text, font)

    return font

def apply_glow(img, coord, ICON_SIZE, avg_color):
    glow_scale = 2.5
    glow_size = int(ICON_SIZE * glow_scale)
    
    mask = Image.new("L", (glow_size, glow_size), 0)
    draw_mask = ImageDraw.Draw(mask)
    margin = glow_size // 3
    draw_mask.ellipse(
        [margin, margin, glow_size - margin, glow_size - margin], 
        fill=180 
    )
    mask = mask.filter(ImageFilter.GaussianBlur(glow_size // 6))

    glow_color_layer = Image.new("RGB", (glow_size, glow_size), avg_color)
    
    full_glow_layer = Image.new("RGB", img.size, (0, 0, 0)) 
    glow_pos = (
        coord[0] - (glow_size - ICON_SIZE) // 2, 
        coord[1] - (glow_size - ICON_SIZE) // 2
    )
    
    full_glow_layer.paste(glow_color_layer, glow_pos, mask)

    result = ImageChops.screen(img.convert("RGB"), full_glow_layer)
    return result.convert("RGBA")