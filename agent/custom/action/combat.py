from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time
import re
import math

from utils import logger
from utils import timelib


class CombatRepetitionCount:
    count: int = 0
    limit: int = 0
    initialized = False
    @classmethod
    def init(cls, limit=0):
        """初始化方法，确保只执行一次"""
        if not cls.initialized:
            cls.limit = limit
            cls.initialized = True
    @classmethod
    def addCount(cls, step=1):
        cls.count = cls.count + step
    @classmethod
    def setCount(cls, data):
        cls.count = data
    @classmethod
    def setLimit(cls, data):
        cls.limit = data
    @classmethod
    def reset(cls):
        cls.count = 0
        cls.limit = 0
        cls.initialized = False
    @classmethod
    def isReachLimit(cls):
        return cls.limit>0 and cls.count>=cls.limit
@AgentServer.custom_action("切换队伍")
class ChangeTeam(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        team_roi = [
            [0,0,0,0],
            [56,117,22,15],
            [127,115,26,23],
            [204,113,16,25],
            [270,113,35,26],
            [349,117,22,22],
            [416,112,23,32],
            [494,113,30,28],
            [565,113,30,29]
        ]
        json_data = json.loads(argv.custom_action_param)
        team_index = int(json_data.get('队伍序号'))
        logger.debug(f"切换队伍到：{team_index}")
        if team_index != 0:
            context.run_task("custom", {
            "custom": {
                "target": team_roi[team_index],
                "action": "Click",
            }
        })
        return CustomAction.RunResult(success=True)
@AgentServer.custom_action("撤回最后一个队伍")
class RecallTeam(CustomAction):

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        team_roi = [
            [0,0,0,0], 
            [200,552,45,45],
            [200,488,45,45],
            [200,427,45,45],
            [200,371,45,45],
            [200,313,45,45],
            [200,246,45,45]
            
        ]
        json_data = json.loads(argv.custom_action_param)
        team_index = int(json_data.get('队伍序号'))
        if team_index != 0:
            context.run_task("custom", {
            "custom": {
                "target": team_roi[team_index],
                "action": "Click",
            }
        })
        return CustomAction.RunResult(success=True)