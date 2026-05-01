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
from maa.context import Context

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
        if entry not in BATTLE_TASK_ENTRIES:
            continue
        # MFAAvalonia 中 MaaInterfaceTask.Check 映射自 JSON 的 "default_check" 字段
        # 默认值为 false（与 C# 中 public bool? Check = false 一致）
        # 只有 default_check 为 true 时才表示该任务被启用
        default_check = task.get("default_check", False)
        if default_check is True:
            logger.debug(f"发现已启用的战斗任务: {task.get('name', entry)}")
            return True

    return False


def disable_battle_tasks(context: Context, current_entry: str = "") -> bool:
    """
    体力耗尽时，自动禁用当前任务之后已启用的战斗任务

    只禁用 TaskItems 列表中排在当前任务之后的、已启用的战斗任务。
    当前任务之前的战斗任务不会被禁用（因为它们已经执行过了）。

    Args:
        context: MAA Context 实例
        current_entry: 当前正在执行的任务入口名称，用于确定只禁用后续任务

    Returns:
        True:  成功禁用
        False: 禁用失败或无需禁用
    """
    instance_id = get_instance_id()
    if not instance_id:
        logger.debug("非 MFAAvalonia 环境，跳过禁用战斗任务")
        return False

    config_path = _find_instance_config(instance_id)
    if not config_path:
        logger.warning(f"未找到实例配置文件，无法禁用战斗任务: instance_id={instance_id}")
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.warning(f"读取实例配置失败，无法禁用战斗任务: {e}")
        return False

    task_items = config.get("TaskItems", [])
    if not task_items:
        return False

    # 在配置文件中查找当前任务的位置
    current_index = -1
    for i, task in enumerate(task_items):
        if isinstance(task, dict) and task.get("entry", "") == current_entry:
            current_index = i
            break

    # 如果未找到当前任务，回退到禁用所有已启用的战斗任务（安全兜底）
    if current_index == -1:
        logger.warning(
            f"未在配置文件中找到当前任务 '{current_entry}'，"
            f"将禁用所有已启用的战斗任务"
        )

    # 只禁用配置文件中排在当前任务之后的、已启用的战斗任务
    disabled_names = []
    for i, task in enumerate(task_items):
        if not isinstance(task, dict):
            continue
        entry = task.get("entry", "")

        # 跳过当前任务及之前的任务（仅在找到当前任务时）
        if current_index != -1 and i <= current_index:
            continue

        if entry not in BATTLE_TASK_ENTRIES:
            continue
        if task.get("default_check", False) is True:
            context.tasker.resource.override_pipeline({f"{entry}": {"enabled": False}})
            logger.info(f"已自动禁用战斗任务: {entry}")
            disabled_names.append(task.get("name", entry))

    if not disabled_names:
        logger.debug("没有需要禁用的战斗任务")
        return False

    logger.info(f"体力耗尽，已自动禁用后续战斗任务: {', '.join(disabled_names)}")
    return True
