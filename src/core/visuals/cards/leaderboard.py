import asyncio
import io
from typing import Optional, Final, Tuple, Dict

import httpx
import logging
from PIL import Image, ImageDraw, ImageFont
from src.core.configs.path import FONTS as FONT_DIR
from ..utils.pillow_utils import load_image

logger = logging.getLogger("lily")


FONT_BOLD: Final = FONT_DIR / "Poppins-Bold.ttf"
FONT_LIGHT: Final = FONT_DIR / "Poppins-Light.ttf"
FONT_REG: Final = FONT_DIR / "Poppins-Regular.ttf"


async def leaderboard_img(top_members: Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]) -> Optional[bytes]:
    first, second, third = top_members

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            requests = []
            for member in (first, second, third):
                requests.append(client.get(member["avatar_url"]))
                deco_url = member.get("avatar_deco_url") or ""
                requests.append(client.get(deco_url) if deco_url else asyncio.sleep(0, result=None))

            responses = await asyncio.gather(*requests)

            avatar_resps = responses[0::2]
            deco_resps = responses[1::2]

            avatars = []
            decos = []
            for avatar_resp, deco_resp in zip(avatar_resps, deco_resps):
                avatar = load_image(avatar_resp)
                assert avatar is not None
                avatars.append(avatar)
                decos.append(load_image(deco_resp) if deco_resp is not None else None)

    except Exception:
        logger.exception("Failed to build podium leaderboard image")
        return None

    CANVAS_W, CANVAS_H = 720, 400
    BASE_BG = (0, 0, 0, 0)

    CENTER_AVATAR_SIZE = 160
    SIDE_AVATAR_SIZE = 110

    CENTER_DECO_SCALE = 1.25
    SIDE_DECO_SCALE = 1.25  

    CENTER_Y = 90            
    SIDE_Y = 140             

    CENTER_X = (CANVAS_W - CENTER_AVATAR_SIZE) // 2
    LEFT_X = 90              
    RIGHT_X = CANVAS_W - 90 - SIDE_AVATAR_SIZE 

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BASE_BG)
    draw = ImageDraw.Draw(canvas)

    name_font_center = ImageFont.truetype(FONT_BOLD, 26)
    name_font_side = ImageFont.truetype(FONT_BOLD, 18)
    msg_font_center = ImageFont.truetype(FONT_REG, 16)
    msg_font_side = ImageFont.truetype(FONT_REG, 13)

    def paste_avatar_with_deco(
        avatar: Image.Image,
        deco: Image.Image | None,
        size: int,
        deco_scale: float,
        x: int,
        y: int,
        ring_pad: int = 4,
        ring_color: tuple = (20, 21, 24, 255),
    ) -> None:
        side = min(avatar.width, avatar.height)
        left = (avatar.width - side) // 2
        top = (avatar.height - side) // 2
        avatar = avatar.crop((left, top, left + side, top + side))
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)

        ring = Image.new("RGBA", (size + ring_pad * 2, size + ring_pad * 2), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring)
        ring_draw.ellipse((0, 0, ring.width - 1, ring.height - 1), fill=ring_color)
        canvas.paste(ring, (x - ring_pad, y - ring_pad), ring)

        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        canvas.paste(avatar, (x, y), mask)

        if deco is not None:
            deco_size = int(size * deco_scale)
            deco_resized = deco.resize((deco_size, deco_size), Image.Resampling.LANCZOS)
            deco_x = x - (deco_size - size) // 2
            deco_y = y - (deco_size - size) // 2
            canvas.alpha_composite(deco_resized, (deco_x, deco_y))

    def draw_name_and_messages(
        display_name: str,
        messages: str,
        center_x: int,
        top_y: int,
        name_font: ImageFont.FreeTypeFont,
        msg_font: ImageFont.FreeTypeFont,
    ) -> None:
        name_text = f"@{display_name}"
        name_bbox = draw.textbbox((0, 0), name_text, font=name_font)
        name_w = name_bbox[2] - name_bbox[0]
        name_x = center_x - name_w // 2

        draw.text((name_x + 1, top_y + 1), name_text, font=name_font, fill=(0, 0, 0, 140))
        draw.text((name_x, top_y), name_text, font=name_font, fill=(255, 255, 255, 255))

        name_h = name_bbox[3] - name_bbox[1]
        msg_text = f"{messages} messages"
        msg_bbox = draw.textbbox((0, 0), msg_text, font=msg_font)
        msg_w = msg_bbox[2] - msg_bbox[0]
        msg_x = center_x - msg_w // 2
        msg_y = top_y + name_h + 8

        draw.text((msg_x + 1, msg_y + 1), msg_text, font=msg_font, fill=(0, 0, 0, 140))
        draw.text((msg_x, msg_y), msg_text, font=msg_font, fill=(170, 175, 182, 255))

    paste_avatar_with_deco(avatars[1], decos[1], SIDE_AVATAR_SIZE, SIDE_DECO_SCALE, LEFT_X, SIDE_Y)
    draw_name_and_messages(
        second["display_name"], second["messages"],
        LEFT_X + SIDE_AVATAR_SIZE // 2, SIDE_Y + SIDE_AVATAR_SIZE + 16,
        name_font_side, msg_font_side,
    )

    paste_avatar_with_deco(avatars[0], decos[0], CENTER_AVATAR_SIZE, CENTER_DECO_SCALE, CENTER_X, CENTER_Y)
    draw_name_and_messages(
        first["display_name"], first["messages"],
        CANVAS_W // 2, CENTER_Y + CENTER_AVATAR_SIZE + 16,
        name_font_center, msg_font_center,
    )

    paste_avatar_with_deco(avatars[2], decos[2], SIDE_AVATAR_SIZE, SIDE_DECO_SCALE, RIGHT_X, SIDE_Y)
    draw_name_and_messages(
        third["display_name"], third["messages"],
        RIGHT_X + SIDE_AVATAR_SIZE // 2, SIDE_Y + SIDE_AVATAR_SIZE + 16,
        name_font_side, msg_font_side,
    )

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)

    return buf.getvalue()