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