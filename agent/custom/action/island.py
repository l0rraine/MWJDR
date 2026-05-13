"""
海岛打理 Custom Action

包含：每日检查、记录日期

每日检查：检查今日是否已完成打理，已完成则跳过。
记录日期：识别到"海岛_协助打理_完成"后记录日期，禁用开关，同日不重复操作。
"""

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from utils import logger
from utils.merchant_utils import save_task_date, disable_switch, daily_check


@AgentServer.custom_action("海岛_每日检查")
class IslandDailyCheck(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        daily_check(context, "海岛打理", "海岛_开关")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("海岛_记录日期")
class IslandRecordDate(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        save_task_date("海岛打理")
        disable_switch(context, "海岛_开关")
        logger.info("海岛打理完成，记录日期")
        return CustomAction.RunResult(success=True)
