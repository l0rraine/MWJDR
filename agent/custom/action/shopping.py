"""
商店购买 Custom Action

包含：
- 游荡商人_每日检查：检查今天是否已购买，是则跳过
- 游荡商人_钻石刷新：免费刷新→钻石刷新→记录日期的核心控制逻辑
- 游荡商人_记录日期：保存购买日期
"""

import json
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JOCR, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, save_data, get_timestamp, set_timestamp
from utils.click_util import random_click_point
from ..reco.record_id import RecordID

SHOPPING_CATEGORY = "shopping"


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
            logger.info("游荡商人今日已购买，跳过")
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

            rx, ry = random_click_point(free_detail.box)
            logger.info(f"点击{rx},{ry}进行免费刷新")
            context.tasker.controller.post_click(rx, ry).wait()
            time.sleep(1.5)
            return CustomAction.RunResult(success=True)

        # 第二步：没有免费刷新了
        if diamond_limit == 0:
            # 不使用钻石刷新，保存日期，结束
            _save_merchant_date("游荡商人")
            MerchantDiamondRefresh._diamond_used = 0
            logger.info("免费刷新已用完，不使用钻石刷新，记录日期")
            return CustomAction.RunResult(success=False)

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
                rx, ry = random_click_point(diamond_detail.box)
                context.tasker.controller.post_click(rx, ry).wait()
                time.sleep(1.0)

                # 处理确认对话框（可能存在也可能不存在）
                img = context.tasker.controller.post_screencap().wait().get()
                confirm_detail = context.run_recognition_direct(
                    JRecognitionType.TemplateMatch,
                    JTemplateMatch(template=["流浪商人/钻石购买.png"], roi=[194, 701, 334, 184]),
                    img,
                )
                if confirm_detail and confirm_detail.hit:
                    rx, ry = random_click_point(confirm_detail.box)
                    context.tasker.controller.post_click(rx, ry).wait()
                    time.sleep(1.0)

                MerchantDiamondRefresh._diamond_used += 1
                logger.info(
                    f"钻石刷新第{MerchantDiamondRefresh._diamond_used}次，"
                    f"共{diamond_limit}次"
                )
                return CustomAction.RunResult(success=True)
            else:
                # 找不到钻石刷新按钮（可能钻石不够或其他原因），保存日期，结束
                logger.warning("未找到钻石刷新按钮，记录日期并结束")
                _save_merchant_date("游荡商人")
                MerchantDiamondRefresh._diamond_used = 0
                return CustomAction.RunResult(success=False)

        # 第四步：钻石刷新次数已达上限
        _save_merchant_date("游荡商人")
        logger.info(
            f"钻石刷新次数已达上限（{diamond_limit}次），记录日期"
        )
        MerchantDiamondRefresh._diamond_used = 0
        return CustomAction.RunResult(success=False)


@AgentServer.custom_action("游荡商人_记录日期")
class MerchantRecordDate(CustomAction):
    """记录游荡商人购买日期"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        _save_merchant_date("游荡商人")
        return CustomAction.RunResult(success=True)


def _save_merchant_date(merchant_name: str):
    """保存商人购买日期到数据文件"""
    account_id = RecordID.current_account_id()
    data = load_data()
    timestamp_ms = int(time.time() * 1000)
    set_timestamp(data, SHOPPING_CATEGORY, account_id, merchant_name, timestamp_ms)
    if save_data(data):
        logger.info(f"{merchant_name}购买日期已记录")
    else:
        logger.warning(f"{merchant_name}购买日期记录失败")
