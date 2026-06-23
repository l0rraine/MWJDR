from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType
import json
import re
from typing import List, Union, Optional

from utils import logger
from utils.img_util import screen_shot

# 队伍 ROI，与 bear.py / combat.py 中 ChangeTeam 一致
# 索引 0 为默认队伍，无需点击
TEAM_ROI = [
    [0, 0, 0, 0],
    [56, 117, 22, 15],
    [127, 115, 26, 23],
    [204, 113, 16, 25],
    [270, 113, 35, 26],
    [349, 117, 22, 22],
    [416, 112, 23, 32],
    [494, 113, 30, 28],
    [565, 113, 30, 29],
]

# 目标选项汇总节点名前缀，去掉前缀即 OCR expected 文本
_TARGET_PREFIX = "加入集结_目标_"

# 优先加入的目标（等级1失控的雪怪），参照 bear.py 优先大车头的逻辑
_PRIORITY_TARGET = "等级1失控的雪怪"

# 当前选中的目标列表（由 加入集结_识别队伍 读取，供识别目标使用）
JOIN_TARGETS: List[str] = []
# 当前使用的队伍编号
JOIN_TEAM = 1


def _read_join_targets(context: Context) -> List[str]:
    """读取用户勾选的加入集结目标。

    遍历 加入集结_目标选项 的 next，逐个检查
    加入集结_目标_等级X... 节点的 enabled 状态（由「目标选择」checkbox 覆盖）。
    返回去掉节点前缀后的目标名列表（直接作为 OCR expected）。
    """
    targets: List[str] = []
    try:
        next_nodes = context.get_node_data("加入集结_目标选项").get("next", [])
        for item in next_nodes:
            if isinstance(item, dict):
                name = item.get("name", "")
            elif isinstance(item, str):
                name = item
            else:
                continue
            if not name or not name.startswith(_TARGET_PREFIX):
                continue
            node_data = context.get_node_data(name)
            if node_data and node_data.get("enabled", False):
                targets.append(name.removeprefix(_TARGET_PREFIX))
    except Exception:
        pass
    return targets


@AgentServer.custom_recognition("加入集结_识别队伍")
class JoinRecoTeam(CustomRecognition):
    """加入集结入口识别：队列不满 + 有目标 + 识别到「加入集结」按钮时返回按钮 box。

    逻辑（参照 bear.py 与挖矿）：
    1. 读取队伍编号 team 与勾选目标 JOIN_TARGETS，无目标则不执行
    2. OCR 队列数量，num1==num2 表示队列已满 → 不执行
    3. 模板匹配「加入集结」按钮（加入集结.png, roi [643,523,44,47]）
    4. 命中则返回按钮 box，框架 Click 点击并 post_delay 500 进入队伍列表
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        global JOIN_TEAM, JOIN_TARGETS

        # 1. 读取队伍编号
        try:
            param = json.loads(argv.custom_recognition_param)
            JOIN_TEAM = int(param.get("team", "1"))
        except Exception:
            JOIN_TEAM = 1

        # 2. 读取勾选目标
        JOIN_TARGETS = _read_join_targets(context)
        if not JOIN_TARGETS:
            logger.debug("加入集结：未选择目标，跳过")
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        img = context.tasker.controller.post_screencap().wait().get()

        # 3. 队列判断（与挖矿_识别队伍数量一致的 OCR）
        detail = context.run_recognition("加入集结_识别队列数量", img)
        if not detail or not detail.hit:
            logger.debug("加入集结：无法识别队列数量")
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        res = re.match(r"(\d+)\D(\d+)", detail.best_result.text)
        if not res:
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        if res.group(1) == res.group(2):
            logger.debug("加入集结：队列已满，跳过")
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        # 4. 识别「加入集结」按钮
        detail = context.run_recognition(
            "加入集结_识别按钮",
            img,
            pipeline_override={
                "加入集结_识别按钮": {
                    "recognition": "TemplateMatch",
                    "template": "加入集结.png",
                    "roi": [643, 523, 44, 47],
                    "threshold": 0.8,
                    "method": 10001,
                }
            },
        )
        if not detail or not detail.hit:
            logger.debug("加入集结：未找到加入集结按钮")
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        logger.debug(f"加入集结：准备加入，目标={JOIN_TARGETS}，队伍={JOIN_TEAM}")
        return CustomRecognition.AnalyzeResult(box=detail.box, detail={})


@AgentServer.custom_recognition("加入集结_识别目标")
class JoinRecoTarget(CustomRecognition):
    """识别队伍列表中的目标行与「直接加入队伍」按钮。

    逻辑（参照 bear.py）：
    1. OCR 目标名（roi [238,183,293,936], expected 为 JOIN_TARGETS），可能识别到多个
    2. 对每个识别结果，优先「等级1失控的雪怪」（参照 bear 优先大车头排序）
    3. 逐个根据目标 box + offset [318,88,70,40] 计算「直接加入队伍」按钮 roi
    4. 模板匹配 熊/直接加入队伍.png（threshold 0.9, method 10001），命中则返回按钮 box
    若全部未命中，主动后退回到主界面，避免停留在队伍列表。
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        if not JOIN_TARGETS:
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        img = context.tasker.controller.post_screencap().wait().get()

        # 1. OCR 目标名（可能命中多个）
        ocr_roi = [238, 183, 293, 936]
        logger.info(f"加入集结：OCR目标 roi={ocr_roi}, expected={JOIN_TARGETS}")
        screen_shot(context, "加入集结_识别目标_OCR前")
        detail = context.run_recognition(
            "加入集结_识别目标_ocr",
            img,
            pipeline_override={
                "加入集结_识别目标_ocr": {
                    "recognition": "OCR",
                    "expected": JOIN_TARGETS,
                    "roi": ocr_roi,
                    "threshold": 0.6,
                }
            },
        )
        if not detail or not detail.hit:
            logger.info("加入集结：未识别到目标")
            screen_shot(context, "加入集结_未识别到目标")
            self._fallback_back(context)
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        # 打印所有 OCR 命中结果
        for r in detail.filtered_results:
            logger.info(f"加入集结：OCR命中 text={r.text}, box={list(r.box)}")

        # 2. 优先「等级1失控的雪怪」，参照 bear.py 优先大车头的排序
        result_sorted = sorted(
            detail.filtered_results,
            key=lambda x: 0 if _PRIORITY_TARGET in x.text else 1,
        )

        join_offset = [318, -88, -70, 45]

        # 3. 逐个尝试匹配「直接加入队伍」按钮
        for result in result_sorted:
            target_box = result.box
            join_roi = [a + b for a, b in zip(target_box, join_offset)]
            logger.info(
                f"加入集结：尝试匹配加入按钮 text={result.text}, "
                f"target_box={list(target_box)}, join_roi={join_roi}"
            )

            join_detail = context.run_recognition(
                "加入集结_识别_join",
                img,
                pipeline_override={
                    "加入集结_识别_join": {
                        "recognition": "TemplateMatch",
                        "template": "熊/直接加入队伍.png",
                        "roi": join_roi,
                        "threshold": 0.9,
                        "method": 10001,
                    }
                },
            )
            if join_detail and join_detail.hit:
                logger.info(f"加入集结：匹配到目标 {result.text}")
                screen_shot(context, f"加入集结_匹配成功_{result.text}")
                return CustomRecognition.AnalyzeResult(box=join_detail.box, detail={})

        logger.info("加入集结：所有目标均未找到直接加入队伍按钮")
        screen_shot(context, "加入集结_未找到加入按钮")
        self._fallback_back(context)
        return CustomRecognition.AnalyzeResult(box=None, detail={})

    def _fallback_back(self, context: Context) -> None:
        """识别失败时主动后退，避免停留在队伍列表页影响后续 JumpBack。"""
        try:
            context.run_action("加入集结_后退")
        except Exception:
            pass


@AgentServer.custom_action("加入集结_加入")
class JoinDeploy(CustomAction):
    """选择队伍（非默认队伍时点击对应 ROI）并点击出征。

    JOIN_TEAM=0 表示默认队伍，不切换。加入操作与 bear.py _select_team_and_deploy 一致，
    但各动作间隔使用节点默认 pre/post_delay，不做极限压缩。
    """

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global JOIN_TEAM
        if JOIN_TEAM > 0 and JOIN_TEAM < len(TEAM_ROI):
            roi = TEAM_ROI[JOIN_TEAM]
            context.run_action(
                "加入集结_选择队伍",
                pipeline_override={"加入集结_选择队伍": {"target": roi}},
            )
        context.run_action("加入集结_点击出征")
        logger.info(f"加入集结：已加入，队伍={JOIN_TEAM}")
        return CustomAction.RunResult(success=True)
