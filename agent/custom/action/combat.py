from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time



@AgentServer.custom_action("切换队伍")
class ChangeTeam(CustomAction):

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        team_roi = [
            [0,0,0,0],
            [56,117,22,15],
            [127,115,26,23],
            [204,113,16,25],
            [270,113,35,26],
            [349,117,22,22],
            [416,112,23,32],
            [494,113,30,28],
            [565,113,30,29]
        ]
        json_data = json.loads(argv.custom_action_param)
        team_index = int(json_data.get('队伍序号'))
        if team_index != 0:
            context.run_task("custom", {
            "custom": {
                "target": team_roi[team_index],
                "action": "Click",
            }
        })
        return True


@AgentServer.custom_action("调整巨兽等级")
class ChangeMonsterLevel(CustomAction):

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        return True

@AgentServer.custom_action("自动集结_怪物分支")
class ChooseMonster(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        jina = int(param.get("巨兽种类"))
        if jina == 1:
            print("开始吉娜")
            context.run_task("自动集结_吉娜入口")
        if jina == 0:
            print("开始冰原巨兽")
            context.run_task("自动集结_巨兽入口")
        return True
@AgentServer.custom_action("开始出征")
class BeginCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        print("出征参数：",param)        
        # TODO:智能化
        #if combat_times == 0:
        #    return True
        
        # 获取返回时间
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("识别集结时间", img)
        # print("time:",detail)
        hours, minutes, seconds = map(int, detail.best_result.text.split(':'))
        return_time = hours * 3600 + minutes * 60 + seconds
        
        # 开始出征
        context.run_task("点击出征")
        time.sleep(0.5)
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("体力不足", img)
        if detail is not None:
            context.run_task("免费体力")
            context.run_task("点击出征")
            img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("自动集结_集结中", img)
        # print(f'detail: {detail}')
        if detail is not None and detail.box:
                # print(f'detail box: {detail.box}')
                # print(f'x,y:{6 + detail.box.x + 195},{detail.box.y}')
                context.tasker.controller.post_click(
                    6 + detail.box.x + 195, detail.box.y
                    
                ).wait()
                
                detail = None
                while detail is None:
                    time.sleep(1)
                    img = context.tasker.controller.post_screencap().wait().get()
                    detail = context.run_recognition("自动集结_行军中",img)
                context.run_task("后退")
                time.sleep(return_time*2 + 2)
                jina =param.get("巨兽种类")
                print("jina=",jina)
                context.run_task("自动集结入口",{
                    "自动集结入口":{
                        "custom_action_param": {
                        "巨兽种类": jina
                    }
                    }
                    
                })
                return True
        return True
    
@AgentServer.custom_action("灯塔开始出征")
class LightBeginCombat(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        json_data = json.loads(argv.custom_action_param)
        print(json_data)        
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("识别集结时间", img)
        print("time:",detail.best_result.text)
        hours, minutes, seconds = map(int, detail.best_result.text.split(':'))
        return_time = hours * 3600 + minutes * 60 + seconds
        
        # 开始出征
        context.run_task("点击出征")
        img = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("体力不足", img)
        if detail is not None:
            context.run_task("免费体力")
            context.run_task("点击出征")
        time.sleep(return_time*2 + 2)
        context.run_task("灯塔入口")        
        return True
    
    
@AgentServer.custom_action("撤回最后一个队伍")
class RecallTeam(CustomAction):

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        team_roi = [
            [0,0,0,0], 
            [200,552,45,45],
            [200,488,45,45],
            [200,427,45,45],
            [200,371,45,45],
            [200,313,45,45],
            [200,246,45,45]
            
        ]
        json_data = json.loads(argv.custom_action_param)
        team_index = int(json_data.get('队伍序号'))
        if team_index != 0:
            context.run_task("custom", {
            "custom": {
                "target": team_roi[team_index],
                "action": "Click",
            }
        })
        return True