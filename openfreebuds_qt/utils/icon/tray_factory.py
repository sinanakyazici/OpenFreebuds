from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from openfreebuds import IOpenFreebuds
from openfreebuds_qt.constants import ASSETS_PATH
from openfreebuds_qt.utils.draw import image_combine_mask, image_spawn_bg_mask

ICON_SIZE = (64, 64)
BATTERY_ICON_SIZE = (256, 256)  # Larger size for battery percentage icons
TRAY_ICON_PATH = ASSETS_PATH / "icon/tray"

# Images
ICON_LOADING = Image.open(TRAY_ICON_PATH / "base_loading.png")
ICON_ANC_OFF = Image.open(TRAY_ICON_PATH / "base_headset.png")
ICON_ANC_ON = Image.open(TRAY_ICON_PATH / "base_headset_1.png")
ICON_ANC_AWR = Image.open(TRAY_ICON_PATH / "base_headset_2.png")
ICON_OVERLAY_ERROR = Image.open(TRAY_ICON_PATH / "overlay_error.png")
ICON_OVERLAY_SETUP = Image.open(TRAY_ICON_PATH / "overlay_setup.png")

# Presets
PRESET_TRANSPARENT = Image.new("RGBA", ICON_SIZE, color="#00000000")
PRESET_LIGHT_MISSING = Image.new("RGBA", ICON_SIZE, color="#FFFFFF33")
PRESET_LIGHT_EMPTY = Image.new("RGBA", ICON_SIZE, color="#FFFFFF77")
PRESET_LIGHT_FULL = Image.new("RGBA", ICON_SIZE, color="#FFFFFFFF")
PRESET_DARK_MISSING = Image.new("RGBA", ICON_SIZE, color="#00000033")
PRESET_DARK_EMPTY = Image.new("RGBA", ICON_SIZE, color="#00000077")
PRESET_DARK_FULL = Image.new("RGBA", ICON_SIZE, color="#000000FF")


def create_tray_icon(theme: str, state: int, battery: int, anc_mode: Optional[str]) -> Image.Image:
    is_dark = theme == "dark"

    if state == IOpenFreebuds.STATE_WAIT or state == IOpenFreebuds.STATE_PAUSED:
        icon = image_combine_mask(ICON_LOADING,
                                  foreground=PRESET_DARK_FULL if is_dark else PRESET_LIGHT_FULL,
                                  background=PRESET_TRANSPARENT)
        return icon
    elif state == IOpenFreebuds.STATE_DISCONNECTED:
        icon = image_combine_mask(ICON_ANC_OFF,
                                  foreground=PRESET_DARK_MISSING if is_dark else PRESET_LIGHT_MISSING,
                                  background=PRESET_TRANSPARENT)
        return icon
    elif state == IOpenFreebuds.STATE_FAILED:
        icon = image_combine_mask(ICON_ANC_OFF,
                                  foreground=PRESET_DARK_MISSING if is_dark else PRESET_LIGHT_MISSING,
                                  background=PRESET_TRANSPARENT)
        icon.alpha_composite(ICON_OVERLAY_ERROR)
        return icon
    elif state == IOpenFreebuds.STATE_STOPPED:
        icon = image_combine_mask(ICON_ANC_OFF,
                                  foreground=PRESET_DARK_MISSING if is_dark else PRESET_LIGHT_MISSING,
                                  background=PRESET_TRANSPARENT)
        icon.alpha_composite(ICON_OVERLAY_SETUP)
        return icon

    # Connected
    power_bg = image_combine_mask(image_spawn_bg_mask(battery / 100, ICON_SIZE),
                                  foreground=PRESET_DARK_FULL if is_dark else PRESET_LIGHT_FULL,
                                  background=PRESET_DARK_EMPTY if is_dark else PRESET_LIGHT_EMPTY)

    if anc_mode == "cancellation":
        icon = ICON_ANC_ON
    elif anc_mode == "awareness":
        icon = ICON_ANC_AWR
    else:
        icon = ICON_ANC_OFF

    result = image_combine_mask(icon,
                                foreground=power_bg,
                                background=PRESET_TRANSPARENT)

    return result


def create_battery_percentage_icon(theme: str, percentage: int) -> Image.Image:
    """Create a simple icon showing battery percentage as text"""
    # Create a transparent background
    img = Image.new("RGBA", ICON_SIZE, color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Get text - only the number without % sign
    text = f"{percentage}"

    # Try to use Tahoma Regular font
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/tahoma.ttf", 48)
    except Exception:
        try:
            font = ImageFont.truetype("tahoma.ttf", 48)
        except Exception:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/tahoma.ttf", 48)
            except Exception:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
                except Exception:
                    font = ImageFont.load_default()

    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Center the text
    x = (ICON_SIZE[0] - text_width) / 2
    y = (ICON_SIZE[1] - text_height) / 2

    # Draw white text
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    return img


def _get_hash(state, battery=0, noise_mode=0):
    if state == IOpenFreebuds.STATE_WAIT or state == IOpenFreebuds.STATE_PAUSED:
        return "state_wait"
    elif state == IOpenFreebuds.STATE_DISCONNECTED:
        return "state_offline"
    elif state == IOpenFreebuds.STATE_FAILED:
        return "state_fail"
    elif state == IOpenFreebuds.STATE_STOPPED:
        return "state_no_dev"

    return "connected_{}_{}".format(noise_mode, battery)
