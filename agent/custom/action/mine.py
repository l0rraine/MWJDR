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
MAX_MINE_TEAMS = 4
ALL_MINES = ["肉", "木", "煤", "铁"]
MINES = list(ALL_MINES)

# 节点名 → 矿名的映射
_MINE_NODE_MAP = {
    "挖矿_矿_肉": "肉",
    "挖矿_矿_木": "木",
    "挖矿_矿_煤": "煤",
    "挖矿_矿_铁": "铁",
}


@AgentServer.custom_action("挖矿_设置参数")
class MineSetParam(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global MAX_MINE_TEAMS, MINES

        # 读取 max_teams
        try:
            param = json.loads(argv.custom_action_param)
            MAX_MINE_TEAMS = int(param.get("max_teams", 4))
        except Exception:
            MAX_MINE_TEAMS = 4

        # 通过 get_node_data 读取 checkbox 启用的矿种
        MINES = []
        try:
            next_nodes = context.get_node_data("挖矿_矿种选项")["next"]
            for node_data in next_nodes:
                name = node_data.get("name", "")
                if node_data.get("enabled", False) and name in _MINE_NODE_MAP:
                    MINES.append(_MINE_NODE_MAP[name])
        except Exception:
            MINES = list(ALL_MINES)

        if not MINES:
            MINES = list(ALL_MINES)

        logger.info(f"挖矿配置: 队伍上限={MAX_MINE_TEAMS}, 矿种={MINES}")
        return CustomAction.RunResult(success=True)


def get_current_mines(context: Context, img):
    global MINES
    m = []
    for mine in MINES:
        d = context.run_recognition(
            "挖矿_识别在挖矿",
            img,
            {
                "挖矿_识别在挖矿": {
                    "recognition": "TemplateMatch",
                    "template": f"{mine}.png",
                    "roi": [11, 241, 47, 226],
                    "threshold": 0.8,
                }
            },
        )
        if d and d.hit:
            m.append(mine)
    return m


@AgentServer.custom_recognition("挖矿_识别队伍")
class MineRecoTeam(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        global CURRENT_MINES, LAST_MINES, NEXT_MINE, MINES, MAX_MINE_TEAMS

        img = context.tasker.controller.post_screencap().wait().get()

        detail = context.run_recognition("挖矿_识别队伍数量", img)
        if not detail or not detail.hit:
            logger.debug("无法识别队伍数量")
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        pattern = r"(\d+)\D(\d+)"
        res = re.match(pattern, detail.best_result.text)
        if not res:
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        num1 = res.group(1)
        num2 = res.group(2)

        if num1 == num2:
            logger.debug("队列已满")
            if not LAST_MINES:
                LAST_MINES = get_current_mines(context, img)
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        CURRENT_MINES.clear()
        CURRENT_MINES = get_current_mines(context, img)

        logger.debug(f"CURRENT_MINES:{CURRENT_MINES}")

        if len(CURRENT_MINES) >= MAX_MINE_TEAMS:
            logger.debug(f"已达到最大挖矿队伍数 {MAX_MINE_TEAMS}")
            if not LAST_MINES:
                LAST_MINES = CURRENT_MINES
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        NEXT_MINE = None
        free_mines = [mine for mine in MINES if mine not in CURRENT_MINES]

        for mine in free_mines:
            if mine not in LAST_MINES:
                NEXT_MINE = mine
                break

        if not NEXT_MINE and free_mines:
            NEXT_MINE = free_mines[0]

        logger.debug(
            f"LAST_MINES:{LAST_MINES},CURRENT_MINES:{CURRENT_MINES},NEXT_MINE:{NEXT_MINE}"
        )
        if NEXT_MINE:
            logger.info(f"下一个要挖： {NEXT_MINE}")
            CURRENT_MINES.append(NEXT_MINE)
            LAST_MINES = CURRENT_MINES
            logger.debug(f"LAST_MINES:{LAST_MINES}")
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