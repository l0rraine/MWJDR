from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time

from utils import logger
@AgentServer.custom_action("开始派出挖矿队伍")
class SendMineQueue(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        logger.debug(f"联盟矿参数")
        json_data = json.loads(argv.custom_action_param)
        logger.debug(f"联盟矿参数:{json_data}")
        return CustomAction.RunResult(success=True)

@AgentServer.custom_action("自动加入参数")
class ReserveAutoJoin(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        json_data = json.loads(argv.custom_action_param)
        logger.debug(f"自动加入参数:{json_data}")
        
        return CustomAction.RunResult(success=True)
    
@AgentServer.custom_action("召回全部队伍")
class RecallAllQueue(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        # 1. 关闭自动加入
        logger.debug("关闭自动加入集结")
        context.run_task("关闭自动加入集结入口")
        context.run_task("转到城外")
        context.run_task("开始查看队列")
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("识别当前队列数量", img)
        context.run_task("后退")
        img = context.tasker.controller.post_screencap().wait().get()
        if detail.hit:
            a, b = map(int, detail.best_result.text.split('/'))
            logger.info("f当前队列数量为：{a}/{b}")
            
            # 2. 召回全部挖矿队伍
            recall_region = [
                    [200,544,43,56],
                    [200,484,43,56],
                    [200,424,43,56],
                    [200,364,43,56],
                    [200,304,43,56],
                    [200,244,43,56]
                    
                ]
            img = context.tasker.controller.post_screencap().wait().get()
            for region in recall_region[-b:]:
                context.run_task("点击召回",{
                    "点击召回": {
                        "target": region
                    }
                })
            logger.info("开始等待队伍回归")
            context.run_task("开始查看队列")
            while True:
                    time.sleep(3)
                    img = context.tasker.controller.post_screencap().wait().get()
                    detail = context.run_recognition("识别当前队列数量", img)
                    if not detail.hit:
                        context.run_task("后退")
                        break        
        return CustomAction.RunResult(success=True)