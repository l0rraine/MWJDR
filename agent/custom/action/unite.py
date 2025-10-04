from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
import random
import time
from utils import logger
from utils import timelib
from utils.chainfo import ChaInfo
@AgentServer.custom_action("联盟总动员_扫描")
class UniteScan(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        param = json.loads(argv.custom_action_param)
        just_double = (int)(param.get('just_double'))
        current_cha_index = str(param.get('current_cha_index','0')) 
        
        
        
        only_1_charater = context.get_node_data("联盟总动员_参数_是否单角色")["enabled"]
        left_slot = context.get_node_data("联盟总动员_参数_是否启用第一栏位")["enabled"]
        right_slot = context.get_node_data("联盟总动员_参数_是否启用第二栏位")["enabled"]
        
        slot_list = []
        if left_slot:
            slot_list.append(0)
        if right_slot:
            slot_list.append(1)
        
        logger.debug(f"参数为：{only_1_charater},{left_slot},{right_slot}")
                
        char_data = context.get_node_data("确定角色")["action"]["param"]["custom_action_param"]
        
        main_cha_index = char_data["王国内序号"]
        kingdom = char_data["王国编号"] or "3194"
        
        current_cha_index = main_cha_index if current_cha_index == '0' else current_cha_index
        
        ChaInfo.init({f"{kingdom}":{current_cha_index:{"slot1":time.time()+86400,"slot2":time.time()+86400}}})
        
        logger.debug(ChaInfo.get_char_data())
        
        logger.debug(f"当前角色：{current_cha_index}")
               
        
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
        need_wait_seconds = [86400,86400]
        for i in slot_list:
            
            logger.debug(f"正在识别{i+1}号位置")
            img = context.tasker.controller.post_screencap().wait().get()
            
            detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})
            if detail is not None:
                hours, minutes, seconds = timelib.split_time_str(detail.best_result.text)
                need_wait_seconds[i] = hours * 3600 + minutes * 60 + seconds
                ChaInfo.set_char_data(kingdom,current_cha_index,{f"slot{i+1}": time.time()+need_wait_seconds[i]})
                logger.debug(f"{i+1}号位置需要等待{need_wait_seconds[i]}秒")
                # logger.debug(f"当前信息：{ChaInfo.get_char_data(kingdom)}")
                continue
            
            detail = context.run_recognition("联盟总动员_正在执行", img, {
                "联盟总动员_正在执行": {"roi": running_roi[i]}
                })
            if detail is not None:
                need_wait_seconds[i] = 86400
                ChaInfo.set_char_data(kingdom,current_cha_index,{f"slot{i+1}": time.time()+need_wait_seconds[i]})
                logger.debug(f"{i+1}号位置正在执行")
                # logger.debug(f"当前信息：{ChaInfo.get_char_data(kingdom)}")
                continue

            refresh = 0
            matched = ''
            
            detail = context.run_recognition("联盟总动员_识别200%倍率", img, {
                    "联盟总动员_识别200%倍率": {"roi": rate_roi[i]}
                    })
                
                
            
            # 确保接下来处于任务详情页面
            context.run_task("点击",{
                    "点击":{
                        "action": "Click",
                        "target": time_roi[i],
                    }
                })
            if detail is None:
                rate = "120%"
            else:
                rate = "200%"
            
            if just_double == 1:
                logger.debug(f"识别出{rate}倍率")              
                if detail is None: 
                    refresh = 1
                else:
                    ChaInfo.set_char_data(kingdom,current_cha_index,{f"slot{i+1}": time.time()+68400}) 
                        
            else:
                all = context.get_node_data("联盟总动员_点击详情")["interrupt"]
                
                filtered = [s for s in all if rate in s]
                need = [d["recognition"]["param"]["expected"] for item in filtered if (d := context.get_node_data(item))["enabled"]]
                flattened = [item for sublist in need for item in sublist]

                if not flattened:
                    refresh = 1
                else:
                    img = context.tasker.controller.post_screencap().wait().get()                
                    detail = context.run_recognition("联盟总动员_识别描述", img, {"联盟总动员_识别描述": {
                            "expected": flattened         
                    }
                    })
                    if detail is None:
                        refresh = 1
                    else:
                        matched = detail.best_result.text
                        ChaInfo.set_char_data(kingdom,current_cha_index,{f"slot{i+1}": time.time()+68400})
            if refresh == 1:
                logger.debug(f"开始刷新位置{i+1}")
                context.run_task("联盟总动员_开始刷新")
                img = context.tasker.controller.post_screencap().wait().get()
                detail = context.run_recognition("联盟总动员_识别时间", img, {"联盟总动员_识别时间": {"roi": time_roi[i]}})
                if detail is not None:
                    hours, minutes, seconds = map(int, detail.best_result.text.split(':'))
                    need_wait_seconds[i] = hours * 3600 + minutes * 60 + seconds
                    ChaInfo.set_char_data(kingdom,current_cha_index,{f"slot{i+1}": time.time()+need_wait_seconds[i]})
                    logger.debug(f"{i+1}号位置需要等待：{minutes}:{seconds},共计{need_wait_seconds[i]}秒")
            else:
                prefix=f"{current_cha_index}号在位置{i+1}"
                logger.info(f"{prefix}刷新出双倍！" if just_double == 1 else f"{prefix}已刷新出{matched}，倍率{rate}")
                context.run_task("点击左上角")
            
        
        # logger.debug(f"当前信息：{ChaInfo.get_char_data(kingdom)}")        
            
            
        if not only_1_charater:    
            next_char = self.find_next_char(ChaInfo.get_char_data(kingdom))
        else:
            next_char = current_cha_index
            
        if next_char == current_cha_index:
            # 当前用户处理完毕后不需要处理下个角色，有可能
            # 1. 当前是单用户模式
            # 2. 另外一个用户的刷新时间大于当前用户的
            
            # 如果2个等待时间不都是一天，那继续等待即可
            if min(need_wait_seconds) != 86400:
                logger.debug(f"开始等待{min(need_wait_seconds)}秒")
                time.sleep(min(need_wait_seconds))
                context.run_task("联盟总动员_入口",{
                        "联盟总动员_入口":{
                            "custom_action_param": {
                            "just_double": just_double,
                            "current_cha_index": next_char
                            
                        }
                        }
                        
                    })
            else:
                logger.info(f"已全部得到2个满意的结果，停止刷新")
        else:
            # 当前用户处理完毕后继续处理下个角色，需要切换角色的操作
            
            # 当前用户已经得到2个满意的结果则打开单角色选项
            if min(need_wait_seconds) == 86400:
                context.override_pipeline({
                "联盟总动员_参数_是否单角色": {
                            "enabled": True
                        }
                })
                logger.info(f"{current_cha_index}号已得到2个满意的结果，停止刷新，切换至{next_char}")
            
            # 切换到下一个角色进行处理
            context.override_pipeline({
                            "确定角色": {
                                "custom_action_param": {
                                    "王国内序号": next_char,
                                    "王国编号": kingdom
                                }
                            }
                        })
            context.override_pipeline({
                            "联盟总动员_开始扫描": {
                                "custom_action_param": {
                                "just_double": just_double,
                                "current_cha_index": next_char
                                
                            }
                            }
                        })
            context.override_next("确定角色",["联盟总动员_入口"])
            context.run_task("启动游戏")
                
        return CustomAction.RunResult(success=True)
    
    def find_next_char(self, data):
        for item in ("1","2"):
            if item not in data:
                return item
        # 存储最小值信息：(值, 父键列表, slot名称)
        min_info = []        
        for key, item in data.items():
            # 检查当前层级是否有slot1和slot2
            for slot_name in ["slot1", "slot2"]:
                if slot_name not in item:
                    return key
                else:
                    # 记录值和完整父键路径
                    value = item[slot_name]
                    min_info.append( (value, key, slot_name) )
        
        # 找到最小值
        min_value = min(item[0] for item in min_info)
        
        result = next(item[1] for item in min_info if item[0] == min_value)       
        
        return result
