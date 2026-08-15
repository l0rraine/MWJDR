from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType
import json
import time
from typing import Union, Optional

from utils import logger
from utils.click_util import click_rect

# 队伍 ROI，与 bear.py / join.py / combat.py 中 ChangeTeam 一致
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

# 当前使用的队伍编号
GARRISON_TEAM = 1


@AgentServer.custom_action("王城驻防_设置间隔")
class GarrisonSetInterval(CustomAction):
    """将用户输入的检查间隔(秒)转为毫秒，override 到 王城驻防_等待.pre_delay。

    王城驻防_等待 用 pre_delay + DoNothing(框架管理延迟，不阻塞 Python 层)。
    本 action 瞬间完成(不 sleep)，仅做单位转换与 override。
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        try:
            param = json.loads(argv.custom_action_param)
            interval = int(param.get("interval", "60"))
        except Exception:
            interval = 60
        # 秒转毫秒，override 王城驻防_等待.pre_delay
        context.override_pipeline({"王城驻防_等待": {"pre_delay": interval * 1000}})
        return CustomAction.RunResult(success=True)


@AgentServer.custom_recognition("王城驻防_检测")
class GarrisonDetect(CustomRecognition):
    """检测是否有空闲队列且存在驻防按钮。

    1. 读 QueueStatus 缓存判断队列是否已满
    2. 模板匹配 驻防.png (roi [7,230,56,373])
    3. 命中则返回 box，框架 Click 后 post_delay 500 进入驻防界面
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        global GARRISON_TEAM

        # 1. 读取队伍编号
        try:
            param = json.loads(argv.custom_recognition_param)
            GARRISON_TEAM = int(param.get("team", "1"))
        except Exception:
            GARRISON_TEAM = 1

        # 2. 队列判断：直接读 QueueStatus 缓存
        from utils.queue_status import QueueStatus

        if QueueStatus.is_full():
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        # 3. 模板匹配驻防按钮
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition(
            "王城驻防_识别按钮",
            img,
            pipeline_override={
                "王城驻防_识别按钮": {
                    "recognition": "TemplateMatch",
                    "template": "驻防.png",
                    "roi": [7, 230, 56, 373],
                    "threshold": 0.8,
                }
            },
        )
        if not detail or not detail.hit:
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        return CustomRecognition.AnalyzeResult(box=detail.box, detail={})


@AgentServer.custom_action("王城驻防_选队出征")
class GarrisonDeploy(CustomAction):
    """选择队伍并点击出征。

    GARRISON_TEAM=0 表示默认队伍，不切换。与 join.py 选队逻辑一致。
    """

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global GARRISON_TEAM
        try:
            param = json.loads(argv.custom_action_param)
            GARRISON_TEAM = int(param.get("team", "1"))
        except Exception:
            GARRISON_TEAM = 1

        # 选队
        if GARRISON_TEAM > 0 and GARRISON_TEAM < len(TEAM_ROI):
            context.run_action(
                "王城驻防_选择队伍",
                pipeline_override={
                    "王城驻防_选择队伍": {"target": TEAM_ROI[GARRISON_TEAM]}
                },
            )
        # 点击出征
        context.run_action("王城驻防_点击出征")
        logger.info(f"王城驻防：已派遣，队伍={GARRISON_TEAM}")
        return CustomAction.RunResult(success=True)
