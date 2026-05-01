"""
联盟商店 Custom Action

包含：每日检查、购买

购买逻辑：
- 进入联盟商店后，在识别范围内扫描所有启用的选项
- 统帅经验无条件购买，其他选项需75%折扣标签
- 有折扣的选项还需确认使用联盟币购买
- 点击联盟币位置触发购买（不能点击物品图标，会弹出说明）
- 联盟币不足时禁用该选项，后续不再购买
- 一轮循环完毕后向上滚动一次，再识别一轮
- 无刷新机制，购买完毕即结束

完成时返回 success=True（next → 商店购买_入口），
通过 context.override_next + context + Resource.override_pipeline 禁用联盟商店_开关防止重入。
每日检查已购买时使用 override_next 跳转至商店购买_入口，避免使用 success=False。
"""

import time

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JOCR, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, get_timestamp
from utils.click_util import click_rect
from utils.merchant_utils import save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID

# 联盟商店购买选项映射: (选项名, 模板图片路径)
UNION_OPTIONS = [
    ("统帅经验", "联盟商店/统帅经验.png"),
    ("研究加速", "联盟商店/研究加速.png"),
    ("训练加速", "联盟商店/训练加速.png"),
    ("建筑加速", "联盟商店/建筑加速.png"),
    ("治疗加速", "联盟商店/治疗加速.png"),
]

# 识别范围
SCAN_ROI = [11, 184, 698, 1001]
# 滚动后识别范围
SCROLL_SCAN_ROI = [9, 903, 697, 296]

# 75%折扣标签相对选项box的offset: [x, y, w, h] 各项与box对应项相加
DISCOUNT_OFFSET = [-69, -94, -13, 21]
# 联盟币标签相对选项box的offset
COIN_OFFSET = [30, -122, -60, 16]

# 滚动参数
SCROLL_BEGIN = [351, 987, 27, 15]
SCROLL_END = [338, 529, 34, 23]
SCROLL_DURATION = 200  # 毫秒


@AgentServer.custom_action("联盟商店_每日检查")
class UnionShopDailyCheck(CustomAction):
    """检查联盟商店今天是否已购买，已购买则跳过"""

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
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
    """
    联盟商店购买逻辑

    流程：
    1. 读取启用的选项
    2. 在识别范围内扫描所有匹配选项
    3. 逐个判断并购买：
       - 统帅经验：无条件购买
       - 其他选项：需有75%折扣标签 + 联盟币标签
    4. 点击联盟币位置触发购买
    5. 处理购买确认对话框
    6. 联盟币不足时禁用该选项
    7. 一轮完毕后滚动一次，再识别一轮
    8. 结束，记录日期
    """

    # 类变量：因联盟币不足被禁用的选项
    _disabled_options: set = set()

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        # Step 1: 读取启用的选项
        enabled_options = self._get_enabled_options(context)
        if not enabled_options:
            logger.info("联盟商店无启用选项，跳过")
        else:
            logger.debug(f"联盟商店启用选项: {[name for name, _ in enabled_options]}")

        # Step 2: 第一轮识别与购买
        img = context.tasker.controller.post_screencap().wait().get()
        self._scan_and_buy(context, img, SCAN_ROI, enabled_options)

        # Step 3: 滚动一次
        self._scroll_up(context)

        # Step 4: 第二轮识别与购买
        img = context.tasker.controller.post_screencap().wait().get()
        self._scan_and_buy(context, img, SCROLL_SCAN_ROI, enabled_options)

        # Step 5: 记录日期，结束
        logger.info("联盟商店购买完成，记录日期")
        self._end(context)
        return CustomAction.RunResult(success=True)

    def _end(self, context: Context):
        save_merchant_date("联盟商店")
        UnionShopPurchase._disabled_options.clear()
        # 同时使用 context 和 resource override 禁用开关
        context.override_pipeline({"联盟商店_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"联盟商店_开关": {"enabled": False}})

    def _get_enabled_options(self, context: Context) -> list[tuple[str, str]]:
        """读取启用的购买选项"""
        enabled = []
        for name, template in UNION_OPTIONS:
            node_name = f"联盟商店_参数_{name}"
            node_data = context.get_node_data(node_name)
            if node_data and node_data.get("enabled", True):
                enabled.append((name, template))
        return enabled

    def _scan_and_buy(
        self,
        context: Context,
        img,
        roi: list[int],
        enabled_options: list[tuple[str, str]],
    ):
        """在指定范围内扫描所有启用选项并尝试购买"""
        for opt_name, template_path in enabled_options:
            if opt_name in self._disabled_options:
                continue

            # 在范围内识别选项
            detail = context.run_recognition_direct(
                JRecognitionType.TemplateMatch,
                JTemplateMatch(template=[template_path], roi=roi, threshold=0.9),
                img,
            )
            if not detail or not detail.hit:
                continue

            logger.debug(f"联盟商店识别到: {opt_name}, score={detail.best_result.score if detail.best_result else 'N/A'}")

            # 判断是否可购买
            if self._should_buy(context, img, opt_name, detail.box):
                # 点击联盟币位置触发购买
                self._click_coin_and_buy(context, img, opt_name, detail.box)
                # 购买后重新截图，因为界面可能已变化
                img = context.tasker.controller.post_screencap().wait().get()

    def _should_buy(
        self,
        context: Context,
        img,
        opt_name: str,
        box,
    ) -> bool:
        """判断选项是否应购买

        统帅经验：无条件购买
        其他选项：需有75%折扣标签
        所有可购买选项：需有联盟币标签
        """
        # 统帅经验无条件购买，但仍需确认有联盟币
        if opt_name == "统帅经验":
            return self._check_coin(context, img, box)

        # 非统帅经验：检查75%折扣标签
        box_rect = box if isinstance(box, list) else [box.x, box.y, box.w, box.h]
        discount_roi = [
            box_rect[0] + DISCOUNT_OFFSET[0],
            box_rect[1] + DISCOUNT_OFFSET[1],
            box_rect[2] + DISCOUNT_OFFSET[2],
            box_rect[3] + DISCOUNT_OFFSET[3],
        ]
        # 确保 w 和 h 至少为 1
        discount_roi[2] = max(1, discount_roi[2])
        discount_roi[3] = max(1, discount_roi[3])

        discount_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["联盟商店/75%.png"], roi=discount_roi, threshold=0.9),
            img,
        )
        if not discount_detail or not discount_detail.hit:
            logger.debug(f"{opt_name} 无75%折扣标签，跳过")
            return False

        # 有折扣，检查联盟币
        return self._check_coin(context, img, box)

    def _check_coin(self, context: Context, img, box) -> bool:
        """检查选项box附近是否存在联盟币标签"""
        box_rect = box if isinstance(box, list) else [box.x, box.y, box.w, box.h]
        coin_roi = [
            box_rect[0] + COIN_OFFSET[0],
            box_rect[1] + COIN_OFFSET[1],
            box_rect[2] + COIN_OFFSET[2],
            box_rect[3] + COIN_OFFSET[3],
        ]
        # 确保 w 和 h 至少为 1
        coin_roi[2] = max(1, coin_roi[2])
        coin_roi[3] = max(1, coin_roi[3])

        coin_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["联盟商店/联盟币.png"], roi=coin_roi, threshold=0.9),
            img,
        )
        if not coin_detail or not coin_detail.hit:
            logger.debug("未找到联盟币标签，跳过")
            return False

        return True

    def _click_coin_and_buy(
        self,
        context: Context,
        img,
        opt_name: str,
        box,
    ):
        """点击联盟币位置触发购买，并处理购买确认对话框"""
        # 计算联盟币位置
        box_rect = box if isinstance(box, list) else [box.x, box.y, box.w, box.h]
        coin_roi = [
            box_rect[0] + COIN_OFFSET[0],
            box_rect[1] + COIN_OFFSET[1],
            box_rect[2] + COIN_OFFSET[2],
            box_rect[3] + COIN_OFFSET[3],
        ]
        coin_roi[2] = max(1, coin_roi[2])
        coin_roi[3] = max(1, coin_roi[3])

        # 识别联盟币并点击其位置
        coin_detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["联盟商店/联盟币.png"], roi=coin_roi, threshold=0.9),
            img,
        )
        if not coin_detail or not coin_detail.hit:
            logger.warning(f"{opt_name} 未找到联盟币位置，跳过购买")
            return

        click_rect(context, coin_detail.box)
        logger.info(f"点击联盟币购买 {opt_name}")
        time.sleep(1.0)

        # 处理购买确认对话框
        self._handle_purchase_confirm(context, opt_name)

    def _handle_purchase_confirm(self, context: Context, opt_name: str):
        """处理购买确认对话框，检查联盟币是否充足"""
        img = context.tasker.controller.post_screencap().wait().get()
        confirm_detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(expected=["确定购买"], roi=[283, 408, 151, 49]),
            img,
        )
        if confirm_detail and confirm_detail.hit:
            # 点击确定购买按钮
            click_rect(context, [595, 695, 35, 21])
            time.sleep(0.5)
            # 点击完成/关闭按钮
            click_rect(context, [264, 810, 205, 42])
            time.sleep(1.0)

            # 检查是否联盟币不足（出现"获取更多"提示）
            img2 = context.tasker.controller.post_screencap().wait().get()
            badge_detail = context.run_recognition_direct(
                JRecognitionType.OCR,
                JOCR(expected=["获取更多"], roi=[275, 101, 156, 65]),
                img2,
            )
            if badge_detail and badge_detail.hit:
                # 联盟币不足，关闭提示3次，间隔1秒
                for _ in range(3):
                    click_rect(context, [333, 33, 28, 10])
                    time.sleep(1.0)
                # 禁用该选项
                self._disabled_options.add(opt_name)
                logger.warning(f"联盟币不足，禁用 {opt_name} 的购买")
            else:
                logger.info(f"购买 {opt_name} 成功")
        else:
            logger.debug("未出现确定购买对话框")

    def _scroll_up(self, context: Context):
        """向上滚动"""
        import random

        br = SCROLL_BEGIN
        er = SCROLL_END
        x1 = random.randint(br[0], br[0] + br[2])
        y1 = random.randint(br[1], br[1] + br[3])
        x2 = random.randint(er[0], er[0] + er[2])
        y2 = random.randint(er[1], er[1] + er[3])
        context.tasker.controller.post_swipe(
            x1, y1, x2, y2, SCROLL_DURATION
        ).wait()
        time.sleep(1)
