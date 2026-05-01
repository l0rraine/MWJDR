"""
联盟商店 Custom Action

包含：每日检查、购买

购买逻辑：
- 统帅经验：直接匹配模板购买（仅检查联盟币）
- 折扣物品：先匹配75%折扣标签，反算物品位置后识别种类，检查联盟币后购买
- 联盟币不足时禁用该物品，后续不再购买
- 一轮扫描后向上滚动一次，再扫描一轮

选项列表从 pipeline JSON 的"联盟商店_选项"节点 next 读取，
物品名=选项名=图片名，模板路径为 {SHOP_DIR}/{name}.png。
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
from utils.merchant_utils import add_offset, save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID

SHOP_DIR = "联盟商店"
TZ_ITEM = "统帅经验"

# 识别范围: [第一轮, 滚动后]
SCAN_ROIS = [[11, 184, 698, 1001], [9, 903, 697, 296]]

# 从75%折扣box计算物品区域: item = discount + ITEM_FROM_DISCOUNT
ITEM_FROM_DISCOUNT = [33, 30, 82, 92]
# 从75%折扣box计算联盟币区域: coin = discount + COIN_FROM_DISCOUNT
COIN_FROM_DISCOUNT = [22, 162, -47, -32]
# 从物品box计算联盟币区域: coin = item + COIN_FROM_ITEM
COIN_FROM_ITEM = [COIN_FROM_DISCOUNT[i] - ITEM_FROM_DISCOUNT[i] for i in range(4)]

# 参数节点前缀
_PARAM_PREFIX = "联盟商店_参数_"


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
    _enabled_names: list = []

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 从JSON读取选项列表
        all_params = context.get_node_data("联盟商店_选项")["next"]
        UnionShopPurchase._enabled_names = []
        for item in all_params:
            param_name = item["name"] if isinstance(item, dict) else item
            node_data = context.get_node_data(param_name)
            if node_data and node_data.get("enabled", True):
                name = param_name.removeprefix(_PARAM_PREFIX)
                UnionShopPurchase._enabled_names.append(name)

        if not self._enabled_names:
            logger.info("联盟商店无启用选项，跳过")
        else:
            logger.debug(f"联盟商店启用选项: {self._enabled_names}")

        for roi in SCAN_ROIS:
            self._buy_tz(context, roi)
            self._buy_discount(context, roi)
            context.run_task("联盟商店_滚动")

        logger.info("联盟商店购买完成，记录日期")
        save_merchant_date("联盟商店")
        UnionShopPurchase._disabled_labels.clear()
        context.override_pipeline({"联盟商店_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"联盟商店_开关": {"enabled": False}})

        return CustomAction.RunResult(success=True)

    def _buy_tz(self, context: Context, roi: list):
        """统帅经验：直接匹配模板购买"""
        if TZ_ITEM not in self._enabled_names or TZ_ITEM in self._disabled_labels:
            return

        detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=[f"{SHOP_DIR}/{TZ_ITEM}.png"], roi=roi),
            _screencap(context),
        )
        if not detail or not detail.hit:
            return

        for match in detail.filtered_results:
            coin_roi = add_offset(match.box, COIN_FROM_ITEM)
            coin_detail = context.run_recognition(
                "联盟商店_联盟币", _screencap(context),
                pipeline_override={"联盟商店_联盟币": {"roi": coin_roi}},
            )
            if not coin_detail or not coin_detail.hit:
                continue
            click_rect(context, coin_roi)
            logger.info(f"点击联盟币购买 {TZ_ITEM}")
            time.sleep(1.0)
            self._handle_confirm(context, TZ_ITEM)
            if TZ_ITEM in self._disabled_labels:
                break

    def _buy_discount(self, context: Context, roi: list):
        """折扣物品：先找75%，再识别物品，检查联盟币后购买"""
        discount_enabled = [n for n in self._enabled_names if n != TZ_ITEM]
        if not discount_enabled:
            return

        detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=[f"{SHOP_DIR}/75%.png"], roi=roi),
            _screencap(context),
        )
        if not detail or not detail.hit:
            return

        matches = detail.filtered_results
        logger.debug(f"联盟商店识别到 {len(matches)} 个75%折扣标签")

        for match in matches:
            item_roi = add_offset(match.box, ITEM_FROM_DISCOUNT)
            coin_roi = add_offset(match.box, COIN_FROM_DISCOUNT)

            # 识别物品：在反算的物品区域内逐个匹配折扣模板
            identify_img = _screencap(context)
            name = None
            for n in discount_enabled:
                if n in self._disabled_labels:
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
