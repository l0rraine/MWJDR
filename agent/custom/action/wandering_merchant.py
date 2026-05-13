"""
游荡商人 Custom Action

包含：每日检查、钻石刷新、记录日期
"""

import json
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JOCR, JTemplateMatch

from utils import logger
from utils.click_util import click_rect
from utils.merchant_utils import add_offset, save_task_date, disable_switch, daily_check


@AgentServer.custom_action("游荡商人_每日检查")
class MerchantDailyCheck(CustomAction):
    """检查游荡商人今天是否已购买，已购买则跳过"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        done = daily_check(context, "游荡商人", "游荡商人_开关",
                           "游荡商人_每日检查", "商店购买_入口")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("游荡商人_钻石刷新")
class MerchantDiamondRefresh(CustomAction):
    """
    游荡商人刷新控制逻辑

    流程：
    1. 先尝试免费刷新，如果有免费刷新则点击并继续购买
    2. 没有免费刷新时，检查钻石刷新次数参数
       - 钻石刷新次数 = 0：保存日期，结束
       - 钻石刷新次数 > 0：执行钻石刷新，计数，到达上限后保存日期，结束

    找到刷新时 return True → pipeline next → 游荡商人_开始购买（继续购买循环）。
    无更多刷新时 override_next + return True → pipeline next → 商店购买_入口（回到商店入口）。
    """

    # 类变量：记录当前已使用钻石刷新次数
    _diamond_used: int = 0

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        diamond_limit = int(param.get("钻石刷新次数", 0))

        # 第一步：尝试免费刷新
        img = context.tasker.controller.post_screencap().wait().get()
        free_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["流浪商人/免费刷新.png"], roi=[511, 213, 171, 96]),
            img,
        )

        if free_detail and free_detail.hit:
            logger.info("发现免费刷新，点击刷新")
            click_rect(context, free_detail.box)
            time.sleep(1.5)
            return CustomAction.RunResult(success=True)

        # 第二步：没有免费刷新了
        if diamond_limit == 0:
            logger.info("免费刷新已用完，不使用钻石刷新，记录日期")
            self._end(context)
            context.override_next("游荡商人_刷新控制", ["商店购买_入口"])
            return CustomAction.RunResult(success=True)

        # 第三步：执行钻石刷新
        if self._diamond_used < diamond_limit:
            img = context.tasker.controller.post_screencap().wait().get()
            diamond_detail = context.run_recognition_direct(
                JRecognitionType.TemplateMatch,
                JTemplateMatch(template=["流浪商人/钻石刷新.png"], roi=[523, 229, 137, 68]),
                img,
            )

            if diamond_detail and diamond_detail.hit:
                click_rect(context, diamond_detail.box)
                time.sleep(1.0)

                # 处理确认对话框
                img = context.tasker.controller.post_screencap().wait().get()
                confirm_detail = context.run_recognition_direct(
                    JRecognitionType.OCR,
                    JOCR(expected=["提示"], roi=[308, 416, 96, 60]),
                    img,
                )
                logger.debug(f"钻石刷新确认对话框识别结果：{confirm_detail.best_result.text if confirm_detail and confirm_detail.hit else '未识别到提示'}")
                if confirm_detail and confirm_detail.hit:
                    click_rect(context, [465, 768, 100, 44])
                    time.sleep(1.0)

                MerchantDiamondRefresh._diamond_used += 1
                logger.info(f"钻石刷新第{MerchantDiamondRefresh._diamond_used}次")
                return CustomAction.RunResult(success=True)

        # 第四步：钻石刷新次数已达上限
        logger.info(f"钻石刷新次数已达上限（{diamond_limit}次），记录日期")
        self._end(context)
        context.override_next("游荡商人_刷新控制", ["商店购买_入口"])
        return CustomAction.RunResult(success=True)

    def _end(self, context: Context):
        save_task_date("游荡商人")
        MerchantDiamondRefresh._diamond_used = 0
        disable_switch(context, "游荡商人_开关")


@AgentServer.custom_action("游荡商人_记录日期")
class MerchantRecordDate(CustomAction):
    """记录游荡商人购买日期"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        save_task_date("游荡商人")
        return CustomAction.RunResult(success=True)
