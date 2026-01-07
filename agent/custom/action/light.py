from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import time

from utils import timelib,logger

@AgentServer.custom_action("灯塔开始出征")
class LightBeginCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        img = context.tasker.controller.post_screencap().wait().get()             
        _, minutes, seconds = timelib.get_time_from_ocr(context,img,"识别集结时间")
                
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
                return CustomAction.RunResult(success=True)
        time.sleep(return_time*2 + 0.5)
        context.run_task("灯塔入口")        
        return CustomAction.RunResult(success=True)