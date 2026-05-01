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
from utils.ocr_util import ocr_until_consistent_by_task
from utils.click_util import click_rect
from utils.mfa_config import disable_battle_tasks

from .combat import CombatRepetitionCount


@AgentServer.custom_action("设置怪兽次数")
class SetMonsterCount(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        text = ocr_until_consistent_by_task(context, "自动集结_识别次数", expected_pattern=r'^\d+$')
        if text is None:
            logger.warning("识别怪兽次数失败")
            return CustomAction.RunResult(success=False)
        remaining = int(text)
        CombatRepetitionCount.reset()

        if remaining <= 0:
            logger.info(f"已达到出征次数上限：10 次，停止出征")
            context.run_task("后退")
            time.sleep(0.5)
            click_rect(context, [628, 727, 15, 18])
            return CustomAction.RunResult(success=False)

        CombatRepetitionCount.init(remaining)
        logger.info(
            f"已识别当前怪兽还剩余{remaining}次"
        )
        context.override_pipeline(
            {
                "自动集结_查看次数":{
                    "enabled": False
                }
            }
        )
        context.run_task("后退")
        time.sleep(0.5)

        if CombatRepetitionCount.isReachLimit():
            click_rect([628, 727, 15, 18])

        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("开始出征")
class BeginCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        # logger.debug(f"出征参数：{param}")

        repeat_limit = int(param.get("出征次数"))
        can_limit = int(param.get("罐头数量"))
        advanced_mode = int(param.get("高级模式",0))
        use_19_can = int(param.get("使用19点罐头",0))

        # debug
        # repeat_limit=7
        # CombatRepetitionCount.setCount(7)
        # CombatRepetitionCount.init(7)

        if repeat_limit != 0: 
            CombatRepetitionCount.init(repeat_limit)

        if can_limit != 0:
            CombatRepetitionCount.init(can_limit)

        _, minutes, seconds = timelib.get_time_from_ocr(context,"识别集结时间",200)                
        return_time = minutes * 60 + seconds

        logger.debug(f"返回时间：{return_time}")
        # 开始出征
        context.run_task("点击出征")

        time.sleep(0.5)
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("体力不足", img)
        # logger.debug(f"{repeat_limit > 0} {advanced_mode == 1} {not CombatRepetitionCount.isReachLimit()}")
        if detail is not None and detail.hit:
            logger.debug(f"体力不足，尝试领取免费体力：{detail.best_result.text}")
            detail = context.run_recognition("是否有免费体力",img)
            if detail is not None and detail.hit:
                # 普通模式下，根据免费罐头选项判断是否领取
                if advanced_mode == 0:
                    current_hour = time.localtime().tm_hour
                    can_use_free = False
                    if current_hour < 19:
                        # 0点~19点，无条件使用免费罐头
                        can_use_free = True
                        logger.debug("0点~19点，无条件领取免费体力")
                    else:
                        # 19点~0点，根据19点罐头选项决定
                        if use_19_can == 1:
                            can_use_free = True
                            logger.debug("19点罐头选项已启用，领取免费体力")
                        else:
                            logger.debug("19点罐头选项未启用，不领取免费体力")

                if not can_use_free:
                    logger.info("免费罐头未启用，不领取免费体力，停止出征")
                    self._end(context)
                    return CustomAction.RunResult(success=False)
                else:
                    logger.debug("领取免费体力")
                    context.run_task("免费体力")                
                    context.run_task("点击出征")
            elif can_limit != 0:        
                logger.debug("无免费体力，尝试使用罐头")
                # 判断罐头次数是否达到上限
                if can_limit > 0 and CombatRepetitionCount.isReachLimit():
                    logger.info(f"已达到罐头使用次数上限：{can_limit}次，停止出征")
                    self._end(context)
                    return CustomAction.RunResult(success=False)

                text = ocr_until_consistent_by_task(context, "识别罐头数量", expected_pattern=r'^\d+$')
                if text is None:
                    logger.warning("识别罐头数量失败")
                    return CustomAction.RunResult(success=False)
                max_can = int(text)
                if max_can<2:
                    logger.info("罐头已用完")
                    self._end(context)
                    return CustomAction.RunResult(success=False)

                c = min(20,CombatRepetitionCount.limit-CombatRepetitionCount.count,max_can)
                context.run_task("使用罐头",{
                    "使用罐头":{
                        "repeat": c
                    }
                })
                CombatRepetitionCount.addCount(c)
                logger.info(f"使用罐头 {c} 次，当前总次数为 {CombatRepetitionCount.count} 次")
                context.run_task("点击出征")
            elif repeat_limit > 0 and advanced_mode == 1 and not CombatRepetitionCount.isReachLimit():
                text = ocr_until_consistent_by_task(context, "识别罐头数量", expected_pattern=r'^\d+$')
                if text is None:
                    logger.warning("识别罐头数量失败")
                    return CustomAction.RunResult(success=False)
                max_can = int(text)
                logger.debug(f"罐头数量：{max_can}")
                if max_can<2:
                    logger.info("罐头已用完")
                    self._end(context)
                    return CustomAction.RunResult(success=False)
                c = min(20,(CombatRepetitionCount.limit-CombatRepetitionCount.count)*2,max_can)
                context.run_task("使用罐头",{
                    "使用罐头":{
                        "repeat": c
                    }
                })
                logger.info(f"使用罐头 {c} 次")
                context.run_task("点击出征")
            else:
                logger.debug("无免费体力，结束")
                self._end(context)
                return CustomAction.RunResult(success=False)

        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("自动集结_与别人队伍重复", img)
        if detail is not None and detail.hit:
            click_rect(context, detail.box)
            return CustomAction.RunResult(success=True)

        if CombatRepetitionCount.limit > 0:
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

        # 判断作战次数是否达到上限
        if CombatRepetitionCount.isReachLimit():
            if advanced_mode == 1:
                logger.info(f"已达到出征次数上限：{CombatRepetitionCount.limit}次，停止出征")
                CombatRepetitionCount.reset()
                return CustomAction.RunResult(success=False)
            else:
                logger.info("已到达次数上限，重新查看次数")
                # 重新查看次数
                context.override_pipeline({"自动集结_查看次数": {"enabled": True}})
                return CustomAction.RunResult(success=True)

        return CustomAction.RunResult(success=True)
    def _end(self, context: Context):
        disable_battle_tasks(context, "自动集结_巨兽入口")
        CombatRepetitionCount.reset()
