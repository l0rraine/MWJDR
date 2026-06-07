from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JActionType, JClick, JSwipe
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
TEAMS_1 = []
TEAMS_2 = []
DOWN_TEAMS = []
TEAM_ORDER = []
SEND_TEAMS = 0
TOTAL_TEAMS = 0
LAST_STAGE = 1
# 每个阶段时长：5分14秒


def get_current_stage_and_team(start_time: str = "21:00", wait_time: int = 2):
    # 1. 获取今天的 日期 + 开始时间
    today = datetime.now().date()
    start = datetime.combine(today, datetime.strptime(start_time, "%H:%M").time())

    # 2. 获取当前系统时间
    now = datetime.now()

    # 3. 计算时间差（秒）
    total_seconds = (now - start).total_seconds()

    # 4. 阶段时长：5分14秒
    stage_seconds = 5 * 60 + 14  # 314 秒

    current_team = 1
    # 5. 计算当前阶段（从 1 开始）
    if total_seconds < 0:
        return 1, current_team  # 还没开始

    current_stage = math.floor(total_seconds / stage_seconds) + 1
    if total_seconds > (current_stage-1)*stage_seconds+60*wait_time:
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
    seconds = (next_stage_time - now).total_seconds() - 2  # 提前 2 秒醒来准备
    logger.info(f"开始等待，剩余时间: {seconds:.0f}秒")
    return seconds


@AgentServer.custom_action("熊_计算队伍")
class BearComputeExpected(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        global TEAMS_1, TEAMS_2, TEAM_ORDER, TOTAL_TEAMS, START_TIME, SEND_TEAMS, LAST_STAGE

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
            SEND_TEAMS = 0
            LAST_STAGE = current_stage
            current_team = 1

        if current_stage > 5:
            logger.info("打熊已结束")
            return CustomAction.RunResult(success=False)

        if current_stage == 5:
            TOTAL_TEAMS = len(TEAM_ORDER)
        else:
            TOTAL_TEAMS = len(TEAM_ORDER) - 1

        first_team_names = [
            name.strip() for name in TEAMS_1.split(",") if name.strip()
        ]
        second_team_names = [
            name.strip() for name in TEAMS_2.split(",") if name.strip()
        ]

        if current_team == 1:
            expected = [rf".*{name}.*" for name in first_team_names]
        else:
            expected = [
                rf".*{name}.*" for name in first_team_names+second_team_names
            ]

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
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        global TEAM_ORDER, SEND_TEAMS, TOTAL_TEAMS
        logger.debug(f"当前循环顺序: {TEAM_ORDER},共可派出队伍 {TOTAL_TEAMS} 支")
        if not self._select_team_and_deploy(context, TEAM_ORDER[0]):
            return CustomAction.RunResult(success=True)

        # [1,2,3,4] → [2,3,4,1]
        TEAM_ORDER = TEAM_ORDER[1:] + TEAM_ORDER[:1]
        SEND_TEAMS = SEND_TEAMS+1
        if SEND_TEAMS == TOTAL_TEAMS:            
            time.sleep(next_stage_seconds())
            SEND_TEAMS = 0

        return CustomAction.RunResult(success=True)

    def _select_team_and_deploy(self, context: Context, team_id: int) -> bool:
        """选择队伍（非默认队伍时点击 ROI）并点击出征。

        返回 True 表示成功出征并返回集结列表。
        """
        global SEND_TEAMS, TOTAL_TEAMS

        start = time.time()
        if team_id > 0:
            roi = TEAM_ROI[team_id]
            context.run_action("熊_选择队伍",pipeline_override={
                "熊_选择队伍": {
                    "target": roi
                }})
            # time.sleep(0.2)
            logger.debug(f"选择队伍耗时: {(time.time() - start) * 1000:.0f}ms")
        start = time.time()
        # 点击出征
        context.run_action("熊_点击出征")
        logger.debug(f"出征耗时: {(time.time() - start) * 1000:.0f}ms")

        time.sleep(0.15)
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("熊_士兵超出上限", img)
        if detail is not None and detail.hit:
            logger.debug(f"{team_id} 士兵超出上限,出征失败")
            context.run_action("熊_后退")
            context.run_action("熊_后退")
            return False
        
        # 此时应已返回集结列表
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("熊_超出容量", img)
        if detail is not None and detail.hit:
            logger.debug(f"{team_id} 熊_超出容量,出征失败")
            return False

        detail = context.run_recognition("熊_在集结列表", img)
        if detail is not None and detail.hit:
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
