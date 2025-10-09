from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time

from utils import logger
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
        img = context.tasker.controller.post_screencap().wait().get()
        expected = f"王国：#{region}"
        
        cha_detail = None        
        count = 3
        while count > 0 and cha_detail is None:
            try:
                region_detail = context.run_recognition(
                    "国度信息",
                    img,
                    {"国度信息": {"expected": expected}},
                )
                cha_detail = context.run_recognition(
                    "选中角色",
                    img,
                    {"选中角色":{"roi":[region_detail.box.x+402,region_detail.box.y+70,119,231]}}
                )
                logger.debugger(cha_detail.box.y-region_detail.box.y<170)
            except Exception as e:
                print(f"第 {4 - count} 次执行出错: {e}")
                time.sleep(2)
            finally:                
                count -= 1
        
        if index=="1" and cha_detail.box.y-region_detail.box.y>170:
            context.run_task(
                "点击角色",
                {"点击角色":
                    {"target":[cha_detail.box.x,cha_detail.box.y-170,cha_detail.box.w,cha_detail.box.h]}
                })
        if index=="2" and cha_detail.box.y-region_detail.box.y<170:
            context.run_task(
                "点击角色",
                {"点击角色":
                    {"target":[cha_detail.box.x,cha_detail.box.y+170,cha_detail.box.w,cha_detail.box.h]}
                })
        logger.debug(f"SwitchCharacter:{json_data}")
        return CustomAction.RunResult(success=True)

# 确保所有任务执行前有队列可用，1. 关闭自动加入 2.如果有不是挖矿的队伍，等待  3. 如果全部在挖矿，召回最后一队
@AgentServer.custom_action("确保有队列可用")
class MakeSureQueueAvailable(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        # 1. 关闭自动加入
        logger.debug("关闭自动加入集结")
        context.run_task("自动加入集结_关闭_入口")  
        context.run_task("转到城外") 
        context.run_task("开始查看队列")
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("当前队列已满", img)
        img = context.tasker.controller.post_screencap().wait().get()
        if detail is not None:
            context.run_task("后退")
            _, b = map(int, detail.best_result.text.split('/'))
            
            logger.info("当前队列已满")
            # 2.如果有不是挖矿的队伍，等待 
            action_region = [
                [56,546,96,28],
                [56,486,96,28],
                [56,426,96,28],
                [56,366,96,28],
                [56,306,96,28],
                [56,246,96,28],
            ]
            flag = 0
            for region in action_region[-b:]:
                detail = context.run_recognition("识别队列动作", img, {
                    "识别队列动作":{
                        "roi": region
                    }
                })
                if detail is not None:
                    flag = 1
                    break
            if flag==1:
                logger.info("开始等待出征队伍回归")
                context.run_task("开始查看队列")
            while flag == 1:
                time.sleep(3)
                img = context.tasker.controller.post_screencap().wait().get()
                detail = context.run_recognition("当前队列已满", img)
                if detail is None:
                    break
            
            # 3. 如果全部在挖矿，召回最后一队
            if flag == 0:
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
                    context.run_task("点击召回",{
                        "点击召回": {
                            "target": region
                        }
                    })
                    break
                logger.info("已取消挖矿队伍，开始等待")
                context.run_task("开始查看队列")
                while True:
                    time.sleep(3)
                    img = context.tasker.controller.post_screencap().wait().get()
                    detail = context.run_recognition("当前队列已满", img)
                    if detail is None:
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