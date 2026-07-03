from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
import json
import re
import time

from maa.custom_recognition import CustomRecognition
from typing import List, Union, Optional
from maa.define import RectType


from utils.ocr_util import ocr_until_consistent_by_task
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
                    "roi": [12, 248, 45, 361],
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

        # 队列未识别成功
        if QueueStatus._if_fail == 1:
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
            logger.debug(f"LAST_MINES={LAST_MINES},CURRENT_MINES={CURRENT_MINES}")
            logger.info(f"派出挖矿队伍：{NEXT_MINE}")
            CURRENT_MINES.append(NEXT_MINE)
            LAST_MINES = list(CURRENT_MINES)
            # 返回任意非 None box 表示命中（挖矿_入口 无 Click action，
            # 命中后走 next 挖矿_点击放大镜）
            return CustomRecognition.AnalyzeResult(box=[0, 0, 1, 1], detail={})
        return CustomRecognition.AnalyzeResult(box=None, detail={})


@AgentServer.custom_recognition("挖矿_识别矿图标")
class MineRecoMine(CustomRecognition):
    """识别矿图标。

    先模板匹配矿图标(找到要挖的矿)，再 OCR 当前矿等级。
    返回矿图标 box，框架 Click 选中该矿。
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        global NEXT_MINE
        img = context.tasker.controller.post_screencap().wait().get()

        # 1. 先模板匹配矿图标（找到要挖的矿）
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
        if not detail or not detail.box:
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        # 返回矿图标 box，框架 Click 选中该矿
        return CustomRecognition.AnalyzeResult(box=detail.box, detail={})


MINE_LEVEL = 0


@AgentServer.custom_action("挖矿_设置等级")
class MineSetLevel(CustomAction):
    """调整矿等级至默认值并搜索。

    识别的当前等级 与 level 参数（默认采矿等级），
    不相同则点击减少/增加按钮调整，每50ms点击一次，直至相等。
    之后点击搜索按钮。
    """

    global MINE_LEVEL
    # 减少按钮 roi
    _DECREASE_ROI = [53, 1042, 33, 28]
    # 增加按钮 roi
    _INCREASE_ROI = [477, 1046, 16, 15]

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        img = context.tasker.controller.post_screencap().wait().get()

        MINE_LEVEL, _ = ocr_until_consistent_by_task(
            context,
            "挖矿_识别矿等级",
            pipeline_override={
                "挖矿_识别矿等级": {
                    "recognition": "OCR",
                    "expected": "\\d+",
                    "roi": [584, 1029, 44, 48],
                }
            },
            expected_pattern=r"^\d$",
        )
        MINE_LEVEL = int(MINE_LEVEL) if MINE_LEVEL else 1

        param = json.loads(argv.custom_action_param)
        default_level = int(param.get("level", 8))

        logger.debug(f"挖矿_设置等级: {default_level}, 当前等级={MINE_LEVEL}")

        if MINE_LEVEL != default_level and MINE_LEVEL > 0:
            if MINE_LEVEL > default_level:
                # 需要降级，点击减少按钮
                diff = MINE_LEVEL - default_level
                roi = self._DECREASE_ROI
                action_name = "挖矿_减少等级"
                logger.info(f"矿等级 {MINE_LEVEL} -> {default_level}，减少 {diff} 次")
            else:
                # 需要升级，点击增加按钮
                diff = default_level - MINE_LEVEL
                roi = self._INCREASE_ROI
                action_name = "挖矿_增加等级"
                logger.info(f"矿等级 {MINE_LEVEL} -> {default_level}，增加 {diff} 次")
            for _ in range(diff):
                context.run_action(
                    action_name,
                    pipeline_override={action_name: {"action": "Click", "target": roi}},
                )
                time.sleep(0.1)
        else:
            logger.debug(f"矿等级 {MINE_LEVEL} == 默认 {default_level}，无需调整")

        # 点击搜索按钮
        context.run_action("挖矿_点击搜索")
        time.sleep(1)
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("挖矿_降级搜索")
class MineDowngradeSearch(CustomAction):
    """点搜索后若未识别到"采集"，循环降级搜索直到识别到。

    点击 [53,1042,33,28] 降一级 → 点搜索 → 等待 → 识别"采集"，
    直到识别到则点击采集并出征。
    """

    # 降级按钮 roi
    _DOWNGRADE_ROI = [53, 1042, 33, 28]
    # 采集按钮 OCR roi
    _COLLECT_ROI = [284, 602, 152, 58]

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global MINE_LEVEL
        # 先识别一次"采集"（设置等级后已点搜索）
        if self._try_collect(context):
            return CustomAction.RunResult(success=True)

        # 降级循环，最大次数为当前矿等级（MINE_LEVEL 为 0 时至少降 8 次）
        max_down = MINE_LEVEL if MINE_LEVEL > 0 else 8
        for _ in range(max_down):
            # logger.debug("未识别到采集，降级搜索")
            context.run_action(
                "挖矿_降级点击",
                pipeline_override={
                    "挖矿_降级点击": {"action": "Click", "target": self._DOWNGRADE_ROI}
                },
            )
            time.sleep(0.5)
            context.run_action("挖矿_点击搜索")
            time.sleep(1)
            if self._try_collect(context):
                return CustomAction.RunResult(success=True)

        logger.warning("降级搜索超过最大次数仍未识别到采集")
        return CustomAction.RunResult(success=True)

    def _try_collect(self, context: Context) -> bool:
        """识别"采集"并点击，返回是否识别到。"""
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition(
            "挖矿_点击采集",
            img,
            pipeline_override={
                "挖矿_点击采集": {
                    "recognition": "OCR",
                    "expected": "采集",
                    "roi": self._COLLECT_ROI,
                }
            },
        )
        if detail and detail.hit:
            context.run_action(
                "挖矿_点击采集",
                pipeline_override={"挖矿_点击采集": {"target": list(detail.box)}},
            )
            return True
        return False
