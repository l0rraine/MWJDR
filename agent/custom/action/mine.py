from maa.agent.agent_server import AgentServer
from maa.context import Context
import json
import re

from maa.custom_recognition import CustomRecognition
from typing import List, Union, Optional
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
    """读取用户勾选的矿种 MINES。

    矿种由"挖矿-矿种" checkbox 选项控制：勾选某矿种时，通过 pipeline_override
    将对应 挖矿_矿_X 节点的 enabled 置为 true。此处遍历 挖矿_矿种选项.next，
    逐个检查 挖矿_矿_X 节点的 enabled 状态。

    注：队伍上限 max_teams 不在此读取，改由 MineRecoTeam.analyze() 通过
    argv.custom_recognition_param 读取（框架调用 recognition 时实时注入，
    必定反映 select 选项的 override）。
    """
    global MINES
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

        # 读取队伍上限 max_teams：由"新手-挖矿配置" select 选项通过
        # pipeline_override 注入 挖矿_入口.custom_recognition_param，
        # 框架调用 recognition 时经 argv 传入，必定反映 override。
        # （此前曾用 get_node_data 读 挖矿_设置参数.custom_action_param，
        # 但该字段未反映 select override，导致读取到默认值 4，故改回 argv 机制）
        try:
            param = json.loads(argv.custom_recognition_param)
            MAX_MINE_TEAMS = int(param.get("max_teams", 4))
        except Exception:
            MAX_MINE_TEAMS = 4

        # 读取用户勾选的矿种 MINES
        _read_mine_config(context)

        img = context.tasker.controller.post_screencap().wait().get()

        if not LAST_MINES:
            LAST_MINES = get_current_mines(context, img)

        # 队列判断：直接读 QueueStatus 缓存（由 新手_不可能任务 定期更新）
        from utils.queue_status import QueueStatus

        if QueueStatus.is_full():
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        CURRENT_MINES.clear()
        CURRENT_MINES = get_current_mines(context, img)

        # logger.debug(f"LAST_MINES:{LAST_MINES},CURRENT_MINES:{CURRENT_MINES}")

        if len(CURRENT_MINES) >= MAX_MINE_TEAMS:
            if not LAST_MINES:
                LAST_MINES = list(CURRENT_MINES)
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        NEXT_MINE = None
        free_mines = [mine for mine in MINES if mine not in CURRENT_MINES]

        for mine in free_mines:
            if mine not in LAST_MINES:
                NEXT_MINE = mine
                break

        if not NEXT_MINE and free_mines:
            NEXT_MINE = free_mines[0]

        if NEXT_MINE:
            logger.info(f"派出挖矿队伍：{NEXT_MINE}")
            CURRENT_MINES.append(NEXT_MINE)
            LAST_MINES = list(CURRENT_MINES)
            # 返回任意非 None box 表示命中（挖矿_入口 无 Click action，
            # 命中后走 next 挖矿_点击放大镜）
            return CustomRecognition.AnalyzeResult(box=[0, 0, 1, 1], detail={})
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
        return CustomRecognition.AnalyzeResult(box=detail.box, detail={})
