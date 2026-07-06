from datetime import datetime
import os
import re
from maa.context import Context
from PIL import Image
from .logger import logger


def screen_shot(context: Context, text: str):
    screen_array = context.tasker.controller.post_screencap().wait().get()

    # Check resolution aspect ratio
    # height, width = screen_array.shape[:2]
    # aspect_ratio = width / height
    # target_ratio = 9 / 16
    # # Allow small deviation (within 1%)
    # if abs(aspect_ratio - target_ratio) / target_ratio > 0.01:
    #     logger.error(f"当前模拟器分辨率不是9:16! 当前分辨率: {width}x{height}")

    # BGR2RGB
    if len(screen_array.shape) == 3 and screen_array.shape[2] == 3:
        rgb_array = screen_array[:, :, ::-1]
    else:
        rgb_array = screen_array
        logger.warning("当前截图并非三通道")

    img = Image.fromarray(rgb_array)

    save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "temp")
    os.makedirs(save_dir, exist_ok=True)
    now = datetime.now()
    text = re.sub(r"[*?]", "", text)
    name = f"{text}_" if text else ""
    name = name + now.strftime("%Y%m%d%H%M%S.") + f"{now.microsecond // 1000:03d}.png"
    img.save(os.path.join(save_dir, name))
    logger.debug(f"截图保存至 temp/{name}")
