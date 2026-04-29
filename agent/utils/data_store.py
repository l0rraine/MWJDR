"""
MWJDR 数据持久化工具

用于存储和读取游戏状态数据（如商店购买记录等）。
数据文件位于 config/mwjdr_data.json，按角色ID分桶存储。
"""

import json
import os
from pathlib import Path
from typing import Optional

from .logger import logger

# 默认时间戳：2003年的一个时间戳，确保任何日期检查都不匹配
DEFAULT_TIMESTAMP_MS = 1058306766000

# 数据文件路径
DATA_DIR = Path("config")
DATA_FILE = DATA_DIR / "mwjdr_data.json"


def _get_data_file_path() -> Path:
    """获取数据文件路径，优先使用 MFA_DATA_ROOT 下的 config 目录"""
    data_root = os.environ.get("MFA_DATA_ROOT")
    if data_root and Path(data_root).exists():
        return Path(data_root) / "config" / "mwjdr_data.json"
    return DATA_FILE


def load_data() -> dict:
    """
    加载数据文件

    Returns:
        dict: 数据字典，如果文件不存在则返回空字典
    """
    data_file = _get_data_file_path()
    if not data_file.exists():
        data_file.parent.mkdir(parents=True, exist_ok=True)
        return {}
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取数据文件失败: {e}")
        return {}


def save_data(data: dict) -> bool:
    """
    保存数据到文件

    Args:
        data: 要保存的数据字典

    Returns:
        bool: 是否保存成功
    """
    data_file = _get_data_file_path()
    try:
        data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.warning(f"写入数据文件失败: {e}")
        return False


def get_account_bucket(data: dict, key: str, account_id: str) -> dict:
    """
    获取角色分桶数据

    Args:
        data: 完整数据字典
        key: 数据类别（如 "shopping"）
        account_id: 角色 ID

    Returns:
        dict: 该角色的数据字典
    """
    store = data.get(key)
    if not isinstance(store, dict):
        store = {}
        data[key] = store

    if account_id:
        normalized_id = account_id.strip()
        bucket = store.get(normalized_id)
        if isinstance(bucket, dict):
            return bucket
        bucket = {}
        store[normalized_id] = bucket
        return bucket

    # 无角色 ID 时使用默认 key
    DEFAULT_KEY = "__default__"
    bucket = store.get(DEFAULT_KEY)
    if not isinstance(bucket, dict):
        bucket = {}
        store[DEFAULT_KEY] = bucket
    return bucket


def get_timestamp(data: dict, category: str, account_id: str, item: str) -> int:
    """
    获取某条记录的时间戳

    Args:
        data: 完整数据字典
        category: 数据类别（如 "shopping"）
        account_id: 角色 ID
        item: 记录名称（如 "游荡商人"）

    Returns:
        int: 毫秒级时间戳，如果不存在则返回默认值
    """
    bucket = get_account_bucket(data, category, account_id)
    return bucket.get(item, DEFAULT_TIMESTAMP_MS)


def set_timestamp(data: dict, category: str, account_id: str, item: str, timestamp_ms: int):
    """
    设置某条记录的时间戳

    Args:
        data: 完整数据字典
        category: 数据类别（如 "shopping"）
        account_id: 角色 ID
        item: 记录名称（如 "游荡商人"）
        timestamp_ms: 毫秒级时间戳
    """
    bucket = get_account_bucket(data, category, account_id)
    bucket[item] = timestamp_ms
