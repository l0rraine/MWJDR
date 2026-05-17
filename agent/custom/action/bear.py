from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JActionType, JClick, JSwipe
import json
import time

from utils import logger

# 队伍 ROI，与 combat.py 中 ChangeTeam 一致
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

# 点击加入按钮的偏移量：从识别到的队伍名 box 到加入按钮
# 示例：box 左上角 (291, 672) → 点击 (639, 790)，偏移 = (348, 118)
JOIN_OFFSET_X = 348
JOIN_OFFSET_Y = 118

# 每个阶段时长：5分14秒
PHASE_DURATION = 5 * 60 + 14


def compute_phases(team_order):
    """计算每个阶段的队伍分配。

    对于 N 支队伍，共 N 个阶段：
    - 阶段 1~N-1：每阶段派 N-1 支队伍（旋转列表，取前 N-1 个）
    - 阶段 N：派全部 N 支队伍

    旋转规则：每次将最后一个元素移到最前面。
    """
    n = len(team_order)
    phases = []
    current = list(team_order)

    for _ in range(n - 1):
        phases.append(current[:n - 1])
        current = [current[-1]] + current[:-1]

    phases.append(current)
    return phases


@AgentServer.custom_action("熊_开始战斗")
class BearCombat(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        start_time_str = param.get("开始时间", "20:00")
        team_names_str = param.get("队伍名", "")
        team_order_str = param.get("循环顺序", "0")

        team_names = [name.strip() for name in team_names_str.split(",") if name.strip()]
        team_order = [int(x.strip()) for x in team_order_str.split(",") if x.strip()]

        if not team_names:
            logger.warning("未配置目标队伍名，无法执行打熊")
            return CustomAction.RunResult(success=False)
        if not team_order:
            logger.warning("未配置循环顺序，无法执行打熊")
            return CustomAction.RunResult(success=False)

        # 构建部分匹配的 expected 列表
        expected = [f".*{name}.*" for name in team_names]

        # 计算阶段分配
        phases = compute_phases(team_order)

        logger.info(
            f"打熊配置: 开始时间={start_time_str}, 目标队伍={team_names}, "
            f"循环顺序={team_order}, 共{len(phases)}个阶段"
        )
        for i, phase in enumerate(phases):
            logger.info(f"  阶段{i + 1}: {phase}")

        # 等待开始时间
        self._wait_for_start(start_time_str)

        # 执行各阶段
        phase_start_time = time.time()

        for phase_idx, phase_teams in enumerate(phases):
            is_last_phase = phase_idx == len(phases) - 1

            for team_id in phase_teams:
                # 查找并加入目标队伍
                if not self._find_and_join(context, expected):
                    logger.warning("未能成功加入队伍，跳过本次")
                    continue

                # 选择队伍并出征
                if not self._select_team_and_deploy(context, team_id):
                    logger.warning("出征失败，跳过本次")
                    continue

            # 非最后阶段，等待下一阶段
            if not is_last_phase:
                elapsed = time.time() - phase_start_time
                wait_time = PHASE_DURATION - elapsed
                if wait_time > 0:
                    logger.info(
                        f"阶段{phase_idx + 1}完成，等待 {wait_time:.0f} 秒进入下一阶段"
                    )
                    time.sleep(wait_time)
                phase_start_time = time.time()

        logger.info("打熊全部阶段完成")
        return CustomAction.RunResult(success=False)

    def _wait_for_start(self, start_time_str: str):
        """等待到指定开始时间。"""
        try:
            hour, minute = map(int, start_time_str.split(":"))
        except ValueError:
            logger.warning(f"无效的开始时间格式: {start_time_str}")
            return

        now = time.localtime()
        target = time.struct_time((
            now.tm_year, now.tm_mon, now.tm_mday,
            hour, minute, 0,
            now.tm_wday, now.tm_yday, now.tm_isdst,
        ))
        target_ts = time.mktime(target)
        now_ts = time.mktime(now)

        if target_ts <= now_ts:
            target_ts += 24 * 3600

        wait_seconds = target_ts - now_ts
        logger.info(f"距离开始时间 {start_time_str} 还有 {wait_seconds:.0f} 秒")
        time.sleep(wait_seconds)
        logger.info(f"开始时间 {start_time_str} 到达，开始打熊")

    def _find_and_join(self, context: Context, expected: list) -> bool:
        """在集结列表中查找目标队伍并点击加入。

        返回 True 表示成功进入队伍选择界面。
        """
        while True:
            img = context.tasker.controller.post_screencap().wait().get()

            detail = context.run_recognition("熊_识别队伍", img, {
                "熊_识别队伍": {"expected": expected}
            })

            if detail is not None and detail.hit:
                box = detail.box
                logger.debug(
                    f"找到目标队伍: {detail.best_result.text} "
                    f"at ({box.x}, {box.y})"
                )

                # 使用偏移量点击加入按钮
                click_x = box.x + JOIN_OFFSET_X
                click_y = box.y + JOIN_OFFSET_Y
                context.tasker.controller.post_click(click_x, click_y).wait()

                # 验证点击是否成功
                time.sleep(0.1)
                img = context.tasker.controller.post_screencap().wait().get()
                verify = context.run_recognition("熊_点击验证", img)

                if verify is not None and verify.hit:
                    # 偏移点击未命中，直接点击识别位置
                    logger.debug("偏移点击未命中，直接点击识别位置")
                    context.tasker.controller.post_click(
                        box.x + box.w // 2, box.y + box.h // 2
                    ).wait()
                    time.sleep(0.1)

                return True

            # 未找到，向下滚动
            context.run_task("熊_向下滚动")

    def _select_team_and_deploy(self, context: Context, team_id: int) -> bool:
        """选择队伍（非默认队伍时点击 ROI）并点击出征。

        返回 True 表示成功出征并返回集结列表。
        """
        if team_id > 0:
            if team_id < len(TEAM_ROI):
                roi = TEAM_ROI[team_id]
                context.run_action_direct(
                    JActionType.Click,
                    JClick(target=roi),
                )
                logger.debug(f"选择队伍 {team_id}")
            else:
                logger.warning(f"队伍索引 {team_id} 超出范围，使用默认队伍")

        # 点击出征
        context.run_task("点击出征")

        # 验证返回集结列表
        time.sleep(0.3)
        for _ in range(5):
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("熊_返回集结列表", img)
            if detail is not None and detail.hit:
                logger.debug("已返回集结列表")
                return True
            time.sleep(0.3)

        # 未返回，点击返回按钮
        logger.debug("未返回集结列表，点击返回")
        context.run_action_direct(
            JActionType.Click,
            JClick(target=[30, 34, 32, 8]),
        )

        time.sleep(0.5)
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("熊_返回集结列表", img)
        if detail is not None and detail.hit:
            logger.debug("点击返回后已回到集结列表")
            return True

        logger.warning("无法返回集结列表")
        return False
