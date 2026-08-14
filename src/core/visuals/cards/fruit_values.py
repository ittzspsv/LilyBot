from PIL import Image, ImageDraw, ImageFilter
from src.core.utils.lily_utility import format_currency
from typing import Final
from src.core.visuals.utils.pillow_utils import load_font, fit_font_size, get_icon_path

FONT_PATH: Final = "public/fonts/Berlin Sans FB Bold.ttf"
NUMBER_FONT_PATH: Final = "public/fonts/Game Bubble.ttf"
ITEM_IMAGE_FOLDER: Final = "public/assets/blox_fruits/fruit_icons"
BACKGROUND: Final = "public/assets/blox_fruits/fruit_values/FruitValues.png"
ICON_SIZE: Final = 220
GLOW_OPACITY: Final = 220



def value_img(data):
    fruit_name = data.get("fruit_name", "UNKNOWN")
    physical_value = data.get("physical_value", 0)
    permanent_value = data.get("permanent_value", 0)
    value_amount = data.get("value", 0)
    demand = data.get("demand", "")
    demand_type = data.get("demand_type", "")

    bg = Image.open(BACKGROUND).convert("RGBA").resize((704, 883))
    canvas = Image.new("RGBA", bg.size)
    canvas.paste(bg, (0, 0))
    draw = ImageDraw.Draw(canvas)

    big_font = load_font(FONT_PATH, 46)
    label_font = load_font(FONT_PATH, 32)
    number_font = load_font(NUMBER_FONT_PATH, 32)

    icon_file = get_icon_path(ITEM_IMAGE_FOLDER, fruit_name)

    if icon_file:
        icon = Image.open(icon_file).convert("RGBA")
        icon = icon.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.BICUBIC)

        avg_color_img = icon.resize((1, 1))
        pixel = avg_color_img.getpixel((0, 0))

        if pixel is None:
            avg_color = (0, 0, 0)
        elif isinstance(pixel, tuple):
            avg_color = tuple(int(c) for c in pixel[:3])
        else:
            gray = int(pixel)
            avg_color = (gray, gray, gray)

        glow_size = (int(ICON_SIZE * 2.5), int(ICON_SIZE * 2.5))
        glow_img = Image.new("RGBA", glow_size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_img)

        ellipse_bbox = (
            glow_size[0] // 4, glow_size[1] // 4,
            3 * glow_size[0] // 4, 3 * glow_size[1] // 4
        )

        glow_draw.ellipse(ellipse_bbox, fill=avg_color + (GLOW_OPACITY,))
        glow = glow_img.filter(ImageFilter.GaussianBlur(40))

        angle = 6
        glow = glow.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        icon = icon.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)

        glow_x = 60 + ICON_SIZE // 2 - glow.width // 2
        glow_y = 260 + ICON_SIZE // 2 - glow.height // 2
        canvas.paste(glow, (glow_x, glow_y), glow)

        icon_x = 60 + ICON_SIZE // 2 - icon.width // 2
        icon_y = 260 + ICON_SIZE // 2 - icon.height // 2
        canvas.alpha_composite(icon, (icon_x, icon_y))

    else:
        print(f"[WARN] Missing icon for {fruit_name}")

    max_name_width = 300
    big_font = fit_font_size(
        draw,
        fruit_name.upper(),
        FONT_PATH,
        max_name_width,
        starting_size=46,
        min_size=28
    )

    draw.text(
        (180, 520),
        fruit_name.upper(),
        font=big_font,
        fill=(255, 255, 255),
        anchor="mm"
    )

    start_x = 360
    start_y = 280
    row_gap = 95
    overall_y = -45

    def row(label, val, y, label_color=(255, 255, 255), value_color=(255, 255, 255), number=0):
        draw.text(
            (start_x, y + overall_y),
            label.upper(),
            font=label_font,
            fill=label_color,
            anchor="lm"
        )

        draw.text(
            (start_x, y + overall_y + 38),
            val,
            font=number_font if number == 1 else label_font,
            fill=value_color,
            anchor="lm"
        )

    row(
        "Physical Value",
        format_currency(physical_value),
        start_y,
        label_color=(220, 220, 220),
        value_color=(170, 255, 190),
        number=1
    )

    row(
        "Permanent Value",
        format_currency(permanent_value),
        start_y + row_gap,
        label_color=(220, 220, 220),
        value_color=(170, 255, 190),
        number=1
    )

    if value_amount:
        row(
            "Value",
            format_currency(value_amount),
            start_y + row_gap * 2,
            label_color=(220, 220, 220),
            value_color=(255, 170, 210),
            number=1
        )
        offset = 3
    else:
        offset = 2

    row(
        "Demand",
        str(demand),
        start_y + row_gap * offset,
        label_color=(220, 220, 220),
        value_color=(255, 215, 140),
        number=1
    )

    if demand_type:
        row(
            "Demand Type",
            demand_type.upper(),
            start_y + row_gap * (offset + 1),
            label_color=(220, 220, 220),
            value_color=(255, 215, 140)
        )

    img = canvas.convert("RGB")
    return img
