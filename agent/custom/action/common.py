from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time

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
        #print("char info:",region,index)
        img = context.tasker.controller.post_screencap().wait().get()
        expected = f"王国：#{region}"
        region_detail = context.run_recognition(
                    "国度信息",
                    img,
                    {"国度信息": {"expected": expected}},
                )
        #print("region_detail:",region_detail)
        #print("cha_roi:",[region_detail.box.x+374,region_detail.box.y+70,119,231])
        cha_detail = context.run_recognition(
            "选中角色",
            img,
            {"选中角色":{"roi":[region_detail.box.x+374,region_detail.box.y+70,119,231]}})
        #print("cha_detail:",cha_detail)
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
        print("SwitchCharacter:", json_data)
        return CustomAction.RunResult(success=True)

# 确保所有任务执行前有队列可用，1. 关闭自动加入 2.如果有不是挖矿的队伍，等待  3. 如果全部在挖矿，召回最后一队
@AgentServer.custom_action("确保有队列可用")
class MakeSureQueueAvailable(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        # 总区域 "roi" : [11,196,230,409]
        # 1. 关闭自动加入
        print("closing auto join")
        context.run_task("关闭自动加入集结入口")
        context.run_task("转到城外")
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("当前队列已满", img)
        if detail is not None:
            a, b = map(int, detail.best_result.text.split('/'))
            print("cancel a queue")
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
            print("current queue flag:", flag)
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
                print("recalled mine queue, waiting")
                while True:
                    time.sleep(3)
                    img = context.tasker.controller.post_screencap().wait().get()
                    detail = context.run_recognition("当前队列已满", img)
                    if detail is None:
                        break

        
        return CustomAction.RunResult(success=True)