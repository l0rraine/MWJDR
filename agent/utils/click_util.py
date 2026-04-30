"""
点击工具

提供基于识别区域的随机点击方法。
"""

import random

from maa.context import Context
from maa.define import Rect

from .logger import logger


def random_click_point(box: Rect) -> tuple[int, int]:
    """
    在识别区域内生成随机点击坐标

    Args:
        box: 识别区域 Rect(x, y, w, h)

    Returns:
        (x, y) 随机坐标元组
    """
    rx = random.randint(box.x, box.x + box.w)
    ry = random.randint(box.y, box.y + box.h)
    logger.debug(f"随机点击坐标: ({rx}, {ry}), 区域: ({box.x}, {box.y}, {box.w}, {box.h})")
    return rx, ry


def click_rect(context: Context, box: Rect):
    """
    在识别区域内随机点击

    自动在 box 范围内生成随机坐标并执行点击。

    Args:
        context: Maa context
        box: 识别区域 Rect(x, y, w, h)
    """
    rx, ry = random_click_point(box)
    context.tasker.controller.post_click(rx, ry).wait()
