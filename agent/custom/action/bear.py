from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from rapidocr_onnxruntime import RapidOCR
import json
import time
import threading

from utils import logger
from datetime import datetime, timedelta
import math

# 队伍 ROI，与 combat.py 中 ChangeTeam 一致
# 索引 0 为默认队伍，无需点击
TEAM_ROI = [
    [0, 0, 0, 0],
    [56, 117, 22, 15],
    [127, 115, 26, 23],
    [204, 113, 16, 25],
    [270, 113, 35, 26],
    [349, 117, 22, 22],
    [416, 112, 23, 32],
    [494, 113, 30, 28],
    [565, 113, 30, 29],
]

START_TIME = ""
TEAMS_1 = []
TEAMS_2 = []
DOWN_TEAMS = []
TEAM_ORDER = []
SEND_TEAMS = 0
TOTAL_TEAMS = 0
LAST_STAGE = 1
RESERVE_TEAM = 1
# 每个阶段时长：5分14秒

_monitor_stop = threading.Event()
_teams_lock = threading.Lock()
_monitor_tasker = None  # 主 Tasker 的引用
_monitor_ocr = None  # RapidOCR 引擎

# 监控通知的 ROI
_MONITOR_ROI = [212, 327, 324, 138]
_MONITOR_EXPECTED = "返回城镇"


def _monitor_returned_teams():
    """后台线程：监控'部队已返回'通知，检测到则 SEND_TEAMS -1

    仅使用 controller.post_screencap 获取截图（Controller 级 API，线程安全），
    使用 RapidOCR 做独立 OCR 识别，完全不涉及 MaaFramework Tasker API。
    """
    # 延迟启动避免与主 pipeline 的首次识别争抢
    _monitor_stop.wait(2)
    roi_x, roi_y, roi_w, roi_h = _MONITOR_ROI
    while not _monitor_stop.is_set():
        try:
            img = _monitor_tasker.controller.post_screencap().wait().get()
            if img is None:
                _monitor_stop.wait(0.5)
                continue
            # 裁剪 ROI 区域
            cropped = img[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
            result, _ = _monitor_ocr(cropped)
            if result:
                for item in result:
                    text = item[1]
                    if _MONITOR_EXPECTED in text:
                        global SEND_TEAMS
                        with _teams_lock:
                            SEND_TEAMS = SEND_TEAMS - 1
                        logger.info(f"检测到部队返回，剩余 {SEND_TEAMS} 只队伍")
                        _monitor_stop.wait(2)
                        break
        except Exception as e:
            logger.debug(f"监控线程异常: {e}")
            _monitor_stop.wait(0.2)
            continue
        _monitor_stop.wait(0.5)


def get_current_stage_and_team(start_time: str = "21:00", wait_time: int = 2):
    today = datetime.now().date()
    start = datetime.combine(today, datetime.strptime(start_time, "%H:%M").time())
    now = datetime.now()
    total_seconds = (now - start).total_seconds()
    stage_seconds = 5 * 60 + 14  # 314 秒
    current_team = 1
    if total_seconds < 0:
        return 1, current_team  # 还没开始

    current_stage = math.ceil(total_seconds / stage_seconds)
    if total_seconds > (current_stage - 1) * stage_seconds + 60 * wait_time:
        current_team = 2

    return current_stage, current_team


def next_stage_seconds():
    global START_TIME
    today = datetime.now().date()
    start = datetime.combine(today, datetime.strptime(START_TIME, "%H:%M").time())
    now = datetime.now()
    total_seconds = (now - start).total_seconds()
    stage_seconds = 5 * 60 + 14  # 314 秒
    next_stage = math.ceil(total_seconds / stage_seconds)
    next_stage_time = start + timedelta(seconds=next_stage * stage_seconds)
    seconds = (next_stage_time - now).total_seconds() + 0.5
    logger.info(f"开始等待，剩余时间: {seconds:.0f}秒")
    return seconds


@AgentServer.custom_action("熊_启动返回监控")
class BearStartMonitor(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global _monitor_tasker, _monitor_ocr
        _monitor_tasker = context.tasker
        if _monitor_ocr is None:
            _monitor_ocr = RapidOCR()
            logger.info("RapidOCR 引擎已初始化")
        if not _monitor_stop.is_set():
            _monitor_stop.clear()
            t = threading.Thread(target=_monitor_returned_teams, daemon=True)
            t.start()
            logger.info("部队返回监控已启动")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_停止返回监控")
class BearStopMonitor(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        _monitor_stop.set()
        logger.info("部队返回监控已停止")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_保留队伍")
class BearReserveTeam(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        global RESERVE_TEAM
        RESERVE_TEAM = int(param.get("保留队伍", True))
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_计算队伍")
class BearComputeExpected(CustomAction):

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TEAMS_1, TEAMS_2, TEAM_ORDER, TOTAL_TEAMS, START_TIME, SEND_TEAMS, LAST_STAGE, RESERVE_TEAM

        param = json.loads(argv.custom_action_param)
        start_time_str = param.get("开始时间", "21:00")
        first_team_names_str = param.get("第一梯队", "")
        second_team_names_str = param.get("第二梯队", "")
        wait_time = int(param.get("等待时间", 3))

        START_TIME = start_time_str
        TEAMS_1 = first_team_names_str
        TEAMS_2 = second_team_names_str

        team_order_str = param.get("循环顺序", "0")

        if not TEAM_ORDER:
            TEAM_ORDER = [
                int(x.strip()) for x in team_order_str.split(",") if x.strip()
            ]

        current_stage, current_team = get_current_stage_and_team(
            start_time_str, wait_time
        )
        # 如果在等待过程中过了一个阶段
        if current_stage != LAST_STAGE:
            logger.info(f"当前切换为阶段 {current_stage}")
            SEND_TEAMS = 0
            LAST_STAGE = current_stage
            current_team = 1

        if current_stage > 5:
            _monitor_stop.set()
            logger.info("打熊已结束")
            return CustomAction.RunResult(success=False)

        if current_stage == 5:
            TOTAL_TEAMS = len(TEAM_ORDER)
        else:
            TOTAL_TEAMS = len(TEAM_ORDER) - RESERVE_TEAM

        first_team_names = [name.strip() for name in TEAMS_1.split(",") if name.strip()]
        second_team_names = [
            name.strip() for name in TEAMS_2.split(",") if name.strip()
        ]

        if current_team == 1:
            expected = [rf".*{name}.*" for name in first_team_names]
        else:
            expected = [rf".*{name}.*" for name in first_team_names + second_team_names]

        # logger.debug(
        #     f"当前阶段: {current_stage}，TEAMS_1: {TEAMS_1}, 当前队伍: {current_team}，识别期望: {expected}"
        # )
        pipeline = {
            "熊_识别队伍": {
                "all_of": [
                    {
                        "sub_name": "team_name",
                        "recognition": "OCR",
                        "roi": [273, 170, 252, 956],
                        "expected": expected,
                        "threshold": 0.6,
                    },
                    {
                        "sub_name": "join",
                        "recognition": "TemplateMatch",
                        "template": "熊/直接加入队伍.png",
                        "roi": "team_name",
                        "roi_offset": [310, 87, 0, 58],
                        "threshold": 0.9,
                        "method": 10001,
                    },
                ]
            }
        }
        context.override_pipeline(pipeline)
        context.tasker.resource.override_pipeline(pipeline)
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_加入集结")
class BearCombat(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TEAM_ORDER, SEND_TEAMS, TOTAL_TEAMS

        if not self._select_team_and_deploy(context, TEAM_ORDER[0]):
            return CustomAction.RunResult(success=True)

        # [1,2,3,4] → [2,3,4,1]
        TEAM_ORDER = TEAM_ORDER[1:] + TEAM_ORDER[:1]
        if SEND_TEAMS == TOTAL_TEAMS:
            time.sleep(next_stage_seconds())
            SEND_TEAMS = 0

        return CustomAction.RunResult(success=True)

    def _select_team_and_deploy(self, context: Context, team_id: int) -> bool:
        """选择队伍（非默认队伍时点击 ROI）并点击出征。

        返回 True 表示成功出征并返回集结列表。
        """
        global SEND_TEAMS, TOTAL_TEAMS

        # start = time.time()
        if team_id > 0:
            roi = TEAM_ROI[team_id]
            context.run_action(
                "熊_选择队伍", pipeline_override={"熊_选择队伍": {"target": roi}}
            )
            # time.sleep(0.2)
            # logger.debug(f"选择队伍耗时: {(time.time() - start) * 1000:.0f}ms")
        # start = time.time()
        # 点击出征
        context.run_action("熊_点击出征")
        # logger.debug(f"出征耗时: {(time.time() - start) * 1000:.0f}ms")

        time.sleep(0.2)
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("熊_士兵超出上限", img)
        if detail and detail.hit:
            logger.debug(f"{team_id} 士兵超出上限,出征失败")
            context.run_action("熊_后退")
            context.run_action("熊_后退")
            return False

        # 此时应已返回集结列表
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("熊_超出容量", img)
        if detail and detail.hit:
            logger.debug(f"{team_id} 熊_超出容量,出征失败")
            return False

        detail = context.run_recognition("熊_在集结列表", img)
        if detail and detail.hit:
            SEND_TEAMS = SEND_TEAMS + 1
            logger.info(f"队伍 {team_id} 已出征，剩余 {TOTAL_TEAMS-SEND_TEAMS} 只队伍")
            return True

        # logger.debug(f"{team_id} 出征失败")
        # detail = None
        # while detail is None or not detail.hit:
        #     context.run_action("熊_后退")
        #     time.sleep(0.4)
        #     img = context.tasker.controller.post_screencap().wait().get()
        #     detail = context.run_recognition("熊_在集结列表", img)

        return False
