"""
游荡商人 Custom Action

包含：每日检查、钻石刷新、记录日期
"""

import json
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context, Rect
from maa.pipeline import JRecognitionType, JOCR, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, get_timestamp
from utils.click_util import click_rect
from utils.merchant_utils import save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID


@AgentServer.custom_action("游荡商人_每日检查")
class MerchantDailyCheck(CustomAction):
    """检查游荡商人今天是否已购买，已购买则跳过"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        account_id = RecordID.current_account_id()
        data = load_data()
        timestamp = get_timestamp(data, SHOPPING_CATEGORY, account_id, "游荡商人")

        if timelib.is_today(timestamp):
            logger.info(f"游荡商人今日已购买，跳过 (timestamp={timestamp})")
            context.override_pipeline({"游荡商人_开关": {"enabled": False}})
            return CustomAction.RunResult(success=False)

        logger.info("游荡商人今日未购买，开始购买")
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
    """

    # 类变量：记录当前已使用钻石刷新次数
    _diamond_used: int = 0

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        diamond_limit = int(param.get("钻石刷新次数", 0))

        # 第一步：尝试免费刷新
        img = context.tasker.controller.post_screencap().wait().get()
        free_detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=["免费刷新"], roi=[513, 212, 169, 98]),
            img,
        )

        if free_detail and free_detail.hit:
            # 有免费刷新，点击并回到购买流程
            logger.info("发现免费刷新，点击刷新")
            click_rect(context, free_detail.box)
            time.sleep(1.5)
            return CustomAction.RunResult(success=True)

        # 第二步：没有免费刷新了
        if diamond_limit == 0:
            # 不使用钻石刷新，保存日期，结束
            logger.info("免费刷新已用完，不使用钻石刷新，记录日期")
            self._end(context)

        # 第三步：执行钻石刷新
        if self._diamond_used < diamond_limit:
            # 尝试找到钻石刷新按钮
            img = context.tasker.controller.post_screencap().wait().get()
            diamond_detail = context.run_recognition_direct(
                JRecognitionType.TemplateMatch,
                JTemplateMatch(template=["流浪商人/钻石刷新.png"], roi=[523, 229, 137, 68]),
                img,
            )

            if diamond_detail and diamond_detail.hit:
                # 点击钻石刷新
                click_rect(context, diamond_detail.box)
                time.sleep(1.0)

                # 处理确认对话框（可能存在也可能不存在）
                img = context.tasker.controller.post_screencap().wait().get()
                confirm_detail = context.run_recognition_direct(
                    JRecognitionType.OCR,
                    JOCR(expected=["提示"], roi=[308, 416, 96, 60]),
                    img,
                )
                logger.debug(f"钻石刷新确认对话框识别结果：{confirm_detail.best_result.text if confirm_detail and confirm_detail.hit else '未识别到提示'}")
                if confirm_detail and confirm_detail.hit:
                    click_rect(context, Rect(465, 768, 100, 44))  # 点击对话框中的确认按钮
                    time.sleep(1.0)

                MerchantDiamondRefresh._diamond_used += 1
                logger.info(
                    f"钻石刷新第{MerchantDiamondRefresh._diamond_used}次"
                )
                return CustomAction.RunResult(success=True)

        # 第四步：钻石刷新次数已达上限
        logger.info(
            f"钻石刷新次数已达上限（{diamond_limit}次），记录日期"
        )
        self._end(context)
        return CustomAction.RunResult(success=False)
    def _end(self, context: Context):
        # 每次 Custom Action 结束时重置钻石使用计数
        save_merchant_date("游荡商人")
        MerchantDiamondRefresh._diamond_used = 0
        context.override_pipeline({"游荡商人_开关": {"enabled": False}})


@AgentServer.custom_action("游荡商人_记录日期")
class MerchantRecordDate(CustomAction):
    """记录游荡商人购买日期"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        save_merchant_date("游荡商人")
        return CustomAction.RunResult(success=True)
