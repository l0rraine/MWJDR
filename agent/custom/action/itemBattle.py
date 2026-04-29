from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JOCR
import json
import random
import time
import re
import math

from utils import logger
from utils import timelib
from utils.mfa_config import disable_battle_tasks
from .combat import CombatRepetitionCount

@AgentServer.custom_action("识别体力")
class RecoVigor(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        cost = int(param.get("体力消耗"))
        detail = None
        while detail is None or not detail.hit:
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition_direct(
                JRecognitionType.OCR,
                JOCR(expected=["\\d+"], roi=[583, 21, 87, 36]),
                img,
            )
            time.sleep(1)
        left = int(detail.best_result.text)
        logger.debug(f"识别剩余体力：{left}")        
        if left < cost:
            logger.info(f"体力耗尽，停止出征")
            disable_battle_tasks("集结物品_识别体力入口")
            return CustomAction.RunResult(success=False)
        CombatRepetitionCount.reset()
        CombatRepetitionCount.setLimit(math.floor(left/cost))
        logger.debug(f"当前剩余体力：{left}，剩余次数：{CombatRepetitionCount.limit}")
        return CustomAction.RunResult(success=True)
    
    
@AgentServer.custom_action("物品集结")
class ItemCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        img = context.tasker.controller.post_screencap().wait().get()
        _, minutes, seconds = timelib.get_time_from_ocr(context,"识别集结时间",200)                
        return_time = minutes * 60 + seconds
        logger.debug(f"返回时间：{return_time}")
        
        
        # 开始出征
        context.run_task("点击出征")
        time.sleep(0.5)
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("体力不足", img)
        if detail.hit:
            logger.debug(f"体力不足，尝试领取免费体力：{detail.best_result.text}")
            detail = context.run_recognition("是否有免费体力",img)
            if detail.hit:
                logger.debug("领取免费体力")
                context.run_task("免费体力")
                return CustomAction.RunResult(success=True)
            else:
                #logger.debug("无免费体力") 
                logger.info(f"体力耗尽，共使用物品集结 {CombatRepetitionCount.count}次，停止出征")  
                disable_battle_tasks("集结物品_识别体力入口")
                return CustomAction.RunResult(success=False)
        
        CombatRepetitionCount.addCount()
        logger.info(f"已出征 {CombatRepetitionCount.count} 次")
        # 80s后查看集结状态
        march_start_time = time.time()
        time.sleep(80)
        context.run_task("转到城外")
        
        detail = None
        while detail is None or not detail.hit:
            if time.time() - march_start_time >= 301:
                logger.info("已超过5分01秒未识别到行军，认为行军已经开始")
                break
            time.sleep(1)
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("自动集结_行军中",img)
        logger.debug(f"已识别到行军")
        time.sleep(return_time*2 + 0.5)
        
        if CombatRepetitionCount.count>=CombatRepetitionCount.limit:
            logger.info(f"体力耗尽，共使用物品集结 {CombatRepetitionCount.count}次，停止出征")
            disable_battle_tasks("集结物品_识别体力入口")
            return CustomAction.RunResult(success=False)
        
        return CustomAction.RunResult(success=True)
