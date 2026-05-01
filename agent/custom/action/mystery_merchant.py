"""
神秘商店 Custom Action

包含：每日检查、购买

购买逻辑：
- 每个槽位：先检查免费，再检查50%折扣（找50%→取色→识别物品→购买）
- 屏幕1（5个槽位）→ 上滑 → 屏幕2（3个槽位）
- 买完一轮后尝试刷新：免费刷新 → 钻石刷新
- 徽章不足时禁用该物品50%购买
- 无法购买且无法刷新时结束
"""

import json
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, get_timestamp
from utils.click_util import click_rect
from utils.merchant_utils import add_offset, save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID

ITEM_NAMES = ["当季专武", "宠物自选箱", "高级野性标记", "行军加速", "橙碎"]
SHOP_DIR = "神秘商店"

# 槽位 ROI
SCREEN1_SLOTS = [
    [240, 419, 241, 286],
    [480, 419, 220, 280],
    [14, 708, 227, 281],
    [242, 708, 234, 285],
    [477, 709, 229, 280],
]
SCREEN2_SLOTS = [
    [14, 909, 231, 280],
    [245, 909, 228, 279],
    [472, 914, 235, 272],
]

# 从50%折扣box计算的offset
ITEM_FROM_50 = [51, 42, 57, 72]
COLOR_FROM_50 = [36, 171, -37, -31]
BUY_FROM_50 = [57, 212, 53, -16]


def _screencap(context: Context):
    return context.tasker.controller.post_screencap().wait().get()


@AgentServer.custom_action("神秘商店_每日检查")
class MysteryMerchantDailyCheck(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        account_id = RecordID.current_account_id()
        data = load_data()
        timestamp = get_timestamp(data, SHOPPING_CATEGORY, account_id, "神秘商店")

        if timelib.is_today(timestamp):
            logger.info(f"神秘商店今日已购买，跳过 (timestamp={timestamp})")
            context.override_pipeline({"神秘商店_开关": {"enabled": False}})
            context.tasker.resource.override_pipeline({"神秘商店_开关": {"enabled": False}})
            context.override_next("神秘商店_每日检查", ["商店购买_入口"])
            return CustomAction.RunResult(success=True)

        logger.info("神秘商店今日未购买，开始购买")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("神秘商店_购买")
class MysteryMerchantPurchase(CustomAction):

    _disabled_50: set = set()
    _enabled_names: list = []
    _diamond_used: int = 0

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        diamond_limit = int(param.get("钻石刷新次数", 0))

        # 截取专武模板
        img = _screencap(context)
        weapon_img = img[490:542, 85:174]
        context.override_image(f"{SHOP_DIR}/当季专武.png", weapon_img)
        logger.debug("已截取专武模板图片")

        # 初始化启用的选项
        MysteryMerchantPurchase._enabled_names = []
        for name in ITEM_NAMES:
            node_data = context.get_node_data(f"神秘商店_参数_{name}")
            if node_data and node_data.get("enabled", True):
                MysteryMerchantPurchase._enabled_names.append(name)

        if not self._enabled_names:
            logger.info("神秘商店无启用选项，仅购买免费物品")
        else:
            logger.debug(f"神秘商店启用选项: {self._enabled_names}")

        # 购买循环
        while True:
            context.run_task("神秘商店_下滑")
            self._search_slots(context, SCREEN1_SLOTS)

            context.run_task("神秘商店_上滑")
            self._search_slots(context, SCREEN2_SLOTS)

            # 尝试刷新
            if self._try_free_refresh(context):
                continue
            if self._try_diamond_refresh(context, diamond_limit):
                continue
            break

        # 结束
        logger.info("神秘商店购买完成，记录日期")
        save_merchant_date("神秘商店")
        MysteryMerchantPurchase._disabled_50.clear()
        MysteryMerchantPurchase._diamond_used = 0
        context.override_pipeline({"神秘商店_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"神秘商店_开关": {"enabled": False}})

        return CustomAction.RunResult(success=True)

    def _search_slots(self, context: Context, slots: list):
        for slot_roi in slots:
            self._try_buy_slot(context, slot_roi)

    def _try_buy_slot(self, context: Context, slot_roi: list):
        # 检查免费
        free_detail = context.run_recognition(
            "神秘商店_免费", _screencap(context),
            pipeline_override={"神秘商店_免费": {"roi": slot_roi}},
        )
        if free_detail and free_detail.hit:
            click_rect(context, free_detail.box)
            logger.info("发现免费物品，购买")
            time.sleep(1.0)
            self._handle_confirm(context, "免费物品")
            return

        # 检查50%折扣
        discount_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=[f"{SHOP_DIR}/50%.png"], roi=slot_roi),
            _screencap(context),
        )
        if not discount_detail or not discount_detail.hit:
            return

        box = discount_detail.box
        box_rect = [box.x, box.y, box.w, box.h] if not isinstance(box, list) else box

        # 取色检查徽章
        color_roi = add_offset(box_rect, COLOR_FROM_50)
        color_detail = context.run_recognition(
            "神秘商店_徽章", _screencap(context),
            pipeline_override={"神秘商店_徽章": {"roi": color_roi}},
        )
        if not color_detail or not color_detail.hit:
            logger.debug("50%标签取色不匹配，跳过")
            return

        # 识别物品
        item_roi = add_offset(box_rect, ITEM_FROM_50)
        identify_img = _screencap(context)
        name = None
        for n in self._enabled_names:
            if n in self._disabled_50:
                continue
            d = context.run_recognition_direct(
                JRecognitionType.TemplateMatch,
                JTemplateMatch(template=[f"{SHOP_DIR}/{n}.png"], roi=item_roi),
                identify_img,
            )
            if d and d.hit:
                name = n
                break

        if not name:
            return

        # 点击购买
        buy_roi = add_offset(box_rect, BUY_FROM_50)
        click_rect(context, buy_roi)
        logger.info(f"50%折扣发现{name}，点击购买")
        time.sleep(1.0)
        self._handle_confirm(context, name)

    def _handle_confirm(self, context: Context, name: str):
        """处理购买确认对话框"""
        confirm_detail = context.run_recognition("神秘商店_确定购买", _screencap(context))
        if confirm_detail and confirm_detail.hit:
            context.run_task("神秘商店_确定购买")
            badge_detail = context.run_recognition("神秘商店_获取更多", _screencap(context))
            if badge_detail and badge_detail.hit:
                context.run_task("神秘商店_关闭提示")
                self._disabled_50.add(name)
                logger.warning(f"徽章不足，禁用{name}的50%购买")
            else:
                logger.info(f"50%购买{name}成功")
        else:
            logger.debug("未出现确定购买对话框")

    def _try_free_refresh(self, context: Context) -> bool:
        detail = context.run_recognition("神秘商店_免费刷新", _screencap(context))
        if detail and detail.hit:
            click_rect(context, detail.box)
            logger.info("神秘商店免费刷新")
            time.sleep(1.5)
            return True
        return False

    def _try_diamond_refresh(self, context: Context, diamond_limit: int) -> bool:
        if diamond_limit <= 0 or self._diamond_used >= diamond_limit:
            return False

        detail = context.run_recognition("神秘商店_钻石刷新", _screencap(context))
        if detail and detail.hit:
            click_rect(context, detail.box)
            time.sleep(1.0)

            # 钻石购买确认
            confirm_detail = context.run_recognition("神秘商店_钻石购买", _screencap(context))
            if confirm_detail and confirm_detail.hit:
                click_rect(context, confirm_detail.box)
                time.sleep(1.0)

            self._diamond_used += 1
            logger.info(f"神秘商店钻石刷新第{self._diamond_used}次，共{diamond_limit}次")
            return True

        return False
