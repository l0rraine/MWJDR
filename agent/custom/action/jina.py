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
            detail = context.run_recognition("开始识别", img,{
                "开始识别": {
                    "recognition": "OCR",
                    "expected": "\\d+",
                    "roi" : [583,21,87,36]
                }
            })
            time.sleep(1)
        left = int(detail.best_result.text)
        logger.debug(f"识别剩余体力：{left}")        
        if left < cost:
            logger.info(f"体力耗尽，停止出征")
            context.override_pipeline({
                "自动集结_吉娜_识别体力":{
                    "next":[]
                }
            })
            return CustomAction.RunResult(success=True)
        CombatRepetitionCount.setLimit(math.floor(left/cost))
        logger.debug(f"当前剩余体力：{left}，剩余次数：{CombatRepetitionCount.limit}")
        return CustomAction.RunResult(success=True)
    
    
@AgentServer.custom_action("吉娜出征")
class JinaCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        img = context.tasker.controller.post_screencap().wait().get()
        _, minutes, seconds = timelib.get_time_from_ocr(context,img,"识别集结时间")
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
                context.run_task("自动集结_吉娜_识别体力入口")
                return CustomAction.RunResult(success=True)
            else:
                #logger.debug("无免费体力") 
                logger.info(f"体力耗尽，共出征吉娜 {CombatRepetitionCount.count}次，停止出征")               
                return CustomAction.RunResult(success=True)
        
        CombatRepetitionCount.addCount()
        logger.info(f"已出征吉娜 {CombatRepetitionCount.count} 次")
        # 80s后查看集结状态
        time.sleep(80)
        context.run_task("转到城外")
        
        detail = None
        while detail is None or not detail.hit:
            time.sleep(1)
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("自动集结_行军中",img)
        logger.debug(f"已识别到行军")
        
        
        time.sleep(return_time*2 + 0.5)
        
        if CombatRepetitionCount.count>=CombatRepetitionCount.limit:
            logger.info(f"体力耗尽，共出征吉娜 {CombatRepetitionCount.count}次，停止出征")
            return CustomAction.RunResult(success=True)
        
        context.run_task("自动集结_吉娜入口")
        return CustomAction.RunResult(success=True)
