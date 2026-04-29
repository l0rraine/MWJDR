# MWJDR - 无尽冬日自动化

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 的《无尽冬日》（Whiteout Survival）自动化工具，通过 [MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia) 提供图形界面。

## 功能一览

### 战斗任务

| 任务 | 说明 | 可配置项 |
|------|------|----------|
| 集结巨兽 | 自动参与巨兽集结，支持普通/高级模式 | 队伍序号、作战模式、次数/体力、免费罐头控制 |
| 自动野兽 | 自动搜索并攻击野兽 | 队伍序号 |
| 自动灯塔 | 自动探索灯塔（救援/野兽/冒险） | 队伍序号 |
| 使用物品集结 | 使用吉娜角/收割者镰刀等物品发起集结 | 物品选择、队伍序号、体力设置 |

### 非战斗任务

| 任务 | 说明 | 可配置项 |
|------|------|----------|
| 启动游戏 | 启动游戏并初始化环境 | 切换角色（王国编号+序号）、确保有队伍可用 |
| 自动游历 | 自动完成游历小游戏（钓鱼、挖掘、烹饪等） | — |
| 联盟总动员 | 扫描联盟任务并刷新高价值奖励 | 槽位开关、各任务类型筛选 |
| 梦境寻忆 | 自动完成梦境寻忆找物玩法 | 闯关模式 / 协梦同行 |
| 结束 | 任务结束后清理环境 | 是否打开自动加入集结 |

### 智能特性

- **自动队列管理**：执行战斗任务前自动确保有空闲队列（关闭自动加入、等待/召回队伍），若无战斗任务则自动跳过
- **智能体力控制**：巨兽作战支持精确次数模式、罐头体力模式；普通模式下 0-19 点自动使用免费罐头，19 点后可配置是否使用
- **体力耗尽自动禁用**：当战斗因体力/罐头耗尽而结束时，自动禁用所有已启用的战斗任务，避免反复空跑
- **角色切换**：支持按王国编号和序号自动切换到指定角色
- **多实例支持**：通过 MFAAvalonia 环境变量识别当前实例，多开时互不干扰

## 项目结构

```
MWJDR/
├── assets/                          # MaaFramework 资源目录
│   ├── interface.json               # 界面配置（任务列表、选项、pipeline_override）
│   └── resource/
│       ├── pipeline/                # Pipeline 定义（16 个 JSON）
│       │   ├── startup.json         #   启动游戏、角色切换、队列管理
│       │   ├── monster.json         #   集结巨兽
│       │   ├── beast.json           #   自动野兽
│       │   ├── light.json           #   自动灯塔
│       │   ├── item-battle.json     #   使用物品集结
│       │   ├── dream.json           #   梦境寻忆
│       │   ├── unite.json           #   联盟总动员
│       │   ├── travel.json          #   自动游历
│       │   ├── mine.json            #   挖矿
│       │   ├── combat.json          #   战斗辅助（OCR 时间、出征状态、体力识别）
│       │   ├── common.json          #   通用节点（关闭礼包、后退、导航城外）
│       │   ├── autojoin.json        #   自动加入集结开关
│       │   ├── end.json             #   结束清理
│       │   ├── gift.json            #   礼包领取
│       │   ├── help.json            #   联盟帮助
│       │   └── reddot.json          #   红点通知、邮件、联盟科技
│       ├── model/                   # OCR 模型
│       └── image/                   # 模板图片
│
├── agent/                           # Python 自定义动作
│   ├── main.py                      # 入口：venv 管理 → AgentServer 启动
│   ├── custom/action/               # 自定义动作实现
│   │   ├── combat.py                #   CombatRepetitionCount 计数器、切换队伍、撤回队伍
│   │   ├── monster.py               #   巨兽次数识别、出征循环
│   │   ├── beast.py                 #   野兽出征循环
│   │   ├── light.py                 #   灯塔出征循环
│   │   ├── itemBattle.py            #   体力识别、物品集结循环
│   │   ├── dream.py                 #   梦境寻忆（坐标字典找物）
│   │   ├── unite.py                 #   联盟总动员扫描
│   │   ├── travel.py                #   游历宝藏挖掘
│   │   ├── mine.py                  #   挖矿队伍派遣/召回
│   │   └── common.py                #   角色切换、队列管理、节点控制
│   └── utils/                       # 工具模块
│       ├── logger.py                #   日志
│       ├── timelib.py               #   OCR 时间解析
│       ├── chainfo.py               #   联盟总动员状态管理
│       └── mfa_config.py            #   MFAAvalonia 实例配置读取、战斗任务检测与禁用
│
├── configure.py                     # 资源配置脚本
├── requirements.txt                 # Python 依赖
└── docs/                            # 文档
```

## 架构设计

本项目采用 **声明式 Pipeline + 命令式 Custom Action** 的双层架构：

```
MFAAvalonia (GUI)
  │
  ├─ 用户选择任务 + 配置选项
  │     │
  │     ▼
  │  interface.json → 收集 pipeline_override
  │     │
  │     ▼
  │  MaaFramework 引擎
  │     │
  │     ├─ 加载 pipeline JSON
  │     ├─ 合并 pipeline_override
  │     └─ 从 entry 节点开始执行
  │           │
  │           ▼
  │     Pipeline 执行循环
  │       ├─ 节点 enabled: false → 跳过
  │       ├─ 识别（TemplateMatch / OCR / ColorMatch）
  │       ├─ 动作（Click / Swipe / Custom / DoNothing）
  │       ├─ Custom Action → 调用 Python 代码
  │       │     ├─ context.run_task() / run_recognition() → 执行子任务
  │       │     ├─ context.override_pipeline() → 运行时修改节点
  │       │     └─ context.run_recognition_direct() / run_action_direct() → 直接调用
  │       └─ 跟随 next 数组进入下一节点
  │
  └─ 任务完成
```

### Pipeline 节点控制

节点有三种 enable/disable 方式：

1. **静态 `pipeline_override`**：`interface.json` 中选项的 cases 定义，任务启动前由 MFAAvalonia 合并
2. **运行时 `override_pipeline()`**：Custom Action 在执行过程中动态修改节点属性
3. **默认 `enabled: false`**：Pipeline JSON 中某些节点默认禁用，由选项或代码激活

### 自定义动作注册

所有 Custom Action 通过装饰器注册到 AgentServer：

```python
@AgentServer.custom_action("动作名称")
class MyAction(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # argv.custom_action_param: JSON 字符串参数
        # context: 可调用 pipeline API
        return CustomAction.RunResult(success=True)
```

### 战斗任务自动检测

`MakeSureQueueAvailable` 在执行前会读取 MFAAvalonia 实例配置，判断用户是否勾选了战斗任务：

```python
from utils.mfa_config import has_battle_tasks

battle_status = has_battle_tasks()
if battle_status is False:
    # 无战斗任务，跳过确保空闲队列
    return CustomAction.RunResult(success=True)
```

实现原理：MFAAvalonia 启动 Agent 进程时注入 `MFA_INSTANCE_ID` 环境变量，Python 端据此读取 `config/instances/{id}.json` 中的 `TaskItems`，检查战斗任务的 `default_check` 状态。

### 体力耗尽自动禁用战斗任务

当任何战斗因体力/罐头耗尽而结束时（无免费体力、罐头用完等），自动禁用当前实例中所有已启用的战斗任务（`default_check: true → false`），避免后续任务反复空跑。

```python
from utils.mfa_config import disable_battle_tasks

# 体力耗尽时调用
disable_battle_tasks()  # 将所有战斗任务的 default_check 设为 false
```

适用场景：
- 集结巨兽：免费罐头未启用 / 罐头次数上限 / 罐头用完 / 无免费体力
- 物品集结：体力耗尽
- 自动野兽：无免费体力
- 自动灯塔：无免费体力

**注意**：因「出征次数上限」导致的结束不会触发禁用（非体力原因）。

## 快速开始

### 前置条件

- Windows 系统
- [MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia) 已安装
- 安卓设备已通过 ADB 连接

### 安装

1. 下载最新 Release 或克隆本仓库

   ```bash
   git clone https://github.com/l0rraine/MWJDR.git
   ```

2. 配置资源文件

   ```bash
   python ./configure.py
   ```

3. 将项目目录添加到 MFAAvalonia 作为资源路径

### 使用

1. 启动 MFAAvalonia，选择本项目
2. 连接安卓设备
3. 选择要执行的任务并配置选项
4. 点击开始

## 开发指南

### 添加新的 Pipeline 节点

1. 在 `assets/resource/pipeline/` 对应的 JSON 文件中添加节点定义
2. 在 `assets/interface.json` 中注册任务入口和可配置选项
3. 如需复杂逻辑，在 `agent/custom/action/` 中实现 Custom Action

### 添加新的 Custom Action

1. 在 `agent/custom/action/` 下创建或修改 Python 文件
2. 使用 `@AgentServer.custom_action("名称")` 装饰器注册
3. 在 Pipeline JSON 中通过 `"action": "Custom"` + `"custom_action": "名称"` 引用

### 调试

开发模式下（`assets/` 目录下存在 `interface.json`），agent 会自动启用 DEBUG 日志级别。

## 鸣谢

- **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** — 核心自动化引擎
- **[MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia)** — 跨平台图形界面
- **[MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights)** — MAA 系列项目的起点

## 许可证

本项目基于 [LICENSE](./LICENSE) 发布。
