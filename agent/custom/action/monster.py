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





@AgentServer.custom_action("设置怪兽次数")
class SetMonsterCount(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        detail = None
        while detail is None or not detail.hit:            
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("自动集结_识别次数", img)
            time.sleep(1)
        count = int(detail.best_result.text)
        CombatRepetitionCount.setCount(10-count)
        logger.debug(f"已识别当前怪兽次数：{count}")
        context.override_pipeline(
            {
                "自动集结_查看次数":{
                    "enabled": False
                }
            }
        )
        context.run_task("后退")
        time.sleep(0.5)
        # debug
        # count=0
        if count == 0:
            # 吉娜模式下，执行出征怪兽次数够10次则直接打吉娜
            logger.info(f"已达到出征次数上限：10 次，开始打吉娜")
            CombatRepetitionCount.reset()
            context.run_task("自动集结_吉娜_识别体力入口")
                
        else:
            context.run_task("自动集结_巨兽入口")
        
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("开始出征")
class BeginCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        logger.debug(f"出征参数：{param}")        

        repeat_limit = int(param.get("出征次数"))
        jina = int(param.get("吉娜"))
        can_limit = int(param.get("罐头数量"))
        
        #debug
        # repeat_limit=7
        # CombatRepetitionCount.setCount(7)
        # CombatRepetitionCount.init(7)
        
        if repeat_limit != 0: 
            CombatRepetitionCount.init(repeat_limit)
            logger.debug(f"出征次数上限：{repeat_limit}次")
        
        if jina == 1:
            logger.debug("吉娜模式")
        
        if can_limit != 0:
            CombatRepetitionCount.init(can_limit)
            logger.debug(f"罐头使用上限：{can_limit}次")
        
        
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
                context.run_task("点击出征")
            elif can_limit != 0:        
                logger.debug("无免费体力，尝试使用罐头")
                context.run_task("使用罐头")
                CombatRepetitionCount.addCount(2)
                logger.info(f"已使用罐头 {CombatRepetitionCount.count} 次")
                context.run_task("点击出征")
                
            else:
                logger.debug("无免费体力，结束")
                context.run_task("转到城外")
                return CustomAction.RunResult(success=True)

        if repeat_limit != 0:
            CombatRepetitionCount.addCount()
            logger.info(f"已出征 {CombatRepetitionCount.count} 次")
        
        # 80s后查看集结状态
        time.sleep(80)
        context.run_task("转到城外")
        detail = None
        while detail is None or not detail.hit:
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("自动集结_集结中", img)
            time.sleep(1)
        logger.debug("已识别到集结中标识")
        context.tasker.controller.post_click(
            6 + detail.box.x + 195, detail.box.y
            
        ).wait()
        
        detail = None
        while detail is None or not detail.hit:
            time.sleep(1)
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("自动集结_行军中",img)
        logger.debug(f"已识别到行军：{detail.best_result.text}")
        context.run_task("后退")
        time.sleep(return_time*2 + 0.5)
        
        
        # 判断作战次数是否达到上限
        if repeat_limit > 0 and repeat_limit <= CombatRepetitionCount.count:             
            # 当前出征次数已达到限制次数
            # 当前为吉娜模式
            # 则重新查看出征次数
            if jina == 1:
                logger.info("已到达次数上限，重新查看次数")
                # 重新查看次数
                context.override_pipeline(
                    {
                        "自动集结_查看次数":{
                            "enabled": True
                        }
                    }
                )
                context.run_task("后退")
                time.sleep(0.5)
                context.run_task("自动集结_点击怪兽")
                time.sleep(0.5)
                CombatRepetitionCount.reset()
                context.run_task("自动集结_查看次数")
            else:
                logger.info(f"已达到出征次数上限：{repeat_limit} 次，停止出征")
            
            return CustomAction.RunResult(success=True)
            
        # 判断罐头次数是否达到上限
        if can_limit > 0 and can_limit <= CombatRepetitionCount.count:
            logger.info(f"已达到罐头使用次数上限：{can_limit}次，停止出征")
            return CustomAction.RunResult(success=True)    
        
        
        
        context.run_task("自动集结_巨兽入口")
        return CustomAction.RunResult(success=True)
