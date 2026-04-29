"""
MFAAvalonia 实例配置读取工具

MFAAvalonia 在启动 Agent 进程时会注入以下环境变量：
- MFA_INSTANCE_ID: 当前实例 ID
- MFA_INSTANCE_NAME: 当前实例名称
- MFA_DATA_ROOT: MFAAvalonia 的工作目录（由 main.py 在 chdir 前保存）

实例配置文件位于: {MFA_DATA_ROOT}/config/instances/{MFA_INSTANCE_ID}.json
其中 TaskItems 字段存储了用户勾选的任务列表。
"""

import json
import os
from pathlib import Path
from typing import Optional

from .logger import logger

# 战斗任务的 entry 名称（对应 interface.json 中 task[].entry）
BATTLE_TASK_ENTRIES = {
    "自动集结_巨兽入口",       # 集结巨兽
    "自动野兽_入口",           # 自动野兽
    "灯塔入口",                # 自动灯塔
    "集结物品_识别体力入口",   # 使用物品集结
}


def get_instance_id() -> Optional[str]:
    """获取当前 MFAAvalonia 实例 ID"""
    return os.environ.get("MFA_INSTANCE_ID") or None


def get_data_root() -> Optional[Path]:
    """获取 MFAAvalonia DataRoot 路径"""
    data_root = os.environ.get("MFA_DATA_ROOT")
    if data_root and Path(data_root).exists():
        return Path(data_root)
    return None


def _find_instance_config(instance_id: str) -> Optional[Path]:
    """
    查找实例配置文件路径

    搜索策略:
    1. {MFA_DATA_ROOT}/config/instances/{id}.json
    2. 从项目根目录向上搜索 config/instances/{id}.json
    """
    # 策略 1: 从 MFA_DATA_ROOT 查找
    data_root = get_data_root()
    if data_root:
        config_path = data_root / "config" / "instances" / f"{instance_id}.json"
        if config_path.exists():
            return config_path

    # 策略 2: 从项目根目录及其父目录查找
    # project_root = agent/ 的父目录
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent  # agent/

    for parent in [project_root] + list(project_root.parents)[:3]:
        config_path = parent / "config" / "instances" / f"{instance_id}.json"
        if config_path.exists():
            return config_path

    return None


def has_battle_tasks() -> Optional[bool]:
    """
    检查当前实例是否启用了战斗任务

    Returns:
        True:  有已启用的战斗任务
        False: 没有已启用的战斗任务
        None:  无法判断（非 MFAAvalonia 环境，或读取配置失败）
    """
    instance_id = get_instance_id()
    if not instance_id:
        logger.debug("非 MFAAvalonia 环境，无法判断战斗任务")
        return None

    config_path = _find_instance_config(instance_id)
    if not config_path:
        logger.warning(f"未找到实例配置文件: instance_id={instance_id}")
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.warning(f"读取实例配置失败: {e}")
        return None

    task_items = config.get("TaskItems", [])
    if not task_items:
        logger.debug("实例配置中无 TaskItems")
        return None

    for task in task_items:
        if not isinstance(task, dict):
            continue
        entry = task.get("entry", "")
        # check 字段默认为 True（与 MFAAvalonia 的 Check != false 逻辑一致）
        check = task.get("check", True)
        if entry in BATTLE_TASK_ENTRIES and check:
            logger.info(f"发现已启用的战斗任务: {task.get('name', entry)}")
            return True

    logger.info("后续无战斗任务")
    return False
