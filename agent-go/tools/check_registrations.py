# -*- coding: utf-8 -*-
"""校验 pipeline JSON 中引用的 custom_action / custom_recognition 是否都在 Go 注册名中。"""
import glob
import json
import os
import re
import sys

# Go 端已注册的名称(手工维护,与 register.go 各 RegisterXxx 一致)
GO_ACTIONS = {
    "新手_设置扫描间隔", "根据需要切换角色", "确保有队列可用", "NodeParaCombine",
    "DisableNode", "NodeOverride", "每日检查", "记录日期", "下午检查", "切换队伍",
    "撤回最后一个队伍", "开始是否识别角色ID", "识别角色ID", "设置怪兽次数", "开始出征",
    "野兽开始出征", "灯塔开始出征", "识别体力", "物品集结", "熊_无剩余队列",
    "熊_初始化参数", "熊_计算队伍", "熊_记录队伍", "熊_加入集结", "王城驻防_设置间隔",
    "王城驻防_选队出征", "加入集结_执行加入", "挖矿_设置等级", "挖矿_降级搜索",
    "挖掘宝藏", "米娅宝藏", "梦境寻忆_判断生效", "梦境寻忆", "联盟总动员_扫描",
    "游荡商人_钻石刷新", "神秘商店_购买", "联盟商店_购买",
}
GO_RECOGNITIONS = {
    "新手_不可能任务", "王城驻防_检测", "加入集结_识别队伍",
    "挖矿_去掉英雄识别", "挖矿_识别队伍", "挖矿_识别矿图标",
}


def collect_pipeline_refs(resource_dir):
    refs = {"action": set(), "recognition": set()}
    for path in glob.glob(os.path.join(resource_dir, "**", "*.json"), recursive=True):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print("SKIP %s: %s" % (path, e))
            continue
        if not isinstance(data, dict):
            continue
        for name, node in data.items():
            if not isinstance(node, dict):
                continue
            if "custom_action" in node:
                refs["action"].add(node["custom_action"])
            if "custom_recognition" in node:
                refs["recognition"].add(node["custom_recognition"])
            # all_of / sub 里的自定义识别
            for sub in node.get("all_of", []) or []:
                if isinstance(sub, dict) and "custom_recognition" in sub:
                    refs["recognition"].add(sub["custom_recognition"])
    return refs


def main():
    resource_dir = sys.argv[1] if len(sys.argv) > 1 else "assets/resource"
    refs = collect_pipeline_refs(resource_dir)
    print("pipeline 引用 custom_action:", sorted(refs["action"]))
    print("pipeline 引用 custom_recognition:", sorted(refs["recognition"]))

    missing_actions = refs["action"] - GO_ACTIONS
    missing_recogs = refs["recognition"] - GO_RECOGNITIONS
    extra_actions = GO_ACTIONS - refs["action"]
    extra_recogs = GO_RECOGNITIONS - refs["recognition"]

    ok = True
    if missing_actions:
        ok = False
        print("!! 缺少注册的 custom_action:", sorted(missing_actions))
    if missing_recogs:
        ok = False
        print("!! 缺少注册的 custom_recognition:", sorted(missing_recogs))
    if extra_actions:
        print("!! Go 注册但 pipeline 未引用:", sorted(extra_actions))
    if extra_recogs:
        print("!! Go 注册但 pipeline 未引用:", sorted(extra_recogs))
    print("RESULT:", "OK" if ok else "MISSING")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
