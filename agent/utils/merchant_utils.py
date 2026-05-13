"""
任务公共工具函数

供商店购买、海岛打理等共享的工具方法。
"""

import time

from maa.context import Context

from utils import logger
from utils import timelib
from utils.data_store import load_data, save_data, get_timestamp, set_timestamp

TASK_CATEGORY = "shopping"


def add_offset(box, offset: list) -> list:
    """box 与 offset 逐项相加，兼容 Rect 和 list"""
    if not isinstance(box, list):
        box = [box.x, box.y, box.w, box.h]
    return [a + b for a, b in zip(box, offset)]


def save_task_date(task_name: str):
    """保存任务完成日期到数据文件

    Args:
        task_name: 任务名称，如 "游荡商人"、"海岛打理"
    """
    from custom.reco.record_id import RecordID

    account_id = RecordID.current_account_id()
    data = load_data()
    timestamp_ms = int(time.time() * 1000)
    set_timestamp(data, TASK_CATEGORY, account_id, task_name, timestamp_ms)
    if save_data(data):
        logger.debug(f"{task_name}完成日期已记录")
    else:
        logger.warning(f"{task_name}完成日期记录失败")


def disable_switch(context: Context, switch_name: str):
    """禁用 pipeline 开关节点"""
    context.override_pipeline({switch_name: {"enabled": False}})
    context.tasker.resource.override_pipeline({switch_name: {"enabled": False}})


def daily_check(context: Context, task_name: str, switch_name: str,
                current_node: str | None = None,
                skip_next: str | None = None) -> bool:
    """通用每日检查：今日已完成则禁用开关并跳过

    Args:
        context: Maa context
        task_name: 任务名称，用于读取/记录时间戳
        switch_name: pipeline 开关节点名，如 "海岛_开关"
        current_node: 已完成时 override_next 的来源节点名
        skip_next: 已完成时 override_next 跳转的目标节点名

    Returns:
        True 表示今日已完成（应跳过），False 表示未完成（应继续）
    """
    from custom.reco.record_id import RecordID

    account_id = RecordID.current_account_id()
    data = load_data()
    timestamp = get_timestamp(data, TASK_CATEGORY, account_id, task_name)

    if timelib.is_today(timestamp):
        logger.info(f"{task_name}今日已完成，跳过 (timestamp={timestamp})")
        disable_switch(context, switch_name)
        if current_node and skip_next:
            context.override_next(current_node, [skip_next])
        return True

    logger.info(f"{task_name}今日未完成，开始执行")
    return False
