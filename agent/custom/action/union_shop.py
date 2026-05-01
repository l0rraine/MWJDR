"""
联盟商店 Custom Action

包含：每日检查、购买

购买逻辑：
- 进入联盟商店后，在识别范围内扫描所有启用的选项
- 统帅经验无条件购买，其他选项需75%折扣标签
- 同一选项可能存在多个实例（如2个治疗加速），每个都需检查75%折扣
- 逐模板识别：每次传入单个模板，filtered_results 返回该模板所有超过阈值的匹配
- 每次处理前刷新截图，确保画面最新
- 有折扣的选项还需确认使用联盟币购买
- 点击联盟币位置触发购买（不能点击物品图标，会弹出说明）
- 联盟币不足时禁用该类物品，后续不再购买
- 一轮循环完毕后向上滚动一次，再识别一轮
- 无刷新机制，购买完毕即结束

75%折扣、联盟币、确定购买、获取更多等识别通过 pipeline JSON 定义，
使用 context.run_recognition + pipeline_override 动态覆盖 ROI。
滚动通过 pipeline JSON 的 Swipe 动作执行。

完成时返回 success=True（next → 商店购买_入口），
通过 context.override_next + context + Resource.override_pipeline 禁用联盟商店_开关防止重入。
每日检查已购买时使用 override_next 跳转至商店购买_入口，避免使用 success=False。
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
SCROLL_SCAN_ROI = [9, 903, 697, 296]

# 75%折扣标签相对选项box的offset: [x, y, w, h] 各项与box对应项相加
DISCOUNT_OFFSET = [-69, -94, -13, 21]
# 联盟币取色区域相对选项box的offset: [x, y, w, h] 各项与box对应项相加
COIN_OFFSET = [-37, 104, -85, -53]


def _add_offset(box_rect: list, offset: list) -> list:
    """将 box 与 offset 逐项相加，w/h 至少为 1"""
    result = [a + b for a, b in zip(box_rect, offset)]
    result[2] = max(1, result[2])
    result[3] = max(1, result[3])
    return result


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

    逐模板识别：每次传入单个模板调用 run_recognition_direct，
    filtered_results 返回该模板所有超过阈值的匹配，同种多个实例均会包含。
    75%折扣、联盟币、确定购买、获取更多等识别通过 pipeline JSON 定义，
    使用 context.run_recognition + pipeline_override 动态覆盖 ROI。
    """

    _disabled_labels: set = set()

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        # Step 1: 读取启用的选项
        tz_enabled = False
        discount_templates = []

        node_data = context.get_node_data(f"联盟商店_参数_{TZ_NAME}")
        if node_data and node_data.get("enabled", True):
            tz_enabled = True

        for name, template in DISCOUNT_ITEMS:
            node_data = context.get_node_data(f"联盟商店_参数_{name}")
            if node_data and node_data.get("enabled", True):
                discount_templates.append(template)

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
        context.run_task("联盟商店_滚动")

        # Step 4: 第二轮识别与购买
        img = context.tasker.controller.post_screencap().wait().get()
        self._scan_and_buy(context, img, SCROLL_SCAN_ROI, tz_enabled, discount_templates)

        # Step 5: 记录日期，结束
        logger.info("联盟商店购买完成，记录日期")
        save_merchant_date("联盟商店")
        UnionShopPurchase._disabled_labels.clear()
        context.override_pipeline({"联盟商店_开关": {"enabled": False}})
        context.tasker.resource.override_pipeline({"联盟商店_开关": {"enabled": False}})

        return CustomAction.RunResult(success=True)

    def _scan_and_buy(
        self,
        context: Context,
        img,
        roi: list[int],
        tz_enabled: bool,
        discount_templates: list[str],
    ):
        """在指定范围内扫描并尝试购买

        逐模板识别，每次传入单个模板：
        - 统帅经验：单模板，无条件购买
        - 折扣加速：逐个模板识别，需75%折扣

        filtered_results 包含该模板所有 NMS 后超过阈值的匹配结果，
        同种物品的多个实例（如2个治疗加速）都会包含在内。
        """
        # 处理统帅经验（无条件购买）
        if tz_enabled and TZ_NAME not in self._disabled_labels:
            img = self._recognize_and_process(
                context, img, roi, TZ_TEMPLATE,
                need_discount=False, label=TZ_NAME,
            )

        # 处理折扣加速（逐模板识别，需75%折扣）
        if discount_templates and "折扣加速" not in self._disabled_labels:
            for template_path in discount_templates:
                img = self._recognize_and_process(
                    context, img, roi, template_path,
                    need_discount=True, label="折扣加速",
                )
                if "折扣加速" in self._disabled_labels:
                    break

        return img

    def _recognize_and_process(
        self,
        context: Context,
        img,
        roi: list[int],
        template_path: str,
        need_discount: bool,
        label: str,
    ):
        """识别单个模板并逐个处理匹配结果

        Args:
            template_path: 单个模板路径
            need_discount: 是否需要75%折扣
            label: 日志标签
        """
        detail = context.run_recognition_direct(
            JRecognitionType.TemplateMatch,
            JTemplateMatch(template=[template_path], roi=roi, threshold=[0.9]),
            img,
        )
        if not detail or not detail.hit:
            return img

        matches = detail.filtered_results
        logger.debug(
            f"联盟商店识别到 {label} ({template_path}): "
            f"{len(matches)} 个匹配"
        )

        for match in matches:
            # 每次都刷新截图
            img = context.tasker.controller.post_screencap().wait().get()

            box = match.box
            box_rect = [box.x, box.y, box.w, box.h] if not isinstance(box, list) else box

            logger.debug(
                f"联盟商店检查: {label}, "
                f"box=({box_rect[0]},{box_rect[1]},{box_rect[2]},{box_rect[3]}), "
                f"score={match.score:.3f}"
            )

            # 检查75%折扣标签
            if need_discount:
                discount_roi = _add_offset(box_rect, DISCOUNT_OFFSET)
                discount_detail = context.run_recognition(
                    "联盟商店_75%折扣", img,
                    pipeline_override={"联盟商店_75%折扣": {"roi": discount_roi}},
                )
                if not discount_detail or not discount_detail.hit:
                    logger.debug("无75%折扣标签，跳过")
                    continue

            # 检查联盟币（取色匹配）
            coin_roi = _add_offset(box_rect, COIN_OFFSET)
            coin_detail = context.run_recognition(
                "联盟商店_联盟币", img,
                pipeline_override={"联盟商店_联盟币": {"roi": coin_roi}},
            )
            if not coin_detail or not coin_detail.hit:
                logger.debug("联盟币取色不匹配，跳过")
                continue

            # 点击联盟币位置触发购买
            click_rect(context, coin_roi)
            logger.info(f"点击联盟币购买 {label}")
            time.sleep(1.0)

            # 处理购买确认对话框（识别+点击确定→点击完成→检查联盟币不足）
            img = context.tasker.controller.post_screencap().wait().get()
            confirm_detail = context.run_recognition("联盟商店_确定购买", img)
            if confirm_detail and confirm_detail.hit:
                # 点击确定购买→点击完成（pipeline next 链式执行）
                context.run_task("联盟商店_确定购买")

                # 检查是否联盟币不足（出现"获取更多"提示）
                img2 = context.tasker.controller.post_screencap().wait().get()
                badge_detail = context.run_recognition("联盟商店_获取更多", img2)
                if badge_detail and badge_detail.hit:
                    # 联盟币不足，关闭提示3次
                    for _ in range(3):
                        context.run_task("联盟商店_关闭提示")
                    self._disabled_labels.add(label)
                    logger.warning(f"联盟币不足，禁用 {label} 的购买")
                else:
                    logger.info(f"购买 {label} 成功")
            else:
                logger.debug("未出现确定购买对话框")

            img = context.tasker.controller.post_screencap().wait().get()

            # 联盟币不足时跳出
            if label in self._disabled_labels:
                break

        return img
