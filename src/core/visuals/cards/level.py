import asyncio
import io
from typing import Optional, Final

import httpx
import math
from PIL import Image, ImageDraw, ImageFont
from src.core.configs.path import FONTS as FONT_DIR
from ..utils.pillow_utils import load_image


FONT_REG: Final = FONT_DIR / "Poppins-Regular.ttf"


async def create_level_card(
    display_name: str,
    avatar_url: str,
    avatar_deco_url: str | None,
    nameplate_url: str | None
) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            avatar_response, deco_response, nameplate_response = await asyncio.gather(
                client.get(avatar_url),
                client.get(avatar_deco_url)
                if avatar_deco_url
                else asyncio.sleep(0, result=None),
                client.get(nameplate_url)
                if nameplate_url
                else asyncio.sleep(0, result=None),
            )

            avatar = load_image(avatar_response)

            assert avatar is not None

            avatar_deco = (
                load_image(deco_response)
                if deco_response is not None
                else None
            )
            nameplate = (
                load_image(nameplate_response)
                if nameplate_response is not None
                else None
            )

    except Exception:
        return None
    CARD_W, CARD_H = 720, 160
    CARD_RADIUS = 28

    AVATAR_SIZE = 200
    AVATAR_PAD_X = 10

    DECO_SCALE = 1.25

    OVERFLOW_Y = 24

    deco_extra = int(AVATAR_SIZE * DECO_SCALE) - AVATAR_SIZE
    OVERFLOW_Y = (deco_extra // 2) + 8
    OVERFLOW_X = (deco_extra // 2) + 8

    CANVAS_W = CARD_W + OVERFLOW_X
    CANVAS_H = CARD_H + (OVERFLOW_Y * 2)

    CARD_X = OVERFLOW_X
    CARD_Y = OVERFLOW_Y

    BASE_BG = (32, 34, 39, 255)

    card = Image.new(
        "RGBA",
        (CARD_W, CARD_H),
        BASE_BG
    )


    if nameplate is not None:
        src_ratio = nameplate.width / nameplate.height
        dst_ratio = CARD_W / CARD_H

        if src_ratio > dst_ratio:
            new_h = CARD_H
            new_w = int(new_h * src_ratio)
        else:
            new_w = CARD_W
            new_h = int(new_w / src_ratio)

        nameplate = nameplate.resize((new_w, new_h), Image.Resampling.LANCZOS)

        left = (new_w - CARD_W) // 2
        top = (new_h - CARD_H) // 2
        nameplate = nameplate.crop((left, top, left + CARD_W, top + CARD_H))

        flat_bg = Image.new("RGBA", (CARD_W, CARD_H), BASE_BG)
        nameplate = Image.alpha_composite(flat_bg, nameplate.convert("RGBA"))

        fade = Image.new("L", (CARD_W, CARD_H), 0)
        fade_draw = ImageDraw.Draw(fade)

        fade_start = int(CARD_W * 0.22)
        fade_end = int(CARD_W * 0.85)

        for x in range(CARD_W):
            if x <= fade_start:
                alpha = 0
            elif x >= fade_end:
                alpha = 255
            else:
                alpha = int(255 * (x - fade_start) / (fade_end - fade_start))
            fade_draw.line((x, 0, x, CARD_H), fill=alpha)

        base_layer = Image.new("RGBA", (CARD_W, CARD_H), BASE_BG)

        card = Image.composite(nameplate, base_layer, fade)

        darken = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 70))
        card = Image.alpha_composite(card, darken)
    mask = Image.new(
        "L",
        (CARD_W, CARD_H),
        0
    )

    mask_draw = ImageDraw.Draw(mask)

    mask_draw.rounded_rectangle(
        (
            0,
            0,
            CARD_W - 1,
            CARD_H - 1
        ),
        radius=CARD_RADIUS,
        fill=255
    )

    rounded_card = Image.new(
        "RGBA",
        (CARD_W, CARD_H),
        (0, 0, 0, 0)
    )

    rounded_card.paste(
        card,
        (0, 0),
        mask
    )

    card = rounded_card

    canvas = Image.new(
        "RGBA",
        (CANVAS_W, CANVAS_H),
        (0, 0, 0, 0)
    )

    canvas.alpha_composite(
        card,
        (CARD_X, CARD_Y)
    )

    side = min(
        avatar.width,
        avatar.height
    )

    a_left = (
        avatar.width - side
    ) // 2

    a_top = (
        avatar.height - side
    ) // 2

    avatar = avatar.crop(
        (
            a_left,
            a_top,
            a_left + side,
            a_top + side
        )
    )

    avatar = avatar.resize(
        (AVATAR_SIZE, AVATAR_SIZE),
        Image.Resampling.LANCZOS
    )

    avatar_x = CARD_X + AVATAR_PAD_X - (deco_extra // 2 if avatar_deco is not None else 0)

    if avatar_deco is None:
        avatar_x = CARD_X + AVATAR_PAD_X

    avatar_y = (
        CARD_Y
        + (CARD_H - AVATAR_SIZE) // 2
    )

    ring_pad = 4

    ring = Image.new(
        "RGBA",
        (
            AVATAR_SIZE + ring_pad * 2,
            AVATAR_SIZE + ring_pad * 2
        ),
        (0, 0, 0, 0)
    )

    ring_draw = ImageDraw.Draw(ring)

    ring_draw.ellipse(
        (
            0,
            0,
            ring.width - 1,
            ring.height - 1
        ),
        fill=(20, 21, 24, 255)
    )

    canvas.paste(
        ring,
        (
            avatar_x - ring_pad,
            avatar_y - ring_pad
        ),
        ring
    )

    avatar_mask = Image.new(
        "L",
        (AVATAR_SIZE, AVATAR_SIZE),
        0
    )

    avatar_mask_draw = ImageDraw.Draw(
        avatar_mask
    )

    avatar_mask_draw.ellipse(
        (
            0,
            0,
            AVATAR_SIZE - 1,
            AVATAR_SIZE - 1
        ),
        fill=255
    )

    canvas.paste(
        avatar,
        (
            avatar_x,
            avatar_y
        ),
        avatar_mask
    )

    if avatar_deco is not None:
        deco_size = int(
            AVATAR_SIZE * DECO_SCALE
        )

        avatar_deco = avatar_deco.resize(
            (deco_size, deco_size),
            Image.Resampling.LANCZOS
        )

        deco_x = (
            avatar_x
            - (deco_size - AVATAR_SIZE) // 2
        )

        deco_y = (
            avatar_y
            - (deco_size - AVATAR_SIZE) // 2
        )

        canvas.alpha_composite(
            avatar_deco,
            (deco_x, deco_y)
        )

    draw = ImageDraw.Draw(canvas)

    text_x = (
        CARD_X
        + AVATAR_PAD_X
        + AVATAR_SIZE
        + 10 # this should be edited inorder to move the text in the x axis
    )

    name_font = ImageFont.truetype(
        FONT_REG,
        34
    )

    bbox = draw.textbbox(
        (0, 0),
        display_name,
        font=name_font
    )

    text_h = bbox[3] - bbox[1]

    text_y = (
        CARD_Y - 25 # This should be edited to move the text to the y axis
        + CARD_H // 2
        - text_h // 2
        - bbox[1]
    )

    draw.text(
        (
            text_x + 2,
            text_y + 2
        ),
        display_name,
        font=name_font,
        fill=(0, 0, 0, 140)
    )

    draw.text(
        (
            text_x,
            text_y
        ),
        display_name,
        font=name_font,
        fill=(255, 255, 255, 255)
    )

    buf = io.BytesIO()

    canvas.save(
        buf,
        format="PNG"
    )

    buf.seek(0)

    return buf.getvalue()