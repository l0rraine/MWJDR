from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time
from utils import logger
import re

@AgentServer.custom_action("联盟总动员_扫描")
class UniteScan(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        just_double = (int)(param.get('just_double'))
    
        quest_roi = [
            [138,656,115,85],
            [472,666,106,71]
        ]
        rate_roi = [
            [27,577,113,120],
            [346,576,108,113]
        ]  
        time_roi = [
            [161,652,123,82],
            [483,648,115,79]
            
        ]
        running_roi = [
            [71,803,32,21],
            [394,803,32,21]
        ]
        need_wait_seconds = [3600,3600]
        for i in range(0,2):
            img = context.tasker.controller.post_screencap().wait().get()
            
            detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})
            if detail is not None:
                parts = re.split(r'\D+', detail.best_result.text)
                numeric_parts = [int(part) for part in parts if part]
                hours, minutes, seconds = (numeric_parts + [None, None, None])[:3]
                need_wait_seconds[i] = hours * 3600 + minutes * 60 + seconds
                logger.debug(f"{i+1}号位置需要等待{need_wait_seconds[i]}秒")
                continue
            
            detail = context.run_recognition("联盟总动员_正在执行", img, {
                "联盟总动员_正在执行": {"roi": running_roi[i]}
                })
            if detail is not None:
                need_wait_seconds[i] = 3600
                logger.debug(f"{i+1}号位置正在执行")
                continue

            refresh = 0
            matched = ''
            detail = context.run_recognition("联盟总动员_识别倍率", img, {
                "联盟总动员_识别倍率": {"roi": rate_roi[i]}
                })
            logger.debug(f"识别倍率：{detail.best_result.text}")
            
            # 确保接下来处于任务详情页面
            context.run_task("点击",{
                    "点击":{
                        "action": "Click",
                        "target": time_roi[i],
                    }
                })
            
            if just_double == 1:                
                if detail is not None and detail.best_result.text != '200%':
                    logger.debug(f"识别出倍率{detail.best_result.text}")
                    refresh = 1
                        
            else:
                all = context.get_node_data("联盟总动员_点击详情")["interrupt"]
                filtered = [s for s in all if detail.best_result.text in s]
                need = [d["recognition"]["param"]["expected"][0] for item in filtered if (d := context.get_node_data(item))["enabled"]]                    
                
                img = context.tasker.controller.post_screencap().wait().get()                
                detail = context.run_recognition("联盟总动员_识别描述", img, {"联盟总动员_识别描述": {
                        "expected": need         
                }
                })
                if detail is None:
                    refresh = 1
                else:
                    matched = detail.best_result.text
            if refresh == 1:
                logger.debug(f"开始刷新位置{i+1}")
                context.run_task("联盟总动员_开始刷新")
                img = context.tasker.controller.post_screencap().wait().get()
                detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})
                if detail is not None:
                    hours, minutes, seconds = map(int, detail.best_result.text.split(':'))
                    need_wait_seconds[i] = hours * 3600 + minutes * 60 + seconds
                    logger.debug(f"{i+1}号位置需要等待：{minutes}:{seconds},共计{need_wait_seconds[i]}秒")
            else:
                logger.info(f"{i+1}号位置刷新出双倍！" if just_double == 1 else f"{i+1}号位置已刷新出{matched}")
                context.run_task("点击左上角")
                        
        
        if min(need_wait_seconds) != 3600:
            logger.debug(f"开始等待{min(need_wait_seconds)}秒")
            time.sleep(min(need_wait_seconds))
            context.run_task("联盟总动员_入口",{
                    "联盟总动员_入口":{
                        "custom_action_param": {
                        "just_double": just_double
                        
                    }
                    }
                    
                })
                
        return CustomAction.RunResult(success=True)