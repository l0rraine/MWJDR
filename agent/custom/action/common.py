import re
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JTemplateMatch
import json
import random
import time
from utils import logger
from utils.ocr_util import ocr_until_consistent_by_task
from utils.merchant_utils import save_task_date, disable_switch, daily_check
from utils import timelib
@AgentServer.custom_action("新手_设置扫描间隔")
class NewbieSetInterval(CustomAction):
    """将用户输入的扫描间隔(秒)转为毫秒，override 到 新手_等待.pre_delay。

    新手_等待 本身用 pre_delay + DoNothing(框架管理延迟，不阻塞 Python 层)。
    本 action 瞬间完成(不 sleep)，仅做单位转换与 override。
    interval 由 interface 的「扫描间隔」input(秒)注入。
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        try:
            param = json.loads(argv.custom_action_param)
            interval = int(param.get("interval", "60"))
        except Exception:
            interval = 60
        # 秒转毫秒，override 新手_等待.pre_delay
        context.override_pipeline({"新手_等待": {"pre_delay": interval * 1000}})
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("根据需要切换角色")
class SwitchCharacter(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        json_data = json.loads(argv.custom_action_param)
        
        region = json_data.get('王国编号') or "3194"
        index = json_data.get('王国内序号')
        logger.debug(f"王国编号:{region},王国内序号:{index}")
        expected = f"王国\\D+{region}"
        
        cha_detail = None
        region_detail = None
        count = 3
        while count > 0 and (cha_detail is None or not cha_detail.hit):
            try:
                img = context.tasker.controller.post_screencap().wait().get()
                region_detail = context.run_recognition(
                    "国度信息",
                    img,
                    {"国度信息": {"expected": expected}},
                )
                if not region_detail or not region_detail.hit:
                    logger.debug(f"未找到国度信息,期望值：{expected}")
                else:
                    logger.debug(f"国度信息：{region_detail.best_result.text}")
                    cha_detail = context.run_recognition(
                        "选中角色",
                        img,
                        {"选中角色":{"roi":[region_detail.best_result.box.x+402,region_detail.best_result.box.y+70,119,231]}}
                    )
                    if cha_detail and cha_detail.hit:
                        logger.debug(f"是否是第一个角色：{cha_detail.best_result.box.y-region_detail.best_result.box.y<170}")
            except Exception as e:
                logger.debug(f"第 {4 - count} 次执行出错: {e}")
            finally:                
                count -= 1
                time.sleep(2)
        
        if not cha_detail or not cha_detail.hit or not region_detail or not region_detail.hit:
            logger.warning("未能识别角色信息，跳过切换")
            return CustomAction.RunResult(success=True)

        offset_y = cha_detail.best_result.box.y - region_detail.best_result.box.y
        if index == "1" and offset_y > 170:
            context.run_task(
                "点击角色",
                {"点击角色":
                    {"target":[cha_detail.best_result.box.x,cha_detail.best_result.box.y-170,cha_detail.best_result.box.w,cha_detail.best_result.box.h]}
                })
            logger.info(f"切换到第一个角色")
        elif index == "2" and offset_y < 170:
            context.run_task(
                "点击角色",
                {"点击角色":
                    {"target":[cha_detail.best_result.box.x,cha_detail.best_result.box.y+170,cha_detail.best_result.box.w,cha_detail.best_result.box.h]}
                })
            logger.info(f"切换到第二个角色")
        else:
            logger.info(f"当前已是第{index}个角色，无需切换")

        # 在角色管理界面 OCR 角色ID
        from ..reco.record_id import RecordID
        from utils.ocr_util import ocr_until_consistent
        account_id = ocr_until_consistent(
            context,
            roi=RecordID._id_roi,
            expected_pattern=RecordID._id_pattern,
        )
        if account_id:
            RecordID._account_id = account_id
            logger.info(f"角色ID已识别：{account_id}")
        else:
            logger.warning("角色ID识别失败，将使用默认存储")
            RecordID._account_id = ""

        return CustomAction.RunResult(success=True)

# 确保所有任务执行前有队列可用，1. 判断是否有战斗任务 2. 关闭自动加入 3.如果有不是挖矿的队伍，等待  4. 如果全部在挖矿，召回最后一队
@AgentServer.custom_action("确保有队列可用")
class MakeSureQueueAvailable(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        # 0. 如果后续没有战斗任务，跳过确保空闲队列
        from utils.mfa_config import has_battle_tasks
        battle_status = has_battle_tasks()
        if battle_status is False:
            logger.info("后续无战斗任务，跳过确保空闲队列")
            return CustomAction.RunResult(success=True)

        # 1. 关闭自动加入
        logger.debug("关闭自动加入集结")
        context.run_task("自动加入集结_关闭_入口")  
        context.run_task("转到城外") 
        context.run_task("开始查看队列")
        text = ocr_until_consistent_by_task(context, "识别当前队列数量", expected_pattern=r'\d+/\d+')
        if text is None:
            logger.warning("识别队列数量失败")
            return CustomAction.RunResult(success=False)
        logger.debug(f"队列情况：{text}")
        match = re.search(r'\d+', text)
        if match and int(match.group())>0:
            return CustomAction.RunResult(success=True)

        context.run_task("后退")
        _, b = map(int, text.split('/'))

        logger.info(f"当前队列已满，队列总数为{b}")
        # 2.如果有不是挖矿的队伍，等待
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("识别队列动作",img)
        if detail.hit:
            logger.info("开始等待出征队伍回归")

        # 3. 如果全部在挖矿，召回最后一队
        else:
            recall_region = [
                [200,544,43,56],
                [200,484,43,56],
                [200,424,43,56],
                [200,364,43,56],
                [200,304,43,56],
                [200,244,43,56]
                
            ]
            img = context.tasker.controller.post_screencap().wait().get()
            for region in recall_region[-b:]:
                detail = context.run_recognition_direct(
                    JRecognitionType.TemplateMatch,
                    JTemplateMatch(template=["召回.png"], roi=region),
                    img,
                )
                if detail.hit:
                    context.run_task("点击召回",{
                        "点击召回": {
                            "target": region
                        }
                    })
                    logger.info("已召回队伍，开始等待")
                    break

        context.run_task("开始查看队列")
        while True:
            time.sleep(1)
            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("识别当前队列数量", img)
            if detail.hit:
                match = re.search(r'\d+', detail.best_result.text)
                if match and int(match.group())>0:
                    break                

        return CustomAction.RunResult(success=True)

@AgentServer.custom_action("NodeParaCombine")
class NodeParaCombine(CustomAction):   
    """
    在 node 合并不同的参数 。

    参数格式:
    {
        "node_name": {"参数1": "值1",...},
        "node_name": {"参数2": "值2",...}
    }
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:

        node_name = json.loads(argv.custom_action_param)["node_name"]
        node_data = context.get_node_data(node_name)
        logger.debug(node_data)
        context.override_pipeline({f"{node_name}": {"enabled": False}})

        return CustomAction.RunResult(success=True)
@AgentServer.custom_action("DisableNode")
class DisableNode(CustomAction):
    """
    将特定 node 设置为 disable 状态 。

    参数格式:
    {
        "node_name": "结点名称"
    }
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:

        node_name = json.loads(argv.custom_action_param)["node_name"]

        context.override_pipeline({f"{node_name}": {"enabled": False}})

        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("NodeOverride")
class NodeOverride(CustomAction):
    """
    在 node 中执行 pipeline_override 。

    参数格式:
    {
        "node_name": {"被覆盖参数": "覆盖值",...},
        "node_name1": {"被覆盖参数": "覆盖值",...}
    }
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:

        ppover = json.loads(argv.custom_action_param)

        if not ppover:
            logger.warning("No ppover")
            return CustomAction.RunResult(success=True)

        logger.debug(f"NodeOverride: {ppover}")
        context.override_pipeline(ppover)

        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("每日检查")
class DailyCheck(CustomAction):
    """通用每日检查 action

    检查今日是否已完成指定任务，已完成则禁用开关并跳过。
    通过 custom_action_param 传参，无需为每个任务新建 action 类。

    参数格式:
    {
        "task_name": "任务名称，如 游荡商人、海岛打理",
        "switch_name": "pipeline 开关节点名，如 游荡商人_开关",
        "current_node": "当前节点名（可选，用于 override_next）",
        "skip_next": "跳转目标节点名（可选，用于 override_next）"
    }
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        task_name = param["task_name"]
        switch_name = param["switch_name"]
        current_node = param.get("current_node")
        skip_next = param.get("skip_next")

        daily_check(context, task_name, switch_name, current_node, skip_next)
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("记录日期")
class RecordDate(CustomAction):
    """通用记录日期 action

    记录任务完成日期，可选禁用 pipeline 开关。
    通过 custom_action_param 传参，无需为每个任务新建 action 类。

    参数格式:
    {
        "task_name": "任务名称，如 游荡商人、海岛打理",
        "switch_name": "开关节点名（可选，提供则同时禁用开关）"
    }
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        task_name = param["task_name"]
        switch_name = param.get("switch_name")

        save_task_date(task_name)
        if switch_name:
            disable_switch(context, switch_name)
        logger.info(f"{task_name}完成，记录日期")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("下午检查")
class AfternoonCheck(CustomAction):
    """通用时段检查 action

    检查当前时间是否已过指定小时，未到则跳过后续节点。
    通过 custom_action_param 传参，支持禁用检查（直接放行）。

    参数格式:
    {
        "hour": 16,              // 目标小时（0-23），默认16（下午4点）
        "enabled": true,         // 是否启用时段检查，false 时直接放行
        "skip_node": "节点名称"   // 未到时间时需要禁用的后续节点名
    }
    """

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        param = json.loads(argv.custom_action_param)
        hour = param.get("hour", 16)
        enabled = param.get("enabled", True)
        skip_node = param.get("skip_node")

        if not enabled:
            logger.info("时段检查已禁用，直接放行")
            return CustomAction.RunResult(success=True)

        if timelib.is_after_hour(hour):
            logger.info(f"当前已过{hour}点，执行后续流程")
            return CustomAction.RunResult(success=True)

        logger.info(f"当前未到{hour}点，跳过后续流程")
        if skip_node:
            context.override_pipeline({skip_node: {"enabled": False}})
        return CustomAction.RunResult(success=True)
