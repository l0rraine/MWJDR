"""队列状态管理。

提供队列数量的识别与缓存。新手_不可能任务(主循环每轮调用)负责
update 更新缓存；mine/join 的 recognition 直接读缓存判断是否已满，
不再各自 OCR。

连续 3 次识别失败后，执行恢复逻辑：转到城外 → 开始查看队列 →
识别当前队列数量 → 后退回主界面，确保队列能够识别出来。
"""

import re
from typing import Optional, Tuple

from maa.context import Context

from .logger import logger
from .ocr_util import ocr_until_consistent_by_task


class QueueStatus:
    """队列数量缓存与识别。单例（模块级全局）。"""

    # 主界面队列指示器 OCR 节点名（挖矿_识别队伍数量 / 加入集结_识别队列数量
    # 共用同一 roi，这里统一用 挖矿_识别队伍数量）
    _MAIN_OCR_TASK = "挖矿_识别队伍数量"
    # 城外队列面板 OCR 节点名
    _CITY_OCR_TASK = "识别当前队列数量"

    # 缓存
    _num1: int = 0  # 已用队列
    _num2: int = 0  # 总队列
    _fail_count: int = 0  # 连续识别失败次数
    _MAX_FAIL = 3  # 超过此次数执行恢复逻辑

    @classmethod
    def update(cls, context: Context) -> None:
        """识别主界面队列指示器，更新缓存。失败累计 _fail_count，
        超过 _MAX_FAIL 执行恢复逻辑（转到城外查看队列）。

        由 新手_不可能任务(custom_recognition) 在主循环每轮调用。
        """
        text, _ = ocr_until_consistent_by_task(
            context, cls._MAIN_OCR_TASK, expected_pattern=r"^\d\D\d$"
        )
        if text:
            match = re.match(r"(\d)\D(\d)", text)
            if match:
                cls._num1 = int(match.group(1))
                cls._num2 = int(match.group(2))
                cls._fail_count = 0
                return
        # 识别失败
        cls._fail_count += 1
        logger.debug(f"队列数量识别失败({cls._fail_count}/{cls._MAX_FAIL})")
        if cls._fail_count >= cls._MAX_FAIL:
            logger.warning(
                f"队列数量连续{cls._fail_count}次识别失败，执行恢复逻辑"
            )
            cls._recover(context)

    @classmethod
    def _recover(cls, context: Context) -> None:
        """恢复逻辑：转到城外 → 开始查看队列 → 识别当前队列数量 → 后退。

        去掉了原「确保有队列可用」中的关闭自动加入步骤。

        注意：城外队列面板的格式是「空闲/总数」（如 4/5 表示 4 个空闲），
        与主界面指示器「已用/总数」语义相反。这里统一转换为「已用/总数」
        存储，使 is_full 判断一致。
        """
        try:
            context.run_task("转到城外")
            context.run_task("开始查看队列")
            text, _ = ocr_until_consistent_by_task(
                context, cls._CITY_OCR_TASK, expected_pattern=r"\d+/\d+"
            )
            if text:
                match = re.search(r"(\d+)\D+(\d+)", text)
                if match:
                    free = int(match.group(1))  # 空闲队列
                    total = int(match.group(2))  # 总队列
                    # 转换为已用/总数，与主界面语义统一
                    cls._num1 = total - free
                    cls._num2 = total
                    cls._fail_count = 0
                    logger.info(
                        f"恢复识别成功：空闲{free}/{total}，已用{cls._num1}/{cls._num2}"
                    )
                    context.run_task("后退")
                    return
            logger.warning("恢复逻辑未能识别队列数量")
        except Exception as e:
            logger.warning(f"恢复逻辑异常: {e}")
        # 恢复失败也重置计数，避免反复触发
        cls._fail_count = 0

    @classmethod
    def is_full(cls) -> bool:
        """队列是否已满（num1 == num2）。"""
        return cls._num1 >= cls._num2

    @classmethod
    def get_nums(cls) -> Tuple[int, int]:
        """返回 (已用队列, 总队列)。"""
        return cls._num1, cls._num2

    @classmethod
    def reset(cls) -> None:
        """重置缓存（测试/初始化用）。"""
        cls._num1 = 0
        cls._num2 = 0
        cls._fail_count = 0
