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
from utils import timelib
from utils.data_store import load_data, get_timestamp
from utils.merchant_utils import save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID


@AgentServer.custom_action("海岛_每日检查")
class IslandDailyCheck(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        account_id = RecordID.current_account_id()
        data = load_data()
        timestamp = get_timestamp(data, SHOPPING_CATEGORY, account_id, "海岛打理")

        if timelib.is_today(timestamp):
            logger.info(f"海岛打理今日已完成，跳过 (timestamp={timestamp})")
            context.override_pipeline({"海岛_开关": {"enabled": False}})
            context.tasker.resource.override_pipeline({"海岛_开关": {"enabled": False}})
            return CustomAction.RunResult(success=True)

        logger.info("海岛打理今日未完成，开始打理")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("海岛_记录日期")
class IslandRecordDate(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        save_merchant_date("海岛打理")
        context.override_pipeline({"海岛_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"海岛_开关": {"enabled": False}})
        logger.info("海岛打理完成，记录日期")
        return CustomAction.RunResult(success=True)
