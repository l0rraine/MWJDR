"""
点击工具

提供基于识别区域的随机点击方法。
"""

import random

from maa.context import Context
from maa.define import Rect

from .logger import logger


def _to_rect(box: Rect | list) -> Rect:
    """
    将 Rect 或 [x, y, w, h] 列表统一转换为 Rect

    Args:
        box: Rect 对象或 [x, y, w, h] 列表

    Returns:
        Rect 对象
    """
    if isinstance(box, list | tuple):
        return Rect(box[0], box[1], box[2], box[3])
    return box


def random_click_point(box: Rect | list) -> tuple[int, int]:
    """
    在识别区域内生成随机点击坐标

    Args:
        box: 识别区域 Rect(x, y, w, h) 或 [x, y, w, h]

    Returns:
        (x, y) 随机坐标元组
    """
    rect = _to_rect(box)
    rx = random.randint(rect.x, rect.x + rect.w)
    ry = random.randint(rect.y, rect.y + rect.h)
    # logger.debug(f"随机点击坐标: ({rx}, {ry}), 区域: ({rect.x}, {rect.y}, {rect.w}, {rect.h})")
    return rx, ry


def click_rect(context: Context, box: Rect | list):
    """
    在识别区域内随机点击

    自动在 box 范围内生成随机坐标并执行点击。

    Args:
        context: Maa context
        box: 识别区域 Rect(x, y, w, h) 或 [x, y, w, h]
    """
    rx, ry = random_click_point(box)
    context.tasker.controller.post_click(rx, ry).wait()
