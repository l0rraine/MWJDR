"""
神秘商店 Custom Action

包含：每日检查、购买（含免费购买、50%折扣购买、免费刷新、钻石刷新）

购买逻辑：
- 屏幕1（5个槽位）→ Swipe上滑 → 屏幕2（3个槽位）→ 刷新
- 每个槽位独立检查：免费物品 → 50%折扣物品（取色+模板匹配）
- 购买后重新截图，从屏幕1重新搜索
- 无法购买且无法刷新时结束

完成时返回 success=True（空 next → JumpBack 回到商店购买_入口），
通过 Resource.override_pipeline 禁用神秘商店_开关防止重入。
"""

import json
import random
import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.define import Rect
from maa.pipeline import JRecognitionType, JColorMatch, JOCR, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, get_timestamp
from utils.click_util import click_rect
from utils.merchant_utils import save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID

# 神秘商店购买选项映射: (选项名, 模板图片路径)
MYSTERY_OPTIONS = [
    ("当季专武", "神秘商店/专武.png"),
    ("宠物自选箱", "神秘商店/宠物自选箱.png"),
    ("高级野性标记", "神秘商店/高级野性标记.png"),
    ("行军加速", "神秘商店/行军加速.png"),
    ("橙碎", "神秘商店/橙碎.png"),
]


@AgentServer.custom_action("神秘商店_每日检查")
class MysteryMerchantDailyCheck(CustomAction):
    """检查神秘商店今天是否已购买，已购买则跳过"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        account_id = RecordID.current_account_id()
        data = load_data()
        timestamp = get_timestamp(data, SHOPPING_CATEGORY, account_id, "神秘商店")

        if timelib.is_today(timestamp):
            logger.info(f"神秘商店今日已购买，跳过 (timestamp={timestamp})")
            context.tasker.resource.override_pipeline({"神秘商店_开关": {"enabled": False}})
            return CustomAction.RunResult(success=True)

        logger.info("神秘商店今日未购买，开始购买")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("神秘商店_购买")
class MysteryMerchantPurchase(CustomAction):
    """
    神秘商店购买逻辑

    流程：
    1. 截取专武模板图片
    2. 循环：
       a. 搜索屏幕1的5个槽位
       b. 无购买 → Swipe上滑 → 搜索屏幕2的3个槽位
       c. 有购买 → 重新截图，从屏幕1重新搜索
       d. 无可购买 → 免费刷新 → 钻石刷新
       e. 无法刷新 → 记录日期，结束
    """

    # 类变量：因徽章不足被禁用的50%购买选项
    _disabled_50_options: set = set()
    # 类变量：已使用钻石刷新次数
    _diamond_used: int = 0

    # 屏幕1的5个槽位 ROI
    SCREEN1_SLOTS = [
        [240, 419, 241, 286],
        [480, 419, 220, 280],
        [14, 708, 227, 281],
        [242, 708, 234, 285],
        [477, 709, 229, 280],
    ]

    # 屏幕2的3个槽位 ROI（Swipe上滑后可见）
    SCREEN2_SLOTS = [
        [14, 909, 231, 280],
        [245, 909, 228, 279],
        [472, 914, 235, 272],
    ]

    # Swipe 参数
    SWIPE_BEGIN = [211, 1089, 11, 12]
    SWIPE_END = [207, 953, 9, 8]
    SWIPE_DURATION = 50  # 毫秒

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
            logger.info("神秘商店无启用选项，仅购买免费物品")
        else:
            logger.debug(f"神秘商店启用选项: {[name for name, _ in enabled_options]}")

        # Step 2: 购买循环
        while True:
            # 2a: 搜索屏幕1
            self._swipe_down(context)
            self._search_slots(context, self.SCREEN1_SLOTS, enabled_options)

            # 2b: Swipe上滑，搜索屏幕2
            self._swipe_up(context)
            img = context.tasker.controller.post_screencap().wait().get()
            self._search_slots(context, self.SCREEN2_SLOTS, enabled_options)

            # 2c: 无可购买物品，尝试刷新
            if self._try_free_refresh(context, img):
                continue
            if self._try_diamond_refresh(context, img, diamond_limit):
                continue
            break

        # Step 3: 记录日期，结束
        logger.info("神秘商店购买完成，记录日期")
        self._end(context)
        return CustomAction.RunResult(success=True)

    def _end(self, context: Context):
        save_merchant_date("神秘商店")
        MysteryMerchantPurchase._disabled_50_options.clear()
        MysteryMerchantPurchase._diamond_used = 0
        context.tasker.resource.override_pipeline({"神秘商店_开关": {"enabled": False}})

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
            node_name = f"神秘商店_参数_{name}"
            node_data = context.get_node_data(node_name)
            if node_data and node_data.get("enabled", True):
                enabled.append((name, template))
        return enabled

    def _search_slots(
        self,
        context: Context,
        slots: list[list[int]],
        enabled_options: list[tuple[str, str]],
    ) -> bool:
        """搜索一组槽位，发现可购买物品则购买

        Returns:
            True: 购买了物品
            False: 无可购买物品
        """
        for slot_roi in slots:
            self._try_buy_slot(context, slot_roi, enabled_options)

    def _try_buy_slot(
        self,
        context: Context,
        slot_roi: list[int],
        enabled_options: list[tuple[str, str]],
    ) -> bool:
        """检查单个槽位，尝试购买免费或50%折扣物品

        Args:
            slot_roi: 槽位搜索区域 [x, y, w, h]

        Returns:
            True: 购买了物品
            False: 无可购买物品
        """
        # 检查免费物品
        img = context.tasker.controller.post_screencap().wait().get()
        free_detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=["免费"], roi=slot_roi),
            img,
        )
        if free_detail and free_detail.hit:
            click_rect(context, free_detail.box)
            logger.info("发现免费物品，购买")
            time.sleep(1.0)
            return True

        # 检查50%折扣物品
        discount_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["神秘商店/50%.png"], roi=slot_roi),
            img,
        )
        if not discount_detail or not discount_detail.hit:
            return False

        box = discount_detail.box

        # 取色检查：offset [36, 171, -37, -31]
        color_roi = [box.x + 36, box.y + 171, box.w - 37, box.h - 31]
        color_detail = context.run_recognition_direct(
            JRecognitionType.ColorMatch,
            JColorMatch(
                lower=[[4, 170, 224]],
                upper=[[5, 204, 237]],
                roi=color_roi,
                method=4,
                count=1,
            ),
            img,
        )
        if not color_detail or not color_detail.hit:
            logger.debug("50%标签取色不匹配，跳过")
            return False

        # 物品图标搜索：offset [51, 42, 57, 72] 与box四项分别相加
        item_roi = [box.x + 51, box.y + 42, box.w + 57, box.h + 72]

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

            # 找到匹配物品，点击购买区域（offset [57, 212, 53, -16]）
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

    def _swipe_up(self, context: Context):
        """向上Swipe，从begin区域随机点到end区域随机点"""
        br = self.SWIPE_BEGIN
        er = self.SWIPE_END
        x1 = random.randint(br[0], br[0] + br[2])
        y1 = random.randint(br[1], br[1] + br[3])
        x2 = random.randint(er[0], er[0] + er[2])
        y2 = random.randint(er[1], er[1] + er[3])
        context.tasker.controller.post_swipe(
            x1, y1, x2, y2, self.SWIPE_DURATION
        ).wait()
        time.sleep(1)

    def _swipe_down(self, context: Context):
        """向下Swipe，从begin区域随机点到end区域随机点"""
        er = self.SWIPE_BEGIN
        br = self.SWIPE_END
        x1 = random.randint(br[0], br[0] + br[2])
        y1 = random.randint(br[1], br[1] + br[3])
        x2 = random.randint(er[0], er[0] + er[2])
        y2 = random.randint(er[1], er[1] + er[3])
        context.tasker.controller.post_swipe(x1, y1, x2, y2, self.SWIPE_DURATION).wait()
        time.sleep(1)

    def _try_free_refresh(self, context: Context, img) -> bool:
        """尝试免费刷新"""
        refresh_detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=["免费刷新"], roi=self.FREE_REFRESH_ROI),
            img,
        )
        if refresh_detail and refresh_detail.hit:
            click_rect(context, refresh_detail.box)
            logger.info("神秘商店免费刷新")
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
            logger.info(f"神秘商店钻石刷新第{self._diamond_used}次，共{diamond_limit}次")
            return True

        return False
