import os
import re
from PIL import Image, ImageDraw, ImageFont

CARD_W, CARD_H = 200, 260
ICON_BOX = 152
PAD = 10
RADIUS = 20
BORDER = "#E2E8F0"
TEXT_COLOR = "#1F2937"
MAX_TEXT_W = CARD_W - 20

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]


def _font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    return mask


def _wrap(draw, text, font, max_width):
    words = text.split(" ")
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _draw_label(draw, label, base_size, top_y):
    raw_lines = label.split("\n")
    for size in (base_size, base_size - 2, base_size - 4, base_size - 6):
        font = _font(size)
        lines = []
        for raw in raw_lines:
            lines.extend(_wrap(draw, raw, font, MAX_TEXT_W))
        if len(lines) <= 3:
            break
    ty = top_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((CARD_W - w) / 2, ty), line, fill=TEXT_COLOR, font=font)
        ty += (bbox[3] - bbox[1]) + 7
    return ty


def _base_card(accent):
    card = Image.new("RGBA", (CARD_W, CARD_H), (255, 255, 255, 255))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        [(1, 1), (CARD_W - 2, CARD_H - 2)], radius=RADIUS, outline=BORDER, width=2, fill="white"
    )
    draw.rounded_rectangle([(1, 1), (CARD_W - 2, 7)], radius=RADIUS, fill=accent)
    draw.rectangle([(1, 4), (CARD_W - 2, 8)], fill=accent)
    return card, draw


def compose_card(icon_path, label, out_path, accent):
    card, draw = _base_card(accent)

    icon = Image.open(icon_path).convert("RGBA")
    scale = min(ICON_BOX / icon.width, ICON_BOX / icon.height)
    new_size = (max(1, int(icon.width * scale)), max(1, int(icon.height * scale)))
    icon = icon.resize(new_size, Image.LANCZOS)
    ix = (CARD_W - new_size[0]) // 2
    iy = PAD + 14 + (ICON_BOX - new_size[1]) // 2
    card.alpha_composite(icon, (ix, iy))

    _draw_label(draw, label, 20, PAD + 14 + ICON_BOX + 8)

    mask = _rounded_mask((CARD_W, CARD_H), RADIUS)
    out = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    out.save(out_path)


def compose_text_card(label, out_path, accent):
    """A card with no source logo available: an accent-colored monogram
    chip standing in for the icon, so the layout still reads as a card grid."""
    card, draw = _base_card(accent)

    tokens = re.findall(r"[A-Za-z]+", label)
    if tokens and tokens[0].isupper() and len(tokens[0]) <= 4:
        monogram = tokens[0]
    elif len(tokens) >= 2:
        monogram = (tokens[0][0] + tokens[1][0]).upper()
    elif tokens:
        monogram = tokens[0][:2].upper()
    else:
        monogram = "?"
    chip = min(ICON_BOX, 96)
    cx0 = (CARD_W - chip) // 2
    cy0 = PAD + 14 + (ICON_BOX - chip) // 2
    draw.ellipse([cx0, cy0, cx0 + chip, cy0 + chip], fill=accent)
    mfont = _font(34 if len(monogram) <= 2 else 24)
    bbox = draw.textbbox((0, 0), monogram, font=mfont)
    mw, mh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx0 + (chip - mw) / 2, cy0 + (chip - mh) / 2 - bbox[1]), monogram, fill="white", font=mfont)

    _draw_label(draw, label, 20, PAD + 14 + ICON_BOX + 8)

    mask = _rounded_mask((CARD_W, CARD_H), RADIUS)
    out = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    out.save(out_path)
