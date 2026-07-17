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
from utils.click_util import click_rect

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
CURRENT_TRUCK = ""
# 已通知"超过40s没开车"的车头集合（元素为 f"{truck}_{stage}"），避免同轮重复打印
_OVER_40S_NOTIFIED = set()
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


@AgentServer.custom_action("熊_无剩余队列")
class BearSetSendTeams(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global SEND_TEAMS, TOTAL_TEAMS
        # SEND_TEAMS = TOTAL_TEAMS
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

        expected = [rf".*{name}.*" for name in TRUCK_1]

        pipeline = {
            "熊_识别队伍_大车头": {
                "all_of": [
                    {
                        "sub_name": "team_name",
                        "recognition": "OCR",
                        "roi": [273, 170, 252, 956],
                        "expected": expected,
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

        expected = [rf".*{name}.*" for name in TRUCK_2]
        pipeline = {
            "熊_识别队伍_普通车头": {
                "all_of": [
                    {
                        "sub_name": "team_name",
                        "recognition": "OCR",
                        "roi": [273, 170, 252, 956],
                        "expected": expected,
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


@AgentServer.custom_action("熊_计算队伍")
class BearComputeTeam(CustomAction):
    """
    计算当前阶段/队伍配置（原 熊_计算队伍）
    """

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TRUCK_1, START_TIME, TEAM_ORDER, FOUND_LEAD_TRUCK, RESERVE_TEAM, TOTAL_TEAMS, LEAD_TRUCK_OF_CURRENT_STAGE, SEND_TEAMS, LAST_STAGE, _OVER_40S_NOTIFIED
        current_stage = get_current_stage(START_TIME)

        if current_stage > LAST_STAGE:
            logger.info(f"当前为第 {current_stage} 轮")
            LAST_STAGE = current_stage
            SEND_TEAMS = 0
            LEAD_TRUCK_OF_CURRENT_STAGE = 0
            _OVER_40S_NOTIFIED.clear()

        if current_stage > 5:
            logger.info("打熊已结束")
            return CustomAction.RunResult(success=False)

        # history = {}
        # found = 0
        # for truck in TRUCK_1:
        #     for i in range(current_stage):
        #         if f"{truck}_{i+1}" in FOUND_LEAD_TRUCK:
        #             history[truck] = i + 1  # 车头是不是之前识别到过

        #     # 如果当前不是第一阶段并且这个大车头没有开过车，那么不为这个车头保留队伍
        #     if history.get(truck, 0) == 0:
        #         if current_stage > 1:
        #             # logger.debug(f"第{current_stage}轮: {truck} 之前没开过车")
        #             found = found + 1
        #     else:
        #         # 之前开过车，并且这个阶段已经检测到这个大车头，不为这个车头保留队伍
        #         k = f"{truck}_{current_stage}"
        #         if k in FOUND_LEAD_TRUCK:
        #             found = found + 1
        #             # logger.debug(f"第{current_stage}轮: {truck} 已开车")
        #         else:  # 之前开过车，但是这个阶段超过40s还不开，那就不保留队伍
        #             last_remain = FOUND_LEAD_TRUCK[f"{truck}_{history[truck]}"]
        #             this_remain = next_stage_seconds()
        #             if last_remain - this_remain >= min(40, this_remain):
        #                 notify_key = f"{truck}_{current_stage}"
        #                 if notify_key not in _OVER_40S_NOTIFIED:
        #                     _OVER_40S_NOTIFIED.add(notify_key)
        #                     logger.debug(
        #                         f"第{current_stage}轮: {truck} 已经超过 40 秒没开车了"
        #                     )
        #                 found = found + 1

        # 之前开过车，这次没开车呢，那就需要保留队伍

        # RESERVE_TEAM = len(TRUCK_1) - found
        RESERVE_TEAM = 0
        TOTAL_TEAMS = len(TEAM_ORDER) - RESERVE_TEAM

        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_记录队伍")
class BearCombat(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global CURRENT_TRUCK, SEND_TEAMS, TOTAL_TEAMS, LEAD_TRUCK_OF_CURRENT_STAGE, FOUND_LEAD_TRUCK, START_TIME, TRUCK_1, TRUCK_2
        detail = argv.reco_detail
        # logger.debug(f"熊_记录队伍 reco_detail: {detail}")
        start = time.time()
        and_result = detail.best_result
        team_result = and_result.sub_results[0]
        join_result = and_result.sub_results[1]

        # logger.debug(f"熊_记录队伍 team_result: {team_result.best_result.text}")

        # logger.debug(f"熊_记录队伍 join_result: {join_result.box}")
        box = [a + b for a, b in zip(join_result.box, [5, 5, -10, -10])]
        # logger.debug(f"熊_记录队伍 join_result box: {box}")

        current_stage = get_current_stage(START_TIME)

        truck = next(
            (s for s in TRUCK_1 + TRUCK_2 if s in team_result.best_result.text), ""
        )
        CURRENT_TRUCK = truck
        k = f"{truck}_{current_stage}"
        if truck and k not in FOUND_LEAD_TRUCK:
            FOUND_LEAD_TRUCK[k] = next_stage_seconds()
            LEAD_TRUCK_OF_CURRENT_STAGE = LEAD_TRUCK_OF_CURRENT_STAGE + 1
            logger.debug(
                f"第{current_stage}轮: 发现大车头 {truck}, 现有大车头 {LEAD_TRUCK_OF_CURRENT_STAGE}"
            )
        teams_exhausted = SEND_TEAMS >= TOTAL_TEAMS
        if not teams_exhausted:
            n = {
                "next": [
                    "熊_在队伍选择页面",
                    "熊_在集结详情页面",
                    "熊_士兵超出上限",
                    "熊_队列不足",
                    "熊_超出容量",
                ]
            }
            context.override_pipeline({"熊_识别队伍_大车头": n})
            context.override_pipeline({"熊_识别队伍_普通车头": n})
            click_rect(context, box)
        else:
            n = {"next": ["熊_开始战斗"]}
            pipeline = {"熊_识别队伍_大车头": n}
            context.override_pipeline(pipeline)
            pipeline = {"熊_识别队伍_普通车头": n}
            context.override_pipeline(pipeline)
        end = time.time()
        logger.debug(f"熊_记录队伍 click_rect 耗时: {end - start:.2f} 秒")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("熊_加入集结")
class BearCombat(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TEAM_ORDER, SEND_TEAMS, TOTAL_TEAMS, LEAD_TRUCK_OF_CURRENT_STAGE, TRUCK_1, _scroll_cooldown
        if self._select_team_and_deploy(context, TEAM_ORDER[0]):
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
        detail = context.run_recognition("熊_在集结列表", img)
        # logger.debug(f"熊_加入集结 reco_detail: {detail}")
        if detail and detail.hit:
            SEND_TEAMS = SEND_TEAMS + 1
            logger.info(f"{team_id} 号队伍已加入 {CURRENT_TRUCK}")
            return True
        return False
