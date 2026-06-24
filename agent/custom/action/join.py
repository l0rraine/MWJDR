from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType
import json
import re
from typing import List, Union, Optional

from utils import logger

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

# 优先加入的目标（等级1失控的雪怪），最优先
_PRIORITY_TARGET = "等级1失控的雪怪"

# 当前选中的目标列表（由 加入集结_识别队伍 读取，供执行加入使用）
JOIN_TARGETS: List[str] = []
# 当前使用的队伍编号
JOIN_TEAM = 1

# 「直接加入队伍」按钮相对目标名的 offset
# join_roi = target_box + offset = [x+318, y-88, w-70, h+45]
_JOIN_OFFSET = [318, -88, 0, 50]


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


def _target_sort_key(text: str) -> tuple:
    """目标排序键：等级1失控的雪怪最优先，等级1-8按等级逆序(高等级优先)。

    返回 (优先级组, 等级)：
    - 雪怪 → (0, 0) 最先
    - 等级8 → (1, -8)
    - 等级7 → (1, -7)
    - ...
    - 等级1 → (1, -1)
    sorted 默认升序，等级取负使高等级排前面。
    """
    if _PRIORITY_TARGET in text:
        return (0, 0)
    # 提取"等级X"中的数字
    m = re.search(r"等级(\d+)", text)
    level = int(m.group(1)) if m else 0
    # 等级高的排前面 → 等级取负，使升序排列时大的在前
    return (1, -level)


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
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        img = context.tasker.controller.post_screencap().wait().get()

        # 3. 队列判断（与挖矿_识别队伍数量一致的 OCR）
        detail = context.run_recognition("加入集结_识别队列数量", img)
        if not detail or not detail.hit:
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        res = re.match(r"(\d+)\D(\d+)", detail.best_result.text)
        if not res:
            return CustomRecognition.AnalyzeResult(box=None, detail={})
        if res.group(1) == res.group(2):
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
            return CustomRecognition.AnalyzeResult(box=None, detail={})

        return CustomRecognition.AnalyzeResult(box=detail.box, detail={})


@AgentServer.custom_action("加入集结_执行加入")
class JoinDeploy(CustomAction):
    """加入集结全流程 action：识别目标 → 匹配加入按钮 → 点击加入 → 选队出征 → 后退。

    由 加入集结_入口 recognition 命中(已Click进入集结列表页)后调用。
    全流程在 action 内完成识别与加入，后退由 pipeline 的 next 节点
    (加入集结_后退) 统一处理，避免 action 内与 next 链重复后退。
    无论成功与否 action 返回 success=True，流程经 加入集结_后退 →
    新手_等待(sleep扫描间隔) 后回主循环，避免失败时紧循环。

    逻辑（参照 bear.py）：
    1. OCR 目标名（roi [238,183,293,936], expected 为 JOIN_TARGETS）
    2. 排序：等级1失控的雪怪最优先，等级1-8逆序(高等级优先)
    3. 逐个根据目标 box + offset 计算「直接加入队伍」按钮 roi
    4. 模板匹配 熊/直接加入队伍.png，命中则点击加入 → 选队 → 出征
    5. 全部未命中或 OCR 未识别到 → 直接返回(由 next 链后退)
    """

    def run(
        self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult:
        global JOIN_TEAM

        if not JOIN_TARGETS:
            return CustomAction.RunResult(success=True)

        img = context.tasker.controller.post_screencap().wait().get()

        # 1. OCR 目标名
        detail = context.run_recognition(
            "加入集结_识别目标_ocr",
            img,
            pipeline_override={
                "加入集结_识别目标_ocr": {
                    "recognition": "OCR",
                    "expected": JOIN_TARGETS,
                    "roi": [238, 183, 293, 936],
                    "threshold": 0.6,
                }
            },
        )
        if not detail or not detail.hit:
            return CustomAction.RunResult(success=True)

        # 2. 排序：雪怪最优先，等级1-8逆序
        result_sorted = sorted(
            detail.filtered_results, key=lambda x: _target_sort_key(x.text)
        )

        # 3. 逐个尝试匹配「直接加入队伍」按钮
        for result in result_sorted:
            target_box = result.box
            join_roi = [a + b for a, b in zip(target_box, _JOIN_OFFSET)]

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
                # 点击加入按钮进入队伍选择页
                context.run_action(
                    "加入集结_点击加入",
                    pipeline_override={
                        "加入集结_点击加入": {"target": list(join_detail.box)}
                    },
                )
                # 选队并出征
                if JOIN_TEAM > 0 and JOIN_TEAM < len(TEAM_ROI):
                    context.run_action(
                        "加入集结_选择队伍",
                        pipeline_override={
                            "加入集结_选择队伍": {"target": TEAM_ROI[JOIN_TEAM]}
                        },
                    )
                context.run_action("加入集结_点击出征")
                logger.info(f"加入集结：已加入 {result.text}，队伍={JOIN_TEAM}")
                return CustomAction.RunResult(success=True)

        return CustomAction.RunResult(success=True)
