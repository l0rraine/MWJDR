"""
联盟商店 Custom Action

包含：入口处理
联盟商店当前为空壳，进入后立即禁用开关并返回商店入口。
"""

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from utils import logger


@AgentServer.custom_action("联盟商店_入口处理")
class UnionShopEntry(CustomAction):
    """联盟商店入口处理：当前为空壳，禁用开关后返回商店入口"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        logger.info("联盟商店当前为空壳，跳过")
        context.override_pipeline({"联盟商店_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"联盟商店_开关": {"enabled": False}})
        context.override_next("联盟商店入口", ["商店购买_入口"])
        return CustomAction.RunResult(success=True)
