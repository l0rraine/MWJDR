from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import time

from utils import logger
from utils import timelib
from utils.mfa_config import disable_battle_tasks

@AgentServer.custom_action("野兽开始出征")
class BeastBeginCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        json_data = json.loads(argv.custom_action_param)
        logger.debug(json_data)

        _, minutes, seconds = timelib.get_time_from_ocr(context,"识别集结时间",200)
        return_time = minutes * 60 + seconds

        # 开始出征
        context.run_task("点击出征")
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("体力不足", img)
        if detail.hit:
            detail = context.run_recognition("是否有免费体力",img)
            if detail.hit:
                context.run_task("免费体力")
                context.run_task("点击出征")
            else:
                disable_battle_tasks(context, "自动野兽_入口")
                return CustomAction.RunResult(success=False)

        # img = context.tasker.controller.post_screencap().wait().get()
        # detail = context.run_recognition("自动集结_与别人队伍重复", img)
        # if detail.hit:
        #     context.tasker.controller.post_click(detail.box.x, detail.box.y).wait()
        #     context.run_task("自动野兽_入口")
        #     return CustomAction.RunResult(success=True)


        time.sleep(return_time*2 + 0.5)
        return CustomAction.RunResult(success=True)
