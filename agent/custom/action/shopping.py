"""
商店购买 Custom Action

包含：
- 游荡商人：每日检查、钻石刷新、记录日期
- 神秘商人：每日检查、购买（含免费购买、50%折扣购买、免费刷新、钻石刷新）
"""

import json
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.define import Rect
from maa.pipeline import JRecognitionType, JOCR, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, save_data, get_timestamp, set_timestamp
from utils.click_util import click_rect
from ..reco.record_id import RecordID

SHOPPING_CATEGORY = "shopping"
MYSTERY_CATEGORY = "神秘商人"

# 神秘商人购买选项映射: (选项名, 模板图片路径)
MYSTERY_OPTIONS = [
    ("当季专武", "神秘商店/专武.png"),
    ("宠物自选箱", "神秘商店/宠物自选箱.png"),
    ("高级野性标记", "神秘商店/高级野性标记.png"),
    ("行军加速", "神秘商店/行军加速.png"),
    ("橙碎", "神秘商店/橙碎.png"),
]


# ==================== 游荡商人 ====================


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
            click_rect(context, free_detail.box)
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
                click_rect(context, diamond_detail.box)
                time.sleep(1.0)

                # 处理确认对话框（可能存在也可能不存在）
                img = context.tasker.controller.post_screencap().wait().get()
                confirm_detail = context.run_recognition_direct(
                    JRecognitionType.TemplateMatch,
                    JTemplateMatch(template=["流浪商人/钻石购买.png"], roi=[194, 701, 334, 184]),
                    img,
                )
                if confirm_detail and confirm_detail.hit:
                    click_rect(context, confirm_detail.box)
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


# ==================== 神秘商人 ====================


@AgentServer.custom_action("神秘商人_每日检查")
class MysteryMerchantDailyCheck(CustomAction):
    """检查神秘商人今天是否已购买，已购买则跳过"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        account_id = RecordID.current_account_id()
        data = load_data()
        timestamp = get_timestamp(data, SHOPPING_CATEGORY, account_id, "神秘商人")

        if timelib.is_today(timestamp):
            logger.info("神秘商人今日已购买，跳过")
            return CustomAction.RunResult(success=False)

        logger.info("神秘商人今日未购买，开始购买")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("神秘商人_购买")
class MysteryMerchantPurchase(CustomAction):
    """
    神秘商人购买逻辑

    流程：
    1. 截取专武模板图片
    2. 循环购买：
       a. 免费物品 → 必买
       b. 50%折扣物品 → 查找启用的选项，点击购买，确认，检查徽章
       c. 无可购买 → 免费刷新
       d. 无免费刷新 → 钻石刷新
       e. 无法刷新 → 记录日期，结束
    """

    # 类变量：因徽章不足被禁用的50%购买选项
    _disabled_50_options: set = set()
    # 类变量：已使用钻石刷新次数
    _diamond_used: int = 0

    # 神秘商人界面搜索区域
    SEARCH_ROI = [14, 395, 695, 805]
    # 免费刷新按钮区域
    FREE_REFRESH_ROI = [531, 297, 127, 35]
    # 钻石刷新按钮区域
    DIAMOND_REFRESH_ROI = [531, 297, 127, 35]

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        diamond_limit = int(param.get("钻石刷新次数", 0))

        # Step 0: 截取专武模板图片
        self._capture_weapon_template(context)

        # Step 1: 读取启用的选项
        enabled_options = self._get_enabled_options(context)
        if not enabled_options:
            logger.info("神秘商人无启用选项，跳过购买")
            _save_merchant_date("神秘商人")
            return CustomAction.RunResult(success=False)
        logger.info(f"神秘商人启用选项: {[name for name, _ in enabled_options]}")

        # Step 2: 购买循环
        max_iterations = 100
        for iteration in range(max_iterations):
            img = context.tasker.controller.post_screencap().wait().get()

            # 2a: 检查免费物品
            if self._try_buy_free(context, img):
                continue

            # 2b: 检查50%折扣物品
            if self._try_buy_discount(context, img, enabled_options):
                continue

            # 2c: 没有可购买物品，尝试免费刷新
            if self._try_free_refresh(context, img):
                continue

            # 2d: 没有免费刷新，尝试钻石刷新
            if self._try_diamond_refresh(context, img, diamond_limit):
                continue

            # 2e: 无法刷新，结束购买
            break

        # Step 3: 记录日期
        _save_merchant_date("神秘商人")
        MysteryMerchantPurchase._disabled_50_options.clear()
        MysteryMerchantPurchase._diamond_used = 0
        logger.info("神秘商人购买完成，记录日期")
        return CustomAction.RunResult(success=False)

    def _capture_weapon_template(self, context: Context):
        """截取界面中专武区域 [85, 490, 89, 52] 作为模板图片"""
        img = context.tasker.controller.post_screencap().wait().get()
        x, y, w, h = 85, 490, 89, 52
        weapon_img = img[y : y + h, x : x + w]
        context.override_image("神秘商店/专武.png", weapon_img)
        logger.debug("已截取专武模板图片")

    def _get_enabled_options(self, context: Context) -> list[tuple[str, str]]:
        """读取启用的购买选项"""
        enabled = []
        for name, template in MYSTERY_OPTIONS:
            node_name = f"神秘商人_参数_{name}"
            node_data = context.get_node_data(node_name)
            if node_data and node_data.get("enabled", True):
                enabled.append((name, template))
        return enabled

    def _try_buy_free(self, context: Context, img) -> bool:
        """尝试购买免费物品，发现免费标签则点击购买"""
        free_detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=["免费"], roi=self.SEARCH_ROI),
            img,
        )
        if free_detail and free_detail.hit:
            click_rect(context, free_detail.box)
            logger.info("发现免费物品，购买")
            time.sleep(1.0)
            return True
        return False

    def _try_buy_discount(
        self, context: Context, img, enabled_options: list[tuple[str, str]]
    ) -> bool:
        """尝试购买50%折扣物品"""
        discount_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["神秘商店/50%.png"], roi=self.SEARCH_ROI),
            img,
        )
        if not discount_detail or not discount_detail.hit:
            return False

        box = discount_detail.box
        # 物品搜索区域: 50%匹配位置的偏移 [51, 42, 57, 72]
        item_roi = [box.x + 51, box.y + 42, 57, 72]

        # 逐个检查启用的选项（排除因徽章不足被禁用的）
        for opt_name, template_path in enabled_options:
            if opt_name in self._disabled_50_options:
                continue

            item_detail = context.run_recognition_direct(
                JRecognitionType.TemplateMatch,
                JTemplateMatch(template=[template_path], roi=item_roi),
                img,
            )
            if not item_detail or not item_detail.hit:
                continue

            # 找到匹配物品，点击购买区域（偏移 [57, 212, 53, -16]）
            purchase_rect = Rect(
                box.x + 57,
                box.y + 212,
                max(1, box.w + 53),
                max(1, box.h - 16),
            )
            click_rect(context, purchase_rect)
            logger.info(f"50%折扣发现{opt_name}，点击购买")
            time.sleep(1.0)

            # 处理确定购买对话框
            self._handle_purchase_confirm(context, opt_name)
            return True

        return False

    def _handle_purchase_confirm(self, context: Context, opt_name: str):
        """处理购买确认对话框，检查徽章是否充足"""
        img = context.tasker.controller.post_screencap().wait().get()
        confirm_detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=["确定购买"], roi=[281, 407, 148, 52]),
            img,
        )
        if confirm_detail and confirm_detail.hit:
            # 点击确定购买按钮
            click_rect(context, Rect(284, 814, 137, 32))
            time.sleep(1.0)

            # 检查是否徽章不足（出现"获取更多"提示）
            img2 = context.tasker.controller.post_screencap().wait().get()
            badge_detail = context.run_recognition_direct(
                JRecognitionType.OCR,
                JOCR(expected=["获取更多"], roi=[283, 114, 151, 45]),
                img2,
            )
            if badge_detail and badge_detail.hit:
                # 徽章不足，关闭提示，禁用该选项的50%购买
                click_rect(context, Rect(196, 23, 63, 34))
                self._disabled_50_options.add(opt_name)
                logger.warning(f"徽章不足，终止{opt_name}的50%购买")
            else:
                logger.info(f"50%购买{opt_name}成功")
        else:
            logger.debug("未出现确定购买对话框")

    def _try_free_refresh(self, context: Context, img) -> bool:
        """尝试免费刷新"""
        refresh_detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=["免费刷新"], roi=self.FREE_REFRESH_ROI),
            img,
        )
        if refresh_detail and refresh_detail.hit:
            click_rect(context, refresh_detail.box)
            logger.info("神秘商人免费刷新")
            time.sleep(1.5)
            return True
        return False

    def _try_diamond_refresh(self, context: Context, img, diamond_limit: int) -> bool:
        """尝试钻石刷新"""
        if diamond_limit <= 0 or self._diamond_used >= diamond_limit:
            return False

        diamond_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(
                template=["流浪商人/钻石刷新.png"], roi=self.DIAMOND_REFRESH_ROI
            ),
            img,
        )
        if diamond_detail and diamond_detail.hit:
            click_rect(context, diamond_detail.box)
            time.sleep(1.0)

            # 处理钻石购买确认对话框
            img2 = context.tasker.controller.post_screencap().wait().get()
            confirm_detail = context.run_recognition_direct(
                JRecognitionType.TemplateMatch,
                JTemplateMatch(
                    template=["流浪商人/钻石购买.png"], roi=[194, 701, 334, 184]
                ),
                img2,
            )
            if confirm_detail and confirm_detail.hit:
                click_rect(context, confirm_detail.box)
                time.sleep(1.0)

            self._diamond_used += 1
            logger.info(f"神秘商人钻石刷新第{self._diamond_used}次，共{diamond_limit}次")
            return True

        return False


# ==================== 公共工具 ====================


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
