from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import re

from maa.custom_recognition import CustomRecognition
from typing import Any, Dict, List, Union, Optional
from maa.define import RectType


from utils import logger

recall_region = [
    [200, 544, 43, 56],
    [200, 484, 43, 56],
    [200, 424, 43, 56],
    [200, 364, 43, 56],
    [200, 304, 43, 56],
    [200, 244, 43, 56],
]
LAST_MINES = []
CURRENT_MINES = []
NEXT_MINE = ""


@AgentServer.custom_recognition("挖矿_识别队伍")
class MineRecoTeam(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        img = context.tasker.controller.post_screencap().wait().get()

        detail = context.run_recognition("挖矿_识别队伍数量", img)
        if not detail or not detail.hit:
            logger.debug("没找到匹配的3/3")
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        pattern = r"(\d+)\D(\d+)"
        res = re.match(pattern, detail.best_result.text)
        if not res:
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        num1 = res.group(1)  # 前数字字符串
        num2 = res.group(2)  # 后数字字符串

        if num1 == num2:
            logger.debug("队列已满")
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        global CURRENT_MINES, LAST_MINES, NEXT_MINE
        CURRENT_MINES.clear()
        mines = ["肉", "木", "煤", "铁"]
        for mine in mines:
            detail = context.run_recognition(
                "挖矿_识别在挖矿",
                img,
                {
                    "挖矿_识别在挖矿": {
                        "recognition": "TemplateMatch",
                        "template": f"{mine}.png",
                        "roi": [11, 241, 47, 226],
                    }
                },
            )
            if detail and detail.hit:
                CURRENT_MINES.append(mine)
        NEXT_MINE = None
        finished_mines = [item for item in LAST_MINES if item not in CURRENT_MINES]
        for mine in mines:
            # 每次都在列表里遍历查找
            if mine not in CURRENT_MINES and mine not in finished_mines:
                NEXT_MINE = mine
                break
        LAST_MINES = CURRENT_MINES
        logger.debug(f"下个矿为{NEXT_MINE}")
        if NEXT_MINE:
            logger.info(f"下一个要挖： {NEXT_MINE}")
            return CustomRecognition.AnalyzeResult(box=detail.box, detail={})
        return CustomRecognition.AnalyzeResult(box=None, detail={})


@AgentServer.custom_recognition("挖矿_识别矿图标")
class MineRecoMine(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        img = context.tasker.controller.post_screencap().wait().get()
        global NEXT_MINE
        detail = context.run_recognition(
            "识别要挖的矿",
            img,
            {
                "识别要挖的矿": {
                    "recognition": "TemplateMatch",
                    "roi": [86, 820, 634, 176],
                    "template": f"{NEXT_MINE}矿.png",
                }
            },
        )
        logger.debug(f"挖矿_识别矿图标: {detail.box}")
        return CustomRecognition.AnalyzeResult(box=detail.box, detail={})
