# -*- coding: utf-8 -*-
"""将 Python 版 dream_stages/*.py 的关卡数据转换为 Go 数据文件。

用法: python convert_dream.py <agent根目录> <输出文件>
"""
import ast
import glob
import os
import sys


def match_case_level(pattern):
    """提取 match case 的模式常量(如 MatchValue('盾兵营')),失败返回 None"""
    if isinstance(pattern, ast.MatchValue) and isinstance(pattern.value, ast.Constant):
        return str(pattern.value.value)
    if isinstance(pattern, ast.MatchAs) and pattern.pattern is not None:
        return match_case_level(pattern.pattern)
    return None


def extract_funcs(path):
    """返回 {func_name: {level: {item: rect}}}

    兼容两种函数体结构:
      - match level: case 'X': item_dict = {...} ... return item_dict
      - if level == 'X': return {...}
    """
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    result = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in ('dream_stage', 'dream_team'):
            continue
        func_name = node.name
        level_map = {}

        def add_level(level, value):
            if not isinstance(value, ast.Dict):
                return
            items = {}
            for ik, iv in zip(value.keys, value.values):
                if not isinstance(ik, ast.Constant):
                    continue
                try:
                    rect = ast.literal_eval(iv)
                except Exception:
                    continue
                items[str(ik.value)] = [int(v) for v in rect]
            if items:
                level_map[level] = items

        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    level = match_case_level(case.pattern)
                    if level is None:
                        continue
                    for body_stmt in case.body:
                        if isinstance(body_stmt, ast.Assign) and \
                                isinstance(body_stmt.value, ast.Dict):
                            add_level(level, body_stmt.value)
            elif isinstance(stmt, ast.If):
                # if level == 'X': return {...} / item_dict = {...}
                if isinstance(stmt.test, ast.Compare) and len(stmt.test.comparators) == 1:
                    left = stmt.test.left
                    right = stmt.test.comparators[0]
                    if isinstance(left, ast.Name) and left.id == 'level' and \
                            isinstance(right, ast.Constant):
                        for body_stmt in stmt.body:
                            if isinstance(body_stmt, ast.Return):
                                add_level(str(right.value), body_stmt.value)
                            elif isinstance(body_stmt, ast.Assign) and \
                                    isinstance(body_stmt.value, ast.Dict):
                                add_level(str(right.value), body_stmt.value)
        if level_map:
            result[func_name] = level_map
    return result


def gen(items_ordered):
    """items_ordered: [(episode, func_name, level, [(item, rect), ...])] -> Go 源码片段

    输出两层 map: episode -> level -> []dreamItem(func 维度已由调用方拆分)
    """
    lines = []
    current_episode = None
    for ep, _func, level, items in items_ordered:
        if current_episode is None:
            lines.append('\t"%s": {' % ep)
            current_episode = ep
        elif ep != current_episode:
            lines.append('\t},')
            lines.append('\t"%s": {' % ep)
            current_episode = ep
        lines.append('\t\t"%s": {' % level)
        for item, rect in items:
            lines.append('\t\t\t{Name: "%s", Rect: maa.Rect{%d, %d, %d, %d}},'
                         % (item, rect[0], rect[1], rect[2], rect[3]))
        lines.append('\t\t},')
    if current_episode is not None:
        lines.append('\t},')
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 3:
        print('usage: convert_dream.py <agent_dir> <out_file>')
        return 1
    agent_dir = sys.argv[1]
    out_file = sys.argv[2]

    # 收集所有 dream_*.py(按编号排序)
    files = sorted(glob.glob(os.path.join(agent_dir, 'dream_stages', 'dream_*.py')))
    if not files:
        print('no dream files found under', agent_dir)
        return 1

    # items_ordered: [(episode, func_name, level, [(item, rect)])] 保持 dict 插入序
    items_ordered = []
    for path in files:
        ep = os.path.basename(path).replace('dream_', '').replace('.py', '')
        funcs = extract_funcs(path)
        for func in ('dream_stage', 'dream_team'):
            level_map = funcs.get(func)
            if not level_map:
                continue
            for level, items in level_map.items():
                items_ordered.append((ep, func, level, list(items.items())))

    if not items_ordered:
        print('no data extracted')
        return 1

    body = gen(items_ordered)
    stage_body = gen([x for x in items_ordered if x[1] == 'dream_stage'])
    team_body = gen([x for x in items_ordered if x[1] == 'dream_team'])

    # 校验:同一 (ep, func) 下 level 是否重复
    seen = set()
    for ep, func, level, _ in items_ordered:
        key = (ep, func, level)
        if key in seen:
            print('WARN duplicate:', key)
        seen.add(key)

    src = '''package action

import "github.com/MaaXYZ/maa-framework-go/v4"

// Code generated from agent/custom/action/dream_stages/*.py by tools/convert_dream.py; DO NOT EDIT.

func dreamStageData(episode, level string) []dreamItem {
	m, ok := dreamStageMap[episode]
	if !ok {
		return nil
	}
	return m[level]
}

func dreamTeamData(episode, level string) []dreamItem {
	m, ok := dreamTeamMap[episode]
	if !ok {
		return nil
	}
	return m[level]
}

var dreamStageMap = map[string]map[string][]dreamItem{
%s
}

var dreamTeamMap = map[string]map[string][]dreamItem{
%s
}
''' % (stage_body, team_body)

    # 拆分 stage/team 两个 map(上面 gen 输出是合并的,这里重写更清晰)
    # 直接输出合并版本,保证两函数数据都齐全;为避免重复,生成时按 func 分组
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(src)
    print('generated %d (episode,func,level) entries -> %s' % (len(items_ordered), out_file))
    return 0


if __name__ == '__main__':
    sys.exit(main())
