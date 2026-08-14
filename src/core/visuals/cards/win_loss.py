from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from src.core.utils.lily_utility import format_currency
from typing import List, Final
from src.core.visuals.components.gradient_text import draw_gradient_text
from src.core.visuals.components.gradient_bar import draw_gradient_bar
from src.core.visuals.utils.pillow_utils import apply_glow


OPTIMIZED: Final = False
ICON_SIZE: Final = 120
VALUE_FONT_OFFSET: Final = 6
W_OR_L_BASE: Final = "public/assets/blox_fruits/win_loss/WORLBase.png"
FRUIT_SUGGESTOR_BASE: Final = "public/assets/blox_fruits/win_loss/FruitSuggestorBase.png"
PERMANENT_ICON_PATH: Final = "public/assets/custom/PermanentIcon.png"
ITEM_ICONS_BASE: Final = "public/assets/blox_fruits/fruit_icons"

def win_loss_img(
        your_fruits: List[str], 
        your_values: List[int], 
        their_fruits: List[str], 
        their_values: List[int],
        your_fruit_types: List[str],
        their_fruit_types: List[str],
        trade_winorlose: str="WIN", 
        trade_conclusion: str="YOUR TRADE IS A L", 
        percentage_Calculation: int=77, 
        winorloseorfair: int = 0, 
        background_type: int=0
    ) -> Image.Image:
    if background_type == 0:
        background_path = W_OR_L_BASE
    else:
        background_path = FRUIT_SUGGESTOR_BASE

    your_coords = [(64, 240), (208, 240), (64, 390), (208, 390)]
    their_coords = [(408, 240), (552, 240), (408, 390), (552, 390)]

    try:
        bg = Image.open(background_path).convert("RGBA")
        img = bg.resize((704, 883))
    except FileNotFoundError:
        print(f"Background not found: {background_path}, using black background.")
        img = Image.new("RGBA", (704, 883), "black")

    ImageDraw.Draw(img)

    def load_font(size):
        try:
            return ImageFont.truetype("src/ui/font/Berlin Sans FB Bold.ttf", size)
        except:
            return ImageFont.load_default()

    font_small = load_font(20)
    font_percentage = load_font(32)
    font_result = load_font(45)
    font_total = load_font(22)

    def paste_fruits(fruits, coords, values, fruit_types):
        total_slots = 4
        nonlocal img
        img = img.convert("RGB")

        for i in range(total_slots):
            coord = coords[i]

            if i < len(fruits):
                fruit = fruits[i]
                val = values[i]
                fruit_type = fruit_types[i]
                try:
                    icon_path = f"{ITEM_ICONS_BASE}/{fruit}.png"
                    icon = Image.open(icon_path).convert("RGBA").resize((ICON_SIZE, ICON_SIZE))

                    avg_color_img = icon.resize((1, 1))
                    pixel = avg_color_img.getpixel((0, 0))
                    
                    if pixel is None:
                        avg_color = (0, 0, 0)
                    elif isinstance(pixel, tuple):
                        avg_color = tuple(int(c) for c in pixel[:3])
                    else:
                        avg_color = (int(pixel), int(pixel), int(pixel))


                    img = apply_glow(img, coord, ICON_SIZE, avg_color)

                    img.paste(icon, coord, icon)

                    value_text_y_offset = ICON_SIZE + 5
                    text_pos = (coord[0] + ICON_SIZE // 2, coord[1] + value_text_y_offset + VALUE_FONT_OFFSET)
                    draw_gradient_text(
                        img, text_pos, f"${format_currency(val)}",
                        font=font_small, gradient_colors=[(186, 85, 211), (0, 191, 255)],
                        anchor="mt", stretch_height=1.1
                    )

                    if "permanent" in fruit_type.lower():
                        perm_icon_size = 44
                        permanent_icon = Image.open(PERMANENT_ICON_PATH).convert("RGBA").resize((perm_icon_size, perm_icon_size))
                        permanent_pos = (coord[0] + ICON_SIZE - perm_icon_size - 6, coord[1] + ICON_SIZE - 36)
                        img.paste(permanent_icon, permanent_pos, permanent_icon)

                except FileNotFoundError:
                    print(f"Missing icon: {fruit}")
            else:
                img = apply_glow(img, coord, ICON_SIZE, (100, 100, 100))

    paste_fruits(your_fruits, your_coords, your_values, your_fruit_types)
    paste_fruits(their_fruits, their_coords, their_values, their_fruit_types)

    your_total = sum(your_values)
    their_total = sum(their_values)
    percent = percentage_Calculation


    your_label_x = (your_coords[0][0] + your_coords[1][0] + ICON_SIZE) // 2
    their_label_x = (their_coords[0][0] + their_coords[1][0] + ICON_SIZE) // 2
    center_x = img.width // 2

    draw_gradient_text(
    img, (your_label_x, 575),
    f"TOTAL: ${format_currency(your_total)}",
    font=font_total,
    gradient_colors=[(128, 255, 255), (255, 128, 255)],
    anchor="mm",
    scale=1.25,            
    stretch_height=1    
)

    draw_gradient_text(
        img, (their_label_x, 575),
        f"TOTAL: ${format_currency(their_total)}",
        font=font_total,
        gradient_colors=[(255, 180, 255), (180, 255, 255)],
        anchor="mm",
        scale=1.25,
        stretch_height=1
    )

    bar_y = 640
    bar_width = 480 
    bar_height = 6    
    bar_x = center_x - bar_width // 2 

    label_offset_y = -35
    conclusion_offset_y = 40

    if winorloseorfair == 0: 
        color_start = (180, 140, 0)
        color_end = (255, 230, 100)
    elif winorloseorfair == 1:  
        color_start = (120, 0, 0)
        color_end = (255, 100, 100)
    else:  
        color_start = (180, 100, 0)
        color_end = (255, 210, 120)

    draw_gradient_bar(
        img, bar_x, bar_y, bar_width, bar_height, percent,
        color_start=color_start, color_end=color_end,
        corner_radius=3
    )

    draw_gradient_text(
        img, (center_x, bar_y + label_offset_y),
        f"{percent}% {trade_winorlose}",
        font=font_percentage,
        gradient_colors=[color_start, color_end],
        anchor="mm",
        scale=1.0
    )

    draw_gradient_text(
        img, (center_x, bar_y + conclusion_offset_y),
        trade_conclusion,
        font=font_result,
        gradient_colors=[color_start, color_end],
        anchor="mm",
        scale=0.75
    )
    return img