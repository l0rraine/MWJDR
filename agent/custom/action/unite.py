from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time
from utils import logger

@AgentServer.custom_action("联盟总动员_扫描")
class UniteScan(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        scores = param.get('wanted_scores')
        number_strings = scores.split(',')
        logger.debug(f"想要的分数：{number_strings}")
    
        # 处理每个数字字符串：去除空格并转换为整数
        wanted_scores = []
        for num_str in number_strings:
            # 去除每个数字字符串前后的空格
            cleaned_str = num_str.strip()
            # 跳过可能的空字符串（如输入为 ",,1,2," 时产生的空值）
            if cleaned_str:
                # 转换为整数并添加到结果列表
                wanted_scores.append(cleaned_str)   
        score_roi = [
            [98,730,226,149],
            [459,733,181,143]
        ]
        time_roi = [
            [65,594,289,191],
            [394,606,262,170]
            
        ]
        need_wait_seconds = [0,0]
        img = context.tasker.controller.post_screencap().wait().get()
        for i in range(0,2):
            detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})
            if detail is not None:
                hours, minutes, seconds = map(int, detail.best_result.text.split(':'))
                need_wait_seconds[i] = hours * 3600 + minutes * 60 + seconds
                logger.debug(f"{i+1}号位置需要等待：{minutes}:{seconds},共计{need_wait_seconds[i]}秒")
            else:
                detail = context.run_recognition("联盟总动员_识别分数", img, {"联盟总动员_识别分数": {"exptected": score_roi[i]}})
                if detail is not None:
                    score = detail.best_result.text.lstrip("+")
                    logger.debug(f"识别到分数：{score}")
                    if score not in wanted_scores:
                        logger.debug(f"开始刷新位置{i+1}")
                        context.run_task("custom",{
                            "custom":{
                                "action": "Click",
                                "target": time_roi[i],
                                "next": "联盟总动员_开始刷新"
                            }
                        })
                        img = context.tasker.controller.post_screencap().wait().get()
                        detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})
                        if detail is not None:
                            hours, minutes, seconds = map(int, detail.best_result.text.split(':'))
                            need_wait_seconds[i] = hours * 3600 + minutes * 60 + seconds
                            logger.debug(f"{i+1}号位置需要等待：{minutes}:{seconds},共计{need_wait_seconds[i]}秒")
        
        if min(need_wait_seconds) != 3600:
            logger.debug(f"开始等待{min(need_wait_seconds)}秒")
            time.sleep(min(need_wait_seconds))
            context.run_task("联盟总动员_入口",{
                    "联盟总动员_入口":{
                        "custom_action_param": {
                        "wanted_scores": scores
                    }
                    }
                    
                })
                
        return CustomAction.RunResult(success=True)