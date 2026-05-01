"""
商人公共工具函数

供联盟商店、神秘商人等共享的工具方法。
"""

import time

from utils import logger
from utils.data_store import load_data, save_data, get_timestamp, set_timestamp

SHOPPING_CATEGORY = "shopping"


def add_offset(box, offset: list) -> list:
    """box 与 offset 逐项相加，兼容 Rect 和 list"""
    if not isinstance(box, list):
        box = [box.x, box.y, box.w, box.h]
    return [a + b for a, b in zip(box, offset)]


def save_merchant_date(merchant_name: str):
    """保存商人购买日期到数据文件

    Args:
        merchant_name: 商人名称，如 "游荡商人"、"神秘商人"
    """
    from custom.reco.record_id import RecordID

    account_id = RecordID.current_account_id()
    data = load_data()
    timestamp_ms = int(time.time() * 1000)
    set_timestamp(data, SHOPPING_CATEGORY, account_id, merchant_name, timestamp_ms)
    if save_data(data):
        logger.debug(f"{merchant_name}购买日期已记录")
    else:
        logger.warning(f"{merchant_name}购买日期记录失败")
