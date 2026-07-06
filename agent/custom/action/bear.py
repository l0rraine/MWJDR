from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from typing import Any, Dict, List, Union, Optional
from maa.define import RectType


from maa.context import Context
import json
import time
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
TRUCK_1 = []
TRUCK_2 = []
TEAM_ORDER = []
SEND_TEAMS = 0
TOTAL_TEAMS = 0
LAST_STAGE = 0
RESERVE_TEAM = 1
FOUND_LEAD_TRUCK = {}
# 已通知"超过40s没开车"的车头集合（元素为 f"{truck}_{stage}"），避免同轮重复打印
_OVER_40S_NOTIFIED = set()
CURRENT_TRUCK = ""
LEAD_TRUCK_OF_CURRENT_STAGE = 0


def get_current_stage(start_time: str = "21:00"):
    today = datetime.now().date()
    start = datetime.combine(today, datetime.strptime(start_time, "%H:%M").time())
    now = datetime.now()
    total_seconds = (now - start).total_seconds()
    stage_seconds = 5 * 60 + 14  # 314 秒
    if total_seconds < 0:
        return 1  # 还没开始
    current_stage = max(1, math.ceil(total_seconds / stage_seconds))

    return current_stage


def next_stage_seconds():
    global START_TIME
    today = datetime.now().date()
    start = datetime.combine(today, datetime.strptime(START_TIME, "%H:%M").time())
    now = datetime.now()
    total_seconds = (now - start).total_seconds()
    stage_seconds = 5 * 60 + 14  # 314 秒
    next_stage = math.ceil(total_seconds / stage_seconds)
    next_stage_time = start + timedelta(seconds=next_stage * stage_seconds)
    seconds = (next_stage_time - now).total_seconds()
    return seconds


# 通知区域 ROI，用于检测“返回城镇”
_NOTIFY_ROI = [212, 327, 324, 138]
_return_cooldown = 0  # 上次扣减时间戳，间隔 >=2s 才视为新通知


def _check_return_notification(context: Context, img) -> None:
    """在主流程截图时顺便检测通知区域是否有"返回城镇"，
    检测到则 SEND_TEAMS -1。两次扣减间隔至少 2s，避免同一条通知重复计数。"""
    global SEND_TEAMS, _return_cooldown

    detail = context.run_recognition(
        "熊_检测返回城镇",
        img,
        pipeline_override={
            "熊_检测返回城镇": {
                "recognition": "OCR",
                "expected": ["返回城镇"],
                "roi": _NOTIFY_ROI,
                "threshold": 0.6,
            }
        },
    )
    if detail and detail.hit:
        now = time.time()
        if now - _return_cooldown >= 2:
            SEND_TEAMS = max(SEND_TEAMS - 1, 0)
            _return_cooldown = now
            logger.debug(f"检测到部队返回，剩余 {SEND_TEAMS} 只队伍")


@AgentServer.custom_action("熊_无剩余队列")
class BearSetSendTeams(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global SEND_TEAMS, TOTAL_TEAMS
        SEND_TEAMS = TOTAL_TEAMS
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_初始化参数")
class BearInitPara(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TRUCK_1, TRUCK_2, TEAM_ORDER, TOTAL_TEAMS, START_TIME, SEND_TEAMS, LAST_STAGE, RESERVE_TEAM, CURRENT_TRUCK, LEAD_TRUCK_OF_CURRENT_STAGE
        # === 初始化 ===
        param = json.loads(argv.custom_action_param)
        start_time_str = param.get("开始时间", "21:00")
        lead_truck_names_str = param.get("大车头", "")
        secondary_truck_names_str = param.get("小车头", "")

        START_TIME = start_time_str

        team_order_str = param.get("循环顺序", "0")
        if not TEAM_ORDER:
            TEAM_ORDER = [
                int(x.strip()) for x in team_order_str.split(",") if x.strip()
            ]

        TRUCK_1 = [
            name.strip() for name in lead_truck_names_str.split(",") if name.strip()
        ]
        TRUCK_2 = [
            name.strip()
            for name in secondary_truck_names_str.split(",")
            if name.strip()
        ]

        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_计算队伍")
class BearComputeTeam(CustomAction):
    """
    计算当前阶段/队伍配置（原 熊_计算队伍）
    """

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TRUCK_1, START_TIME, TEAM_ORDER, FOUND_LEAD_TRUCK, RESERVE_TEAM, TOTAL_TEAMS, LEAD_TRUCK_OF_CURRENT_STAGE, SEND_TEAMS, LAST_STAGE, _OVER_40S_NOTIFIED

        img = context.tasker.controller.post_screencap().wait().get()
        _check_return_notification(context, img)

        current_stage = get_current_stage(START_TIME)

        if current_stage > LAST_STAGE:
            logger.info(f"当前为第 {current_stage} 轮")
            LAST_STAGE = current_stage
            # SEND_TEAMS = 0
            LEAD_TRUCK_OF_CURRENT_STAGE = 0
            _OVER_40S_NOTIFIED.clear()

        if current_stage > 5:
            logger.info("打熊已结束")
            return CustomAction.RunResult(success=False)

        history = {}
        found = 0
        for truck in TRUCK_1:
            for i in range(current_stage):
                if f"{truck}_{i+1}" in FOUND_LEAD_TRUCK:
                    history[truck] = i + 1  # 车头是不是之前识别到过

            # 如果当前不是第一阶段并且这个大车头没有开过车，那么不为这个车头保留队伍
            if history.get(truck, 0) == 0:
                if current_stage > 1:
                    # logger.debug(f"第{current_stage}轮: {truck} 之前没开过车")
                    found = found + 1
            else:
                # 之前开过车，并且这个阶段已经检测到这个大车头，不为这个车头保留队伍
                k = f"{truck}_{current_stage}"
                if k in FOUND_LEAD_TRUCK:
                    found = found + 1
                    # logger.debug(f"第{current_stage}轮: {truck} 已开车")
                else:  # 之前开过车，但是这个阶段超过40s还不开，那就不保留队伍
                    last_remain = FOUND_LEAD_TRUCK[f"{truck}_{history[truck]}"]
                    this_remain = next_stage_seconds()
                    if last_remain - this_remain >= min(40, this_remain):
                        notify_key = f"{truck}_{current_stage}"
                        if notify_key not in _OVER_40S_NOTIFIED:
                            _OVER_40S_NOTIFIED.add(notify_key)
                            logger.debug(
                                f"第{current_stage}轮: {truck} 已经超过 40 秒没开车了"
                            )
                        found = found + 1

            # 之前开过车，这次没开车呢，那就需要保留队伍

        RESERVE_TEAM = len(TRUCK_1) - found
        TOTAL_TEAMS = len(TEAM_ORDER) - RESERVE_TEAM

        # 队伍已全部派出
        # if SEND_TEAMS >= TOTAL_TEAMS:
        #     if LEAD_TRUCK_OF_CURRENT_STAGE == len(TRUCK_1):
        #         # 大车头已全部出现，等待下一阶段
        #         seconds = next_stage_seconds() + 1
        #         logger.info(f"队伍已全部派出，等待下一阶段，剩余时间: {seconds:.0f}秒")
        #         time.sleep(seconds)

        #         new_stage = LAST_STAGE + 1
        #         logger.info(f"当前为第 {new_stage} 轮")
        #         LAST_STAGE = new_stage
        #         SEND_TEAMS = 0
        #         LEAD_TRUCK_OF_CURRENT_STAGE = 0

        return CustomAction.RunResult(success=True)


@AgentServer.custom_recognition("熊_识别队伍")
class BearRecoTeam(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        global TRUCK_1, TRUCK_2, TEAM_ORDER, TOTAL_TEAMS, START_TIME, SEND_TEAMS, LAST_STAGE, RESERVE_TEAM, CURRENT_TRUCK, LEAD_TRUCK_OF_CURRENT_STAGE
        expected = [rf".*{name}.*" for name in TRUCK_1 + TRUCK_2]

        if not expected:
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        img = context.tasker.controller.post_screencap().wait().get()

        team_name_roi = [273, 170, 252, 956]
        join_offset = [310, 87, 0, 58]

        # 1. OCR team_name
        detail = context.run_recognition(
            "熊_识别队伍_team_name",
            img,
            pipeline_override={
                "熊_识别队伍_team_name": {
                    "recognition": "OCR",
                    "expected": expected,
                    "roi": team_name_roi,
                    "threshold": 0.6,
                    "pre_delay": 0,
                    "post_delay": 0,
                }
            },
        )

        if not detail or not detail.hit:
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        # 始终扫描大车头（即使队伍已派完，也需要记录大车头出现情况）
        current_stage = get_current_stage(START_TIME)
        for result in detail.filtered_results:
            truck = next((s for s in TRUCK_1 if s in result.text), "")
            k = f"{truck}_{current_stage}"
            if truck and k not in FOUND_LEAD_TRUCK:
                FOUND_LEAD_TRUCK[k] = next_stage_seconds()
                LEAD_TRUCK_OF_CURRENT_STAGE = LEAD_TRUCK_OF_CURRENT_STAGE + 1
                logger.debug(
                    f"第{current_stage}轮: 发现大车头 {truck}, 现有大车头 {LEAD_TRUCK_OF_CURRENT_STAGE}"
                )

        # 队伍已派完，不再加入，但大车头扫描已在上面完成
        teams_exhausted = SEND_TEAMS >= TOTAL_TEAMS
        if teams_exhausted:
            # if LEAD_TRUCK_OF_CURRENT_STAGE != len(TRUCK_1):
            # logger.debug("队伍已全部派出，继续监控大车头")
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        # 优先识别大车头
        result_sorted = sorted(
            detail.filtered_results,
            key=lambda x: 0 if any(s in x.text for s in TRUCK_1) else 1,
        )

        for result in result_sorted:
            truck_name_box = result.box  # [x, y, w, h]

            # 3. 根据 team_name 坐标 + offset 计算 join ROI
            join_roi = [a + b for a, b in zip(truck_name_box, join_offset)]

            # 4. TemplateMatch join 按钮
            detail = context.run_recognition(
                "熊_识别队伍_join",
                img,
                pipeline_override={
                    "熊_识别队伍_join": {
                        "recognition": "TemplateMatch",
                        "template": "熊/直接加入队伍.png",
                        "roi": join_roi,
                        "threshold": 0.9,
                        "method": 10001,
                        "pre_delay": 0,
                        "post_delay": 0,
                    }
                },
            )

            if detail and detail.hit:
                CURRENT_TRUCK = result.text
                logger.debug(f"准备加入 {CURRENT_TRUCK}")
                return CustomRecognition.AnalyzeResult(box=detail.box, detail={})

        return CustomRecognition.AnalyzeResult(box=None, detail={})


@AgentServer.custom_action("熊_加入集结")
class BearCombat(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TEAM_ORDER, SEND_TEAMS, TOTAL_TEAMS, LEAD_TRUCK_OF_CURRENT_STAGE, TRUCK_1
        if not self._select_team_and_deploy(context, TEAM_ORDER[0]):
            return CustomAction.RunResult(success=True)

        # [1,2,3,4] → [2,3,4,1]
        TEAM_ORDER = TEAM_ORDER[1:] + TEAM_ORDER[:1]

        return CustomAction.RunResult(success=True)

    def _select_team_and_deploy(self, context: Context, team_id: int) -> bool:
        """选择队伍（非默认队伍时点击 ROI）并点击出征。

        返回 True 表示成功出征并返回集结列表。
        """
        global SEND_TEAMS, TOTAL_TEAMS, CURRENT_TRUCK
        if team_id > 0:
            roi = TEAM_ROI[team_id]
            context.run_action(
                "熊_选择队伍", pipeline_override={"熊_选择队伍": {"target": roi}}
            )
        context.run_action("熊_点击出征")

        time.sleep(0.3)
        img = context.tasker.controller.post_screencap().wait().get()

        # from utils.img_util import screen_shot

        # screen_shot(context, "检查熊_士兵超出上限")
        detail = context.run_recognition("熊_士兵超出上限", img)
        if detail and detail.hit:
            logger.debug(f"{team_id} 士兵超出上限,出征失败")
            time.sleep(0.15)
            context.run_action("熊_后退")
            time.sleep(0.15)
            context.run_action("熊_后退")
            return False

        # 此时应已返回集结列表
        detail = context.run_recognition("熊_超出容量", img)
        if detail and detail.hit:
            logger.debug(f"{team_id} 熊_超出容量,出征失败")
            return False

        detail = context.run_recognition("熊_在集结列表", img)
        if detail and detail.hit:
            SEND_TEAMS = SEND_TEAMS + 1
            logger.info(f"{team_id} 号队伍已加入 {CURRENT_TRUCK}")
            return True

        return False


_scroll_cooldown = 0  # 上次滚动时间戳，间隔 >=2s 才滚动


@AgentServer.custom_action("熊_向下滚动")
class BearScrollDown(CustomAction):
    """2s 冷却的向下滚动，冷却期内跳过滑动直接返回成功，不影响识别频率。"""

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global _scroll_cooldown
        now = time.time()
        if now - _scroll_cooldown >= 2:
            _scroll_cooldown = now
            context.run_action(
                "熊_执行滚动",
                pipeline_override={
                    "熊_执行滚动": {
                        "pre_delay": 0,
                        "post_delay": 0,
                        "action": "Swipe",
                        "begin": [433, 909, 14, 10],
                        "end": [423, 792, 21, 11],
                        "duration": 150,
                    }
                },
            )
        return CustomAction.RunResult(success=True)
