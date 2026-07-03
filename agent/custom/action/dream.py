import json
import random
import re
import time
import os
from datetime import datetime


from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from maa.pipeline import JActionType, JClick, JRecognitionType, JOCR
from utils import logger
from utils.click_util import click_rect
from PIL import Image
from utils.merchant_utils import disable_switch
import importlib

EPISODE = "1"


@AgentServer.custom_action("梦境寻忆_判断生效")
class DreamEffective(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        global EPISODE
        json_data = json.loads(argv.custom_action_param)
        EPISODE = json_data.get("episode")
        is_stage = context.get_node_data("梦境寻忆_闯关").get("enabled", False)

        if is_stage:
            all = context.get_node_data("梦境寻忆_开始闯关")["next"]
            name_list = [item["name"] for item in all]
        else:
            all = context.get_node_data("梦境寻忆_组队")["next"]
            name_list = [item["name"] for item in all]
        if EPISODE == "0":
            max_str = max(name_list, key=lambda d: int(d.split("_")[1]))
            EPISODE = int(max_str.split("_")[1])
            logger.debug(f"当前最新阶段: {EPISODE}")
            for item in name_list:
                if max_str != item:
                    disable_switch(context, item)
        else:
            logger.debug(f"当前选择阶段: {EPISODE}")
            for item in name_list:
                if f"梦境寻忆_{EPISODE}_" not in item:
                    disable_switch(context, item)

        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("梦境寻忆")
class Memories(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        json_data = json.loads(argv.custom_action_param)
        mode = json_data.get("mode")
        level = json_data.get("level")
        logger.debug(f"当前模式:{mode},当前关卡:{level}")
        self.screen_shot(context, level)
        #  闯关模式
        if mode == "闯关":
            self.stage_mode(context, level)
        else:
            self.team_mode(context, level)
        return CustomAction.RunResult(success=True)

    def stage_mode(self, context: Context, level):
        global EPISODE
        module_name = f"custom.action.dream_stages.dream_{EPISODE}"
        item_dict = {}
        try:
            # 动态导入模块
            mod = importlib.import_module(module_name)
            # 拼接函数名
            func_name = f"dream_stage"
            target_func = getattr(mod, func_name)
            # 调用函数
            item_dict = target_func(level)
        except ModuleNotFoundError:
            raise ValueError(f"不存在episode={EPISODE}对应的dream_{EPISODE}.py")
        except AttributeError:
            raise ValueError(f"dream_{EPISODE}.py 中无 {func_name} 函数")

        areas = [[40, 1135, 214, 72], [252, 1133, 215, 69], [467, 1133, 217, 71]]

        detail = None
        expected = list(item_dict)
        done_dict = {}
        miss_dict = {}
        while detail is None or not detail.hit:
            for area in areas:
                img = context.tasker.controller.post_screencap().wait().get()
                d = context.run_recognition_direct(
                    JRecognitionType.OCR,
                    JOCR(roi=area, only_rec=True),
                    img,
                )
                if not d.filtered_results:
                    continue

                # 三段式匹配：先完全匹配，再包含匹配，最后缺失打印
                texts = [r.text.strip().capitalize() for r in d.filtered_results]
                # 1. 完全匹配（abc == key）
                match = next(
                    (key for key in item_dict if any(t == key for t in texts)),
                    None,
                )
                # 2. 包含匹配（key in abc）
                if not match:
                    match = next(
                        (key for key in item_dict if any(key in t for t in texts)),
                        None,
                    )
                if match:
                    logger.debug(f"找到:{match}")
                    click_rect(context, item_dict[match])
                    done_dict[match] = item_dict.pop(match)
                else:
                    # 3. 缺失打印：取 score 最高的 t，检查是否之前已匹配过
                    t = max(d.filtered_results, key=lambda r: r.score)
                    t = t.text.strip().capitalize()
                    already_found = any(key in t for key in done_dict)
                    if not already_found:
                        if t not in miss_dict:
                            logger.info(f"缺失:{t}")
                        miss_dict[t] = miss_dict.get(t, 0) + 1
                time.sleep(0.5)

            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("梦境寻忆_找到所有物品", img)
        logger.info(f"共点击{len(done_dict)}个物品")
        # detail.best_result.box 是 Rect 对象，转为 list 供 JClick 使用
        box = detail.best_result.box
        click_target = [box.x, box.y, box.w, box.h] if hasattr(box, "x") else list(box)
        context.run_action_direct(
            JActionType.Click,
            JClick(target=click_target),
        )

    def team_mode(self, context: Context, level):
        global EPISODE
        module_name = f"custom.action.dream_stages.dream_{EPISODE}"
        item_dict = {}
        try:
            # 动态导入模块
            mod = importlib.import_module(module_name)
            # 拼接函数名
            func_name = f"dream_team"
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
            [529, 1193, 133, 62],
        ]

        detail = None
        expected = list(item_dict)
        done_dict = {}
        miss_dict = {}
        while detail is None or not detail.hit:
            for area in areas:
                img = context.tasker.controller.post_screencap().wait().get()
                d = context.run_recognition_direct(
                    JRecognitionType.OCR,
                    JOCR(roi=area, only_rec=True),
                    img,
                )
                if not d.filtered_results:
                    continue
                # 三段式匹配：先完全匹配，再包含匹配，最后缺失打印
                texts = [r.text.strip().capitalize() for r in d.filtered_results]
                # 1. 完全匹配（abc == key）
                match = next(
                    (key for key in item_dict if any(t == key for t in texts)),
                    None,
                )
                # 2. 包含匹配（key in abc）
                if not match:
                    match = next(
                        (key for key in item_dict if any(key in t for t in texts)),
                        None,
                    )
                if match:
                    logger.debug(f"找到:{match}")
                    click_rect(context, item_dict[match])
                    done_dict[match] = item_dict.pop(match)
                else:
                    # 3. 缺失打印：取 score 最高的 t，检查是否之前已匹配过
                    t = max(d.filtered_results, key=lambda r: r.score)
                    t = t.text.strip().capitalize()
                    already_found = any(key in t for key in done_dict)
                    if not already_found:
                        if t not in miss_dict:
                            logger.info(f"缺失:{t}")
                        miss_dict[t] = miss_dict.get(t, 0) + 1
                time.sleep(0.5)

            img = context.tasker.controller.post_screencap().wait().get()
            detail = context.run_recognition("梦境寻忆_找到所有物品", img)
        logger.info(f"共点击{len(done_dict)}个物品")

    def screen_shot(self, context: Context, text: str):
        screen_array = context.tasker.controller.post_screencap().wait().get()

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

        save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "temp")
        os.makedirs(save_dir, exist_ok=True)
        now = datetime.now()
        text = re.sub(r"[*?]", "", text)
        name = (
            f"{text}_"
            + now.strftime("%Y%m%d%H%M%S.")
            + f"{now.microsecond // 1000:03d}.png"
        )
        img.save(os.path.join(save_dir, name))
        logger.debug(f"截图保存至 temp/{name}")
