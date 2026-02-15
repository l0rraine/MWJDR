from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time
import re
import math

from utils import logger
from utils import timelib
from .combat import CombatRepetitionCount

@AgentServer.custom_action("挖掘宝藏")
class DoDig(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        board = [
            [279,729,77,77],
            [280,812,78,75],
            [283,893,72,74],
            [200,894,76,73],
            [364,812,74,72],
            [362,894,76,72],
            [361,975,79,74],
            [445,814,75,73]
        ]
        for i in range(8):
            logger.debug(f"查看地块{i+1}")
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("自动游历_挖宝_空白地块", img, {
                "自动游历_挖宝_空白地块":{
                    "roi": board[i]
                }
            })
            if detail.hit:
                context.tasker.controller.post_click(
                    detail.box.x, detail.box.y
                    
                ).wait()
                logger.debug(f"点击地块{i+1}")
                time.sleep(1)
        
        return CustomAction.RunResult(success=True)
    

    
@AgentServer.custom_action("米娅宝藏")
class MiaTreasure(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        board = [
            [175,801,46,45],
            [338,808,46,46],
            [503,815,37,40],
            [90,949,48,45],
            [250,951,60,39],
            [423,950,39,38],
            [580,959,39,30],
            [172,1094,39,34],
            [336,1088,41,48],
            [510,1090,36,39]
        ]
        return CustomAction.RunResult(success=True)