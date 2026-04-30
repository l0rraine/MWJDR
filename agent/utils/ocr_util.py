"""
OCR 工具

提供关键数据的高可靠性 OCR 读取方法。
"""

import re
import time

from maa.context import Context
from maa.pipeline import JRecognitionType, JOCR

from .logger import logger


def ocr_until_consistent(
    context: Context,
    roi: list,
    expected_pattern: str = None,
    consistent_count: int = 3,
    max_attempts: int = 30,
) -> str | None:
    """
    OCR 读取直到获得多次完全一致的结果

    适用于关键数据（如角色ID）的高可靠性读取。
    每次读取先用正则过滤不合法结果，合法结果与历史记录比较，
    当连续获得 consistent_count 次完全相同的结果时采用。

    Args:
        context: Maa context
        roi: OCR 区域 [x, y, w, h]
        expected_pattern: 正则表达式过滤，不匹配的结果直接丢弃（如 "^\\d{9}$"）
        consistent_count: 需要连续一致的次数，默认 3
        max_attempts: 最大尝试次数，默认 30

    Returns:
        str: 识别结果，失败返回 None
    """
    last_result = None
    same_count = 0

    for attempt in range(1, max_attempts + 1):
        try:
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition_direct(
                JRecognitionType.OCR,
                JOCR(roi=roi, only_rec=True),
                img,
            )

            if not detail or not detail.hit:
                logger.debug(f"OCR第{attempt}次：未识别到内容")
                same_count = 0
                continue

            text = detail.best_result.text.strip()

            # 正则过滤
            if expected_pattern and not re.match(expected_pattern, text):
                logger.debug(f"OCR第{attempt}次：结果'{text}'不匹配正则'{expected_pattern}'，丢弃")
                same_count = 0
                continue

            # 一致性校验
            if text == last_result:
                same_count += 1
                logger.debug(f"OCR第{attempt}次：'{text}'一致（{same_count}/{consistent_count}）")
                if same_count >= consistent_count:
                    logger.debug(f"OCR一致性校验通过：'{text}'（{consistent_count}次一致）")
                    return text
            else:
                last_result = text
                same_count = 1
                logger.debug(f"OCR第{attempt}次：'{text}'（1/{consistent_count}）")

        except Exception as e:
            logger.debug(f"OCR第{attempt}次异常：{e}")
            same_count = 0

        time.sleep(0.3)

    logger.warning(f"OCR一致性校验失败：超过最大尝试次数{max_attempts}，最后结果'{last_result}'")
    return None
