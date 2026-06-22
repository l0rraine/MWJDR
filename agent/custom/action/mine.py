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


def _read_mine_config(context: Context) -> None:
    """读取挖矿配置（队伍上限 max_teams 与启用的矿种 MINES）。

    原先由 挖矿_设置参数 Custom Action 在 新手_入口 流程中一次性设置，
    但该节点为 DirectHit 且返回 success=True、next 为空，会导致 新手_入口
    的后续 JumpBack 节点永不执行。现将参数读取移至 挖矿_识别队伍 中实时执行。

    - max_teams：来自"新手-挖矿配置" select 选项对 挖矿_设置参数 节点
      custom_action_param 的覆盖，通过 get_node_data 读取。
    - MINES：遍历 挖矿_矿种选项 的 next，逐个检查 挖矿_矿_X 节点的
      enabled 状态（由"挖矿-矿种" checkbox 选项覆盖）。
    """
    global MINES, MAX_MINE_TEAMS

    # 1. 读取 max_teams
    try:
        node = context.get_node_data("挖矿_设置参数")
        cap = node.get("custom_action_param") if node else None
        # custom_action_param 可能是 dict 或 JSON 字符串，统一处理
        if isinstance(cap, str):
            cap = json.loads(cap) if cap.strip() else {}
        if not isinstance(cap, dict):
            cap = {}
        MAX_MINE_TEAMS = int(cap.get("max_teams", 4))
    except Exception:
        MAX_MINE_TEAMS = 4

    # 2. 读取启用的矿种
    mines: List[str] = []
    try:
        next_nodes = context.get_node_data("挖矿_矿种选项").get("next", [])
        for item in next_nodes:
            # next 项可能是 {"name": ..., "enabled": ...} 或纯字符串，兼容两种
            if isinstance(item, dict):
                name = item.get("name", "")
            elif isinstance(item, str):
                name = item
            else:
                continue
            if not name or name not in _MINE_NODE_MAP:
                continue
            # 直接查节点 enabled，避免依赖 next 项的格式
            node_data = context.get_node_data(name)
            if node_data and node_data.get("enabled", False):
                mines.append(_MINE_NODE_MAP[name])
    except Exception:
        pass

    MINES = mines if mines else list(ALL_MINES)
    logger.info(f"挖矿配置: 队伍上限={MAX_MINE_TEAMS}, 矿种={MINES}")


@AgentServer.custom_action("挖矿_设置参数")
class MineSetParam(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        # 该节点保留为"新手-挖矿配置" select 选项的参数载体
        # （pipeline_override 目标为 挖矿_设置参数.custom_action_param）。
        # 新手流程中不再调用本 action，参数改由 挖矿_识别队伍 实时读取，
        # 以避免 DirectHit + success=True 阻断 新手_入口 的 JumpBack 流程。
        _read_mine_config(context)
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

        # 实时读取挖矿配置（原由 挖矿_设置参数 设置，现移至此处，
        # 确保 新手_入口 的 JumpBack 流程不被 DirectHit 节点阻断）
        _read_mine_config(context)

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