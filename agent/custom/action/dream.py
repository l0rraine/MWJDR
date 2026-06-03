import json
import random
import re
import time
import os
from datetime import datetime


from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from maa.pipeline import JRecognitionType, JOCR
from utils import logger
from utils.click_util import click_rect
from PIL import Image
from utils.merchant_utils import disable_switch
import importlib

EPISODE = "1"
@AgentServer.custom_action("梦境寻忆-判断生效")
class DreamEffective(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        global EPISODE
        json_data = json.loads(argv.custom_action_param)
        EPISODE = json_data.get("episode")
        all = context.get_node_data("梦境寻忆_开始闯关")["next"]
        if EPISODE == "0":
            max_str = max(
                all, key=lambda x: int(re.search(r"_(\d+)_", x).group(1))
            )
            for item in all:
                if f"梦境寻忆_{max_str}_" not in item:
                    disable_switch(context,item)

            all = context.get_node_data("梦境寻忆_组队")["next"]
            for item in all:
                if f"梦境寻忆_{max_str}_" not in item:
                    disable_switch(context, item)
        else:
            for item in all:
                if f"梦境寻忆_{EPISODE}_" not in item:
                    disable_switch(context,item)

            all = context.get_node_data("梦境寻忆_组队")["next"]
            for item in all:
                if f"梦境寻忆_{EPISODE}_" not in item:
                    disable_switch(context, item)
        return CustomAction.RunResult(success=False)

@AgentServer.custom_action("梦境寻忆")
class Memories(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        json_data = json.loads(argv.custom_action_param)
        mode = json_data.get('mode')

        level = json_data.get('level')
        logger.debug(f'当前模式:{mode},当前关卡:{level}')
        #  闯关模式
        if mode=='闯关':
            self.stage_mode(context,level)
        else:
            self.team_mode(context,level)
        return CustomAction.RunResult(success=True)

    def stage_mode(
        self,
        context: Context,
        level):
        global EPISODE
        module_name = f"action.dream.dream_{EPISODE}"
        item_dict={}
        try:
            # 动态导入模块
            mod = importlib.import_module(module_name)
            # 拼接函数名
            func_name = f"dream_{EPISODE}_stage"
            target_func = getattr(mod, func_name)
            # 调用函数
            item_dict = target_func(level)
        except ModuleNotFoundError:
            raise ValueError(f"不存在episode={EPISODE}对应的dream_{EPISODE}.py")
        except AttributeError:
            raise ValueError(f"dream_{EPISODE}.py 中无 {func_name} 函数")

        areas = [
            [40, 1135, 214, 72],
            [252, 1133, 215, 69],
            [467, 1133, 217, 71]
            ]

        detail = None
        expected=list(item_dict)
        done_dict={}
        miss_dict={}
        while detail is None or not detail.hit:
            for area in areas:
                img = context.tasker.controller.post_screencap().wait().get()
                d = context.run_recognition_direct(
                    JRecognitionType.OCR,
                    JOCR(expected=expected, roi=area, only_rec=False, threshold=0.8),
                    img,
                )

                if d.best_result is None:
                    continue 
                t = d.best_result.text
                if t not in item_dict:
                    if t not in done_dict:
                        if t not in miss_dict:
                            logger.info(f"缺失:{t}")
                        miss_dict[t] = 1
                    continue

                logger.debug(f"物品:{t}")
                click_rect(context, item_dict[t])
                done_dict[t]=item_dict.pop(t)
                time.sleep(0.5)     

            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("梦境寻忆_找到所有物品", img)
        logger.info(f"共点击{len(done_dict)}个物品")
        return CustomAction.RunResult(success=True)

    def team_mode(
        self,
        context: Context,
        level):
        global EPISODE
        module_name = f"action.dream.dream_{EPISODE}"
        item_dict = {}
        try:
            # 动态导入模块
            mod = importlib.import_module(module_name)
            # 拼接函数名
            func_name = f"dream_{EPISODE}_team"
            target_func = getattr(mod, func_name)
            # 调用函数
            item_dict = target_func(level)
        except ModuleNotFoundError:
            raise ValueError(f"不存在episode={EPISODE}对应的dream_{EPISODE}.py")
        except AttributeError:
            raise ValueError(f"dream_{EPISODE}.py 中无 {func_name} 函数")
        
        areas = [
            [68, 1120, 111, 58],
            [281, 1123, 160, 54],
            [508, 1121, 172, 61],
            [71, 1196, 124, 59],
            [297, 1200, 132, 53],
            [529, 1193, 133, 62]
            ]

        detail = None
        expected=list(item_dict)
        done_dict={}
        while detail is None or not detail.hit:
            for area in areas:
                img = context.tasker.controller.post_screencap().wait().get()
                d = context.run_recognition_direct(
                    JRecognitionType.OCR,
                    JOCR(expected=expected, roi=area, only_rec=True),
                    img,
                )

                if d.best_result is None:
                    continue 
                t = d.best_result.text
                if t not in item_dict:
                    if t not in done_dict:
                        logger.info(f"缺失:{t}")
                    continue

                logger.debug(f"物品:{t}")
                click_rect(context, item_dict[t])
                done_dict[t]=item_dict.pop(t)
                time.sleep(0.5)     

            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("梦境寻忆_找到所有物品", img)
        logger.info(f"共点击{len(done_dict)}个物品")
        return CustomAction.RunResult(success=True)

    def screen_shot(
        self,
        context: Context
        ):
        screen_array = context.tasker.controller.cached_image

        # Check resolution aspect ratio
        # height, width = screen_array.shape[:2]
        # aspect_ratio = width / height
        # target_ratio = 9 / 16
        # # Allow small deviation (within 1%)
        # if abs(aspect_ratio - target_ratio) / target_ratio > 0.01:
        #     logger.error(f"当前模拟器分辨率不是9:16! 当前分辨率: {width}x{height}")

        # BGR2RGB
        if len(screen_array.shape) == 3 and screen_array.shape[2] == 3:
            rgb_array = screen_array[:, :, ::-1]
        else:
            rgb_array = screen_array
            logger.warning("当前截图并非三通道")

        img = Image.fromarray(rgb_array)

        save_dir = "temp"
        os.makedirs(save_dir, exist_ok=True)
        now = datetime.now()
        img.save(f"{save_dir}/{self._get_format_timestamp(now)}.png")
        logger.debug(f"截图保存至 {save_dir}/{self._get_format_timestamp(now)}.png")

    def _get_format_timestamp(self, now):

        date = now.strftime("%Y.%m.%d")
        time = now.strftime("%H.%M.%S")
        milliseconds = f"{now.microsecond // 1000:03d}"

        return f"{date}-{time}.{milliseconds}"
