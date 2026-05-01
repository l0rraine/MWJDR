"""
联盟商店 Custom Action

包含：每日检查、购买

购买逻辑：
- 统帅经验：直接匹配模板购买（仅检查联盟币）
- 折扣物品：先匹配75%折扣标签，反算物品位置后识别种类，检查联盟币后购买
- 联盟币不足时禁用该物品，后续不再购买
- 一轮扫描后向上滚动一次，再扫描一轮
"""

import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, get_timestamp
from utils.click_util import click_rect
from utils.merchant_utils import save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID

TZ_NAME = "统帅经验"
TZ_TEMPLATE = "联盟商店/统帅经验.png"

# 折扣物品: (选项名, 模板路径)
DISCOUNT_ITEMS = [
    ("研究加速", "联盟商店/研究加速.png"),
    ("训练加速", "联盟商店/训练加速.png"),
    ("建筑加速", "联盟商店/建筑加速.png"),
    ("治疗加速", "联盟商店/治疗加速.png"),
]

ALL_ITEM_NAMES = [TZ_NAME] + [n for n, _ in DISCOUNT_ITEMS]

# 识别范围
SCAN_ROI = [11, 184, 698, 1001]
SCROLL_SCAN_ROI = [9, 903, 697, 296]

# 相对选项box的offset
DISCOUNT_OFFSET = [-69, -94, -13, 21]
COIN_OFFSET = [-37, 104, -85, -53]

# 从75%折扣box反算物品box: item = discount + ITEM_FROM_DISCOUNT
ITEM_FROM_DISCOUNT = [-o for o in DISCOUNT_OFFSET]
# 从75%折扣box计算联盟币区域: coin = discount + COIN_FROM_DISCOUNT
COIN_FROM_DISCOUNT = [a + b for a, b in zip(ITEM_FROM_DISCOUNT, COIN_OFFSET)]


def _add_offset(box_rect: list, offset: list) -> list:
    result = [a + b for a, b in zip(box_rect, offset)]
    result[2] = max(1, result[2])
    result[3] = max(1, result[3])
    return result


def _screencap(context: Context):
    return context.tasker.controller.post_screencap().wait().get()


@AgentServer.custom_action("联盟商店_每日检查")
class UnionShopDailyCheck(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        account_id = RecordID.current_account_id()
        data = load_data()
        timestamp = get_timestamp(data, SHOPPING_CATEGORY, account_id, "联盟商店")

        if timelib.is_today(timestamp):
            logger.info(f"联盟商店今日已购买，跳过 (timestamp={timestamp})")
            context.override_pipeline({"联盟商店_开关": {"enabled": False}})
            context.tasker.resource.override_pipeline({"联盟商店_开关": {"enabled": False}})
            context.override_next("联盟商店_每日检查", ["商店购买_入口"])
            return CustomAction.RunResult(success=True)

        logger.info("联盟商店今日未购买，开始购买")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("联盟商店_购买")
class UnionShopPurchase(CustomAction):

    _disabled_labels: set = set()

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        enabled_names = []
        for name in ALL_ITEM_NAMES:
            node_data = context.get_node_data(f"联盟商店_参数_{name}")
            if node_data and node_data.get("enabled", True):
                enabled_names.append(name)

        if not enabled_names:
            logger.info("联盟商店无启用选项，跳过")
        else:
            logger.debug(f"联盟商店启用选项: {enabled_names}")

        self._scan_and_buy(context, SCAN_ROI, enabled_names)
        context.run_task("联盟商店_滚动")
        self._scan_and_buy(context, SCROLL_SCAN_ROI, enabled_names)

        logger.info("联盟商店购买完成，记录日期")
        save_merchant_date("联盟商店")
        UnionShopPurchase._disabled_labels.clear()
        context.override_pipeline({"联盟商店_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"联盟商店_开关": {"enabled": False}})

        return CustomAction.RunResult(success=True)

    def _scan_and_buy(self, context: Context, roi: list, enabled_names: list):
        # 统帅经验：直接匹配购买
        if TZ_NAME in enabled_names and TZ_NAME not in self._disabled_labels:
            detail = context.run_recognition_direct(
                JRecognitionType.TemplateMatch,
                JTemplateMatch(template=[TZ_TEMPLATE], roi=roi, threshold=[0.9]),
                _screencap(context),
            )
            if detail and detail.hit:
                for match in detail.filtered_results:
                    box = match.box
                    box_rect = [box.x, box.y, box.w, box.h] if not isinstance(box, list) else box
                    coin_roi = _add_offset(box_rect, COIN_OFFSET)
                    coin_detail = context.run_recognition(
                        "联盟商店_联盟币", _screencap(context),
                        pipeline_override={"联盟商店_联盟币": {"roi": coin_roi}},
                    )
                    if not coin_detail or not coin_detail.hit:
                        continue
                    click_rect(context, coin_roi)
                    logger.info("点击联盟币购买 统帅经验")
                    time.sleep(1.0)
                    self._handle_confirm(context, TZ_NAME)
                    if TZ_NAME in self._disabled_labels:
                        break

        # 折扣物品：先找75%，再识别物品
        discount_enabled = [n for n, _ in DISCOUNT_ITEMS if n in enabled_names]
        if not discount_enabled:
            return

        detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["联盟商店/75%.png"], roi=roi, threshold=[0.9]),
            _screencap(context),
        )
        if not detail or not detail.hit:
            return

        matches = detail.filtered_results
        logger.debug(f"联盟商店识别到 {len(matches)} 个75%折扣标签")

        for match in matches:
            box = match.box
            discount_box = [box.x, box.y, box.w, box.h] if not isinstance(box, list) else box

            # 从75%反算物品区域和联盟币区域
            item_roi = _add_offset(discount_box, ITEM_FROM_DISCOUNT)
            coin_roi = _add_offset(discount_box, COIN_FROM_DISCOUNT)

            # 识别物品：在反算的物品区域内逐个匹配折扣模板
            identify_img = _screencap(context)
            name = None
            for item_name, template_path in DISCOUNT_ITEMS:
                if item_name not in enabled_names or item_name in self._disabled_labels:
                    continue
                d = context.run_recognition_direct(
                    JRecognitionType.TemplateMatch,
                    JTemplateMatch(template=[template_path], roi=item_roi, threshold=[0.9]),
                    identify_img,
                )
                if d and d.hit:
                    name = item_name
                    break

            if not name:
                continue

            # 检查联盟币
            coin_detail = context.run_recognition(
                "联盟商店_联盟币", _screencap(context),
                pipeline_override={"联盟商店_联盟币": {"roi": coin_roi}},
            )
            if not coin_detail or not coin_detail.hit:
                logger.debug("联盟币取色不匹配，跳过")
                continue

            click_rect(context, coin_roi)
            logger.info(f"点击联盟币购买 {name}")
            time.sleep(1.0)
            self._handle_confirm(context, name)
            if name in self._disabled_labels:
                break

    def _handle_confirm(self, context: Context, name: str):
        """处理购买确认对话框"""
        confirm_detail = context.run_recognition("联盟商店_确定购买", _screencap(context))
        if confirm_detail and confirm_detail.hit:
            context.run_task("联盟商店_确定购买")
            badge_detail = context.run_recognition("联盟商店_获取更多", _screencap(context))
            if badge_detail and badge_detail.hit:
                for _ in range(3):
                    context.run_task("联盟商店_关闭提示")
                self._disabled_labels.add(name)
                logger.warning(f"联盟币不足，禁用 {name} 的购买")
            else:
                logger.info(f"购买 {name} 成功")
        else:
            logger.debug("未出现确定购买对话框")
