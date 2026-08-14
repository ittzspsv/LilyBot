from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import Final, Dict
from ..utils.pillow_utils import get_icon_path, get_text_size
from ..components.neon_text import draw_neon_text
from src.core.utils.lily_utility import format_currency
from src.core.visuals.utils.pillow_utils import apply_glow 


fruits = {
    "Rocket": 5000,
    "Buddha" : 1200000,
    "Tiger" : 50000000,
    "Yeti" : 50000000,
    "Kitsune" : 80000000,
    "Dragon" : 150000000,   
}


CARD_WIDTH: Final = 900
BG_COLOR: Final = (0, 0, 0)
PRICE_COLOR: Final = (0, 255, 0)
FONT_PATH: Final = "public/fonts/Berlin Sans FB Bold.ttf"
NUMBER_FONT_PATH: Final = "public/fonts/Game Bubble.ttf"
ITEM_IMAGE_FOLDER: Final = "public/assets/blox_fruits/fruit_icons"

def stock_img(data_dict: Dict[str, int], stock_type: str="normal") -> Image.Image:
    background_path = (
        "public/assets/blox_fruits/stock/NormalStock.png"
        if "normal" in stock_type
        else "public/assets/blox_fruits/stock/MirageStock.png"
    )
    bg = Image.open(background_path).convert("RGBA")
    bg_w, bg_h = bg.size

    img = Image.new("RGBA", (bg_w, bg_h), (0, 0, 0, 0))
    img.paste(bg, (0, 0), bg)
    draw = ImageDraw.Draw(img)

    items = list(data_dict.items())
    count = len(items)

    try:
        item_font = ImageFont.truetype(FONT_PATH, 40)
        price_font = ImageFont.truetype(NUMBER_FONT_PATH, 32)
    except:
        item_font = ImageFont.load_default()
        price_font = ImageFont.load_default()

    max_cols = 3
    icon_size = 300 if count <= max_cols else 250
    gap_y = 120

    if count > 2 * max_cols:
        items = items[-2 * max_cols:]
        count = len(items)

    if count <= max_cols:
        rows = [count]
    elif count <= 2 * max_cols:
        first_row = min(max_cols, count)
        second_row = count - first_row
        rows = [first_row, second_row]
    else:
        rows = [max_cols, max_cols]

    total_height = len(rows) * icon_size + (len(rows) - 1) * gap_y + 80
    y_start = (bg_h - total_height) // 2

    item_index = 0
    for r, cols_in_row in enumerate(rows):
        row_y = y_start + r * (icon_size + gap_y)
        total_icon_width = cols_in_row * icon_size
        remaining_space = bg_w - total_icon_width
        gap_x = remaining_space // (cols_in_row + 1)
        x_start = gap_x

        for c in range(cols_in_row):
            if item_index >= count:
                break

            name, price = items[item_index]
            x = x_start + c * (icon_size + gap_x)

            icon_path = get_icon_path(ITEM_IMAGE_FOLDER, name)
            if icon_path:
                icon = Image.open(icon_path).convert("RGBA")
                icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

                small_icon = icon.resize((1, 1))
                pixel = small_icon.getpixel((0, 0))
                avg_color = pixel[:3] if isinstance(pixel, tuple) else (255, 255, 255)

                img = apply_glow(
                    img,
                    (x, row_y + 30),
                    icon_size,
                    avg_color
                )

                draw = ImageDraw.Draw(img)

                img.paste(icon, (x, row_y + 30), icon)

            draw.text(
                (x + icon_size // 2, row_y),
                name.upper(),
                font=item_font,
                fill=(255, 224, 102),
                anchor="mt"
            )

            price_str = f"${format_currency(price)}"
            price_w, _ = get_text_size(draw, price_str, price_font)
            price_x = x + (icon_size - price_w) / 2
            price_y = row_y + 30 + icon_size + 15

            draw.text(
                (price_x + price_w / 2, price_y),
                price_str,
                font=price_font,
                fill=(255, 224, 102),
                anchor="mt"
            )

            item_index += 1

    return img