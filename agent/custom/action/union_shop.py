"""
联盟商店 Custom Action

包含：每日检查、购买

购买逻辑：
- 进入联盟商店后，在识别范围内扫描所有启用的选项
- 统帅经验无条件购买，其他选项需75%折扣标签
- 同一选项可能存在多个实例（如2个治疗加速），每个都需检查75%折扣
- 使用 filtered_results 获取所有超过阈值的匹配结果，逐个处理
- 每次处理前刷新截图，确保画面最新
- 统帅经验和其他加速分两次识别（逻辑不同），去除逐选项循环
- 有折扣的选项还需确认使用联盟币购买
- 点击联盟币位置触发购买（不能点击物品图标，会弹出说明）
- 联盟币不足时禁用该类物品，后续不再购买
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
from maa.pipeline import JRecognitionType, JColorMatch, JOCR, JTemplateMatch

from utils import logger
from utils import timelib
from utils.data_store import load_data, get_timestamp
from utils.click_util import click_rect
from utils.merchant_utils import save_merchant_date, SHOPPING_CATEGORY
from ..reco.record_id import RecordID

# 统帅经验模板
TZ_NAME = "统帅经验"
TZ_TEMPLATE = "联盟商店/统帅经验.png"

# 需要折扣的选项: (选项名, 模板路径)
DISCOUNT_ITEMS = [
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
# 联盟币取色区域相对选项box的offset: [x, y, w, h] 各项与box对应项相加
COIN_OFFSET = [-37, 104, -85, -53]
# 联盟币取色范围 upper/lower
COIN_UPPER = [[5, 174, 225]]
COIN_LOWER = [[5, 161, 221]]

# 滚动参数
SCROLL_BEGIN = [351, 987, 27, 15]
SCROLL_END = [338, 529, 34, 23]
SCROLL_DURATION = 200  # 毫秒


def _add_offset(box_rect: list, offset: list) -> list:
    """将 box 与 offset 逐项相加，w/h 至少为 1"""
    result = [a + b for a, b in zip(box_rect, offset)]
    result[2] = max(1, result[2])
    result[3] = max(1, result[3])
    return result


def _box_to_list(box) -> list[int]:
    """将 Rect 对象或 list 统一转为 [x, y, w, h]"""
    if isinstance(box, list):
        return box
    return [box.x, box.y, box.w, box.h]


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

    统帅经验：无条件购买（仅检查联盟币）
    折扣加速：需75%折扣标签 + 联盟币

    将模板分两组识别（统帅经验 / 折扣加速），去除逐选项循环。
    filtered_results 返回所有 NMS 后超过阈值的匹配，同种多个实例均会包含。
    """

    # 类变量：因联盟币不足被禁用的标签
    _disabled_labels: set = set()

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        # Step 1: 读取启用的选项
        tz_enabled, discount_templates = self._get_enabled_templates(context)
        if not tz_enabled and not discount_templates:
            logger.info("联盟商店无启用选项，跳过")
        else:
            labels = []
            if tz_enabled:
                labels.append(TZ_NAME)
            if discount_templates:
                labels.append("折扣加速")
            logger.debug(f"联盟商店启用选项: {labels}")

        # Step 2: 第一轮识别与购买
        img = context.tasker.controller.post_screencap().wait().get()
        img = self._scan_and_buy(context, img, SCAN_ROI, tz_enabled, discount_templates)

        # Step 3: 滚动一次
        self._scroll_up(context)

        # Step 4: 第二轮识别与购买
        img = context.tasker.controller.post_screencap().wait().get()
        self._scan_and_buy(context, img, SCROLL_SCAN_ROI, tz_enabled, discount_templates)

        # Step 5: 记录日期，结束
        logger.info("联盟商店购买完成，记录日期")
        self._end(context)
        return CustomAction.RunResult(success=True)

    def _end(self, context: Context):
        save_merchant_date("联盟商店")
        UnionShopPurchase._disabled_labels.clear()
        # 同时使用 context 和 resource override 禁用开关
        context.override_pipeline({"联盟商店_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"联盟商店_开关": {"enabled": False}})

    def _get_enabled_templates(
        self, context: Context
    ) -> tuple[bool, list[str]]:
        """读取启用的购买选项，返回 (统帅经验是否启用, 折扣加速模板列表)"""
        tz_enabled = False
        discount_templates = []

        # 检查统帅经验
        node_data = context.get_node_data(f"联盟商店_参数_{TZ_NAME}")
        if node_data and node_data.get("enabled", True):
            tz_enabled = True

        # 检查折扣加速
        for name, template in DISCOUNT_ITEMS:
            node_data = context.get_node_data(f"联盟商店_参数_{name}")
            if node_data and node_data.get("enabled", True):
                discount_templates.append(template)

        return tz_enabled, discount_templates

    def _scan_and_buy(
        self,
        context: Context,
        img,
        roi: list[int],
        tz_enabled: bool,
        discount_templates: list[str],
    ):
        """在指定范围内扫描并尝试购买

        统帅经验和其他加速分两组识别：
        - 统帅经验：单模板，无条件购买
        - 折扣加速：多模板合并识别，需75%折扣

        filtered_results 包含所有 NMS 后超过阈值的匹配结果，
        同种物品的多个实例（如2个治疗加速）都会包含在内。
        """
        # 处理统帅经验（无条件购买）
        if tz_enabled and TZ_NAME not in self._disabled_labels:
            img = self._recognize_and_process(
                context, img, roi, [TZ_TEMPLATE],
                need_discount=False, label=TZ_NAME,
            )

        # 处理折扣加速（需75%折扣）
        if discount_templates and "折扣加速" not in self._disabled_labels:
            img = self._recognize_and_process(
                context, img, roi, discount_templates,
                need_discount=True, label="折扣加速",
            )

        return img

    def _recognize_and_process(
        self,
        context: Context,
        img,
        roi: list[int],
        templates: list[str],
        need_discount: bool,
        label: str,
    ):
        """识别模板并逐个处理匹配结果

        Args:
            templates: 模板路径列表
            need_discount: 是否需要75%折扣
            label: 日志标签
        """
        detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=templates, roi=roi, threshold=0.9),
            img,
        )
        if not detail or not detail.hit:
            return img

        matches = detail.filtered_results
        logger.debug(f"联盟商店识别到 {label}: {len(matches)} 个匹配")

        for match in matches:
            # 每次都刷新截图
            img = context.tasker.controller.post_screencap().wait().get()

            box_rect = _box_to_list(match.box)

            logger.debug(
                f"联盟商店检查: {label}, "
                f"box=({box_rect[0]},{box_rect[1]},{box_rect[2]},{box_rect[3]}), "
                f"score={match.score:.3f}"
            )

            # 检查是否可购买
            can_buy = True
            if need_discount:
                can_buy = self._check_discount(context, img, box_rect)

            if can_buy:
                can_buy = self._check_coin(context, img, box_rect)

            if can_buy:
                self._click_coin_and_buy(context, img, label, box_rect)
                img = context.tasker.controller.post_screencap().wait().get()

            # 联盟币不足时跳出
            if label in self._disabled_labels:
                break

        return img

    def _check_discount(self, context: Context, img, box_rect: list[int]) -> bool:
        """检查选项box附近是否有75%折扣标签"""
        discount_roi = _add_offset(box_rect, DISCOUNT_OFFSET)
        detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=["联盟商店/75%.png"], roi=discount_roi, threshold=0.9),
            img,
        )
        if not detail or not detail.hit:
            logger.debug("无75%折扣标签，跳过")
            return False
        return True

    def _check_coin(self, context: Context, img, box_rect: list[int]) -> bool:
        """检查选项box附近是否存在联盟币（取色匹配）"""
        coin_roi = _add_offset(box_rect, COIN_OFFSET)
        detail = context.run_recognition_direct(
            JRecognitionType.ColorMatch,
            JColorMatch(upper=COIN_UPPER, lower=COIN_LOWER, roi=coin_roi, count=1),
            img,
        )
        if not detail or not detail.hit:
            logger.debug("联盟币取色不匹配，跳过")
            return False
        return True

    def _click_coin_and_buy(
        self,
        context: Context,
        img,
        label: str,
        box_rect: list[int],
    ):
        """点击联盟币位置触发购买，并处理购买确认对话框"""
        coin_roi = _add_offset(box_rect, COIN_OFFSET)

        # 取色匹配联盟币并点击该区域
        detail = context.run_recognition_direct(
            JRecognitionType.ColorMatch,
            JColorMatch(upper=COIN_UPPER, lower=COIN_LOWER, roi=coin_roi, count=1),
            img,
        )
        if not detail or not detail.hit:
            logger.warning(f"{label} 联盟币取色不匹配，跳过购买")
            return

        click_rect(context, coin_roi)
        logger.info(f"点击联盟币购买 {label}")
        time.sleep(1.0)

        # 处理购买确认对话框
        self._handle_purchase_confirm(context, label)

    def _handle_purchase_confirm(self, context: Context, label: str):
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
                # 禁用该类物品
                self._disabled_labels.add(label)
                logger.warning(f"联盟币不足，禁用 {label} 的购买")
            else:
                logger.info(f"购买 {label} 成功")
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
