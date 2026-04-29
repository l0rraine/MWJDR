from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import time

from utils import timelib,logger
from utils.mfa_config import disable_battle_tasks

@AgentServer.custom_action("灯塔开始出征")
class LightBeginCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        
        _, minutes, seconds = timelib.get_time_from_ocr(context,"识别集结时间",200)                
        return_time = minutes * 60 + seconds
        
        logger.debug(f"返回时间：{return_time}")
        
        # 开始出征
        context.run_task("点击出征")
        time.sleep(0.5)
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("体力不足", img)
        if detail.hit:
            detail = context.run_recognition("是否有免费体力",img)
            if detail.hit:
                context.run_task("免费体力")
                context.run_task("点击出征")
            else:
                disable_battle_tasks("灯塔入口")
                return CustomAction.RunResult(success=False)
        time.sleep(return_time*2 + 0.5)
        return CustomAction.RunResult(success=True)