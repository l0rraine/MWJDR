from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
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
DOWN_TEAMS = []
TEAM_ORDER = []
SEND_TEAMS = 0
TOTAL_TEAMS = 0
LAST_STAGE = 0
RESERVE_TEAM = 1
FOUND_LEAD_TRUCK = {}
CURRENT_TRUCK = ""
_BEAR_ENDED = False


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
    seconds = (next_stage_time - now).total_seconds() + 0.5
    return seconds


@AgentServer.custom_action("熊_识别队伍")
class BearIdentifyTeam(CustomAction):
    """合并原 熊_计算队伍 + 熊_识别队伍

    1. 计算当前阶段/队伍配置（原 熊_计算队伍）
    2. OCR 识别队伍名，获取匹配内容和坐标
    3. 根据坐标偏移匹配「直接加入」按钮
    4. 同时满足则点击加入
    """

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global TRUCK_1, TRUCK_2, TEAM_ORDER, TOTAL_TEAMS, START_TIME, SEND_TEAMS, LAST_STAGE, RESERVE_TEAM, CURRENT_TRUCK, _BEAR_ENDED

        # === 初始化 ===
        param = json.loads(argv.custom_action_param)
        start_time_str = param.get("开始时间", "21:00")
        lead_truck_names_str = param.get("大车头", "")
        secondary_truck_names_str = param.get("小车头", "")

        START_TIME = start_time_str
        TRUCK_1 = lead_truck_names_str
        TRUCK_2 = secondary_truck_names_str

        team_order_str = param.get("循环顺序", "0")
        if not TEAM_ORDER:
            TEAM_ORDER = [
                int(x.strip()) for x in team_order_str.split(",") if x.strip()
            ]

        current_stage = get_current_stage(start_time_str)
        if current_stage != LAST_STAGE:
            logger.info(f"当前为阶段 {current_stage}")
            LAST_STAGE = current_stage
            SEND_TEAMS = 0

        if current_stage > 5:
            logger.info("打熊已结束")
            _BEAR_ENDED = True
            return CustomAction.RunResult(success=False)

        lead_truck_names = [name.strip() for name in TRUCK_1.split(",") if name.strip()]
        secondary_truck_names = [
            name.strip() for name in TRUCK_2.split(",") if name.strip()
        ]

        expected = [rf".*{name}.*" for name in lead_truck_names + secondary_truck_names]

        if not expected:
            return CustomAction.RunResult(success=False)

        # === 识别车头名称 ===
        team_name_roi = [273, 170, 252, 956]
        join_offset = [310, 87, 0, 58]
        join_target_offset = [5, 5, -10, -10]

        img = context.tasker.controller.post_screencap().wait().get()

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
                }
            },
        )
        if not detail or not detail.hit:
            return CustomAction.RunResult(success=True)

        # 2. 计算当前可派出的队伍总数
        truck_name_text = detail.best_result.text

        history = {}
        found = 0
        for truck in lead_truck_names:
            if current_stage > 1:
                for i in range(current_stage - 1):
                    if f"{truck}_{i+1}" in FOUND_LEAD_TRUCK:
                        history[truck] = i + 1  # 车头是不是之前识别到过

            k = f"{truck}_{current_stage}"

            # 当前识别结果是大车头且不在列表中则补充
            if truck in truck_name_text and k not in FOUND_LEAD_TRUCK:
                FOUND_LEAD_TRUCK[k] = next_stage_seconds()

            # 这个车头之前都没有开车，那这次不管是不是他开车都不等他了
            if history.get(truck, 0) == 0:
                found = found + 1
            else:
                # 之前开过车，并且这次是他开车，这次就不等了
                if k in FOUND_LEAD_TRUCK:
                    found = found + 1
                else:  # 之前开过车，但是这次超过40s还不开，之后就不等了
                    last_remain = FOUND_LEAD_TRUCK[f"{truck}_{history[truck]}"]
                    this_remain = next_stage_seconds()
                    if last_remain - this_remain >= 40:
                        found = found + 1

            # 之前开过车，这次没开车呢，那就需要等他

        RESERVE_TEAM = len(lead_truck_names) - found
        TOTAL_TEAMS = len(TEAM_ORDER) - RESERVE_TEAM

        truck_name_box = detail.box  # [x, y, w, h]

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
                }
            },
        )
        if not detail or not detail.hit:
            return CustomAction.RunResult(success=True)

        CURRENT_TRUCK = truck_name_text

        # 5. 两个都匹配，点击加入按钮
        join_box = detail.box
        click_target = [a + b for a, b in zip(join_box, join_target_offset)]

        context.run_action(
            "熊_点击加入按钮",
            pipeline_override={
                "熊_点击加入按钮": {
                    "pre_delay": 0,
                    "post_delay": 0,
                    "action": "Click",
                    "target": click_target,
                    "repeat": 2,
                    "repeat_delay": 100,
                }
            },
        )

        time.sleep(0.3)

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
            seconds = next_stage_seconds()
            logger.info(f"开始等待，剩余时间: {seconds:.0f}秒")
            time.sleep(seconds)
            SEND_TEAMS = 0

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
            logger.info(f"{team_id} 号队伍已加入 {CURRENT_TRUCK}")
            return True

        return False


@AgentServer.custom_action("熊_向下滚动")
class BearScrollDown(CustomAction):
    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global _BEAR_ENDED
        if _BEAR_ENDED:
            return CustomAction.RunResult(success=False)
        context.run_action(
            "__bear_scroll",
            pipeline_override={
                "__bear_scroll": {
                    "action": "Swipe",
                    "begin": [433, 909, 14, 10],
                    "end": [423, 792, 21, 11],
                    "duration": 100,
                    "post_delay": 200,
                }
            },
        )
        return CustomAction.RunResult(success=True)
