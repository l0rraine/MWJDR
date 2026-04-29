from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JActionType, JClick
import json
import time
from utils import logger
from utils import timelib

@AgentServer.custom_action("联盟总动员_扫描")
class UniteScan(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        left_slot = context.get_node_data("联盟总动员_参数_是否启用第一栏位")["enabled"]
        right_slot = context.get_node_data("联盟总动员_参数_是否启用第二栏位")["enabled"]
        
        slot_list = []
        if left_slot:
            slot_list.append(0)
        if right_slot:
            slot_list.append(1)
        
        logger.debug(f"栏位启用状态：左={left_slot}, 右={right_slot}")
               
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
        img = context.tasker.controller.post_screencap().wait().get()            
        detail = context.run_recognition("联盟总动员_巴尔德", img)
        if detail.hit:
            logger.debug("发现巴尔德，修正坐标")
            rate_roi[0][1] += 60
            rate_roi[1][1] += 60
            time_roi[0][1] += 60
            time_roi[1][1] += 60
            running_roi[0][1] += 60
            running_roi[1][1] += 60
        
        need_wait_seconds = [86400,86400]
        for i in slot_list:
            
            logger.debug(f"正在识别{i+1}号位置")
            img = context.tasker.controller.post_screencap().wait().get()
            
            detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})

            if detail.hit:
                hours, minutes, seconds = timelib.split_time_str(detail.best_result.text)
                need_wait_seconds[i] = hours * 3600 + minutes * 60 + seconds
                
                # 大于5分钟说明是这个位置任务已做完，用于后面的判断
                need_wait_seconds[i] = 86400 if need_wait_seconds[i] > 300 else need_wait_seconds[i]
                    
                logger.debug(f"{i+1}号位置需要等待{need_wait_seconds[i]}秒")
                continue
            
            detail = context.run_recognition("联盟总动员_正在执行", img, {
                "联盟总动员_正在执行": {"roi": running_roi[i]}
                })
            if detail.hit:
                need_wait_seconds[i] = 86400
                logger.debug(f"{i+1}号位置正在执行")
                continue

            refresh = 0
            matched = ''
            
            detail = context.run_recognition("联盟总动员_识别200%倍率", img, {
                    "联盟总动员_识别200%倍率": {"roi": rate_roi[i]}
                    })
                
            if not detail.hit:
                rate = "120%"
            else:
                rate = "200%"    
            
            # 确保接下来处于任务详情页面
            context.run_action_direct(
                JActionType.Click,
                JClick(target=time_roi[i]),
            )
            
            all = context.get_node_data("联盟总动员_点击详情")["next"]
            
            name_list = [item['name'] for item in all]
            need = [d["recognition"]["param"]["expected"] for item in name_list if (d := context.get_node_data(item))["enabled"]]
            flattened = [item for sublist in need for item in sublist]
            if not flattened:
                refresh = 1
            else:
                img = context.tasker.controller.post_screencap().wait().get()                
                detail = context.run_recognition("联盟总动员_识别描述", img, {"联盟总动员_识别描述": {
                        "expected": flattened         
                }
                })
                if not detail.hit:
                    refresh = 1
                else:
                    matched = detail.best_result.text
                    need_wait_seconds[i] = 86400
                        
            if refresh == 1:
                logger.debug(f"开始刷新位置{i+1}")
                context.run_task("联盟总动员_开始刷新")
                detail = None
                while detail is None or not detail.hit:
                    img = context.tasker.controller.post_screencap().wait().get()
                    detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})
                    time.sleep(1)
                _, minutes, seconds = timelib.split_time_str(detail.best_result.text)
                need_wait_seconds[i] = minutes * 60 + seconds
                
                logger.debug(f"{i+1}号位置需要等待：{minutes}:{seconds},共计{need_wait_seconds[i]}秒")
            else:
                prefix=f"{i+1}号位置"
                logger.info(f"{prefix}已刷新出{matched}，倍率{rate}")
                context.run_task("点击左上角")
            
        
        if min(need_wait_seconds) != 86400:
                logger.debug(f"开始等待{min(need_wait_seconds)}秒")
                time.sleep(min(need_wait_seconds))
                return CustomAction.RunResult(success=True)
        else:
            logger.info(f"已全部得到满意的结果，停止刷新")
            return CustomAction.RunResult(success=False)
