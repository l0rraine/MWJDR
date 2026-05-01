# MWJDR 项目知识库

本文档记录了在 MWJDR 项目开发过程中，关于 MaaFramework 和 MFAAvalonia 的常见疑问与解答。

---

## 目录

1. [多实例运行时如何区分当前实例？](#1-多实例运行时如何区分当前实例)
2. [MFAAvalonia 向 Agent 进程注入了哪些环境变量？](#2-mfaavalonia-向-agent-进程注入了哪些环境变量)
3. [如何在执行前检测用户是否选择了战斗任务？](#3-如何在执行前检测用户是否选择了战斗任务)
4. [实例配置文件中 `check` 和 `default_check` 的区别？](#4-实例配置文件中-check-和-default_check-的区别)
5. [`CustomAction.RunResult(success=True/False)` 对任务执行有什么影响？](#5-customactionrunresultsuccesstruefalse-对任务执行有什么影响)
6. [`_direct` API 与普通 Pipeline 调用的区别？](#6-_direct-api-与普通-pipeline-调用的区别)
7. [JRecognitionType / JActionType 的作用？](#7-jrecognitiontype--jactiontype-的作用)
8. [Custom Action 中使用 context.run_task() 递归调用导致重复执行](#8-custom-action-中使用-contextrun_task-递归调用导致重复执行)
9. [Custom Action 中应避免的 context.run_task() 递归调用模式](#9-custom-action-中应避免的-contextrun_task-递归调用模式)
10. [行军识别无限等待问题与超时机制](#10-行军识别无限等待问题与超时机制)
11. [context.run_recognition 返回 None 的条件](#11-contextrun_recognition-返回-none-的条件)
12. [JumpBack 机制与嵌套节点执行顺序](#12-jumpback-机制与嵌套节点执行顺序)
13. [detail.box 与 detail.best_result.box 的关系](#13-detailbox-与-detailbest_resultbox-的关系)
14. [ColorMatch 取色识别 API](#14-colormatch-取色识别-api)
15. [Rect 偏移量计算规则](#15-rect-偏移量计算规则)
16. [override_pipeline 三层级作用域与跨任务持久化](#16-override_pipeline-三层级作用域与跨任务持久化)

---

## 1. 多实例运行时如何区分当前实例？

### 问题

当用户同时运行多个 MFAAvalonia 实例时，`config/instances/` 目录下会有多个配置文件。每个 Agent 进程如何确定自己属于哪个实例？

### 解答

MFAAvalonia 在启动 Agent 进程时，会通过**环境变量注入**的方式传递实例信息。具体来说，MFAAvalonia 会在启动参数或环境中注入以下关键变量：

| 环境变量 | 说明 |
|---|---|
| `MFA_INSTANCE_ID` | 当前实例的唯一标识符（对应 `config/instances/{id}.json` 的文件名） |
| `MFA_INSTANCE_NAME` | 当前实例的显示名称 |

因此，每个 Agent 进程可以通过读取 `os.environ["MFA_INSTANCE_ID"]` 来获取自己的实例 ID，进而找到对应的配置文件。这使得多实例并行运行时，各实例能够独立、正确地读取自己的配置。

### 实现要点

```python
import os

instance_id = os.environ.get("MFA_INSTANCE_ID")
if instance_id:
    config_path = os.path.join(config_dir, f"{instance_id}.json")
    # 读取该实例的专属配置
```

> ⚠️ 注意：如果进程不是由 MFAAvalonia 启动的（例如直接命令行运行），则不会有这些环境变量。代码需要处理这种情况。

---

## 2. MFAAvalonia 向 Agent 进程注入了哪些环境变量？

### 问题

MFAAvalonia 启动 Agent 时会注入哪些环境变量？分别有什么用途？

### 解答

MFAAvalonia 通过 `MaaInterface` 中的 `AdbController` 配置和进程启动逻辑，向 Agent 进程注入以下环境变量：

| 环境变量 | 说明 | 示例值 |
|---|---|---|
| `MFA_INSTANCE_ID` | 当前实例的唯一 ID | `"abc123-def456"` |
| `MFA_INSTANCE_NAME` | 当前实例的显示名称 | `"实例1"` |
| `PI_*`（前缀变量） | 客户端/控制器相关配置信息 | — |

此外，MFAAvalonia 还会将**当前工作目录 (CWD)** 设置为 MFAAvalonia 的 `DataRoot` 路径。这意味着在 Agent 进程中，`os.getcwd()` 初始值就是 MFAAvalonia 的数据目录。

### 实现要点

由于 Agent 的 `main.py` 中通常会执行 `os.chdir()` 切换到自身目录，因此需要在 `chdir` 之前保存 DataRoot 路径：

```python
# main.py 中，在 chdir 之前保存
os.environ["MFA_DATA_ROOT"] = os.getcwd()
os.chdir(os.path.dirname(os.path.abspath(__file__)))
```

---

## 3. 如何在执行前检测用户是否选择了战斗任务？

### 问题

当用户没有选择任何战斗任务时，"确保有空闲队列"节点仍然会执行，造成不必要的等待。能否在执行前自动判断并跳过？

### 解答

可以通过读取 MFAAvalonia 的实例配置文件来实现。具体流程：

1. **读取实例 ID**：从 `MFA_INSTANCE_ID` 环境变量获取
2. **读取实例配置**：从 `config/instances/{id}.json` 加载 JSON
3. **检查 TaskItems**：遍历 `TaskItems` 数组，检查战斗任务是否被启用
4. **返回判断结果**：`True`（有战斗任务）/ `False`（无战斗任务）/ `None`（非 MFAAvalonia 环境）

### 战斗任务定义

以下任务被视为"战斗任务"：

- 集结巨兽
- 自动野兽
- 自动灯塔
- 使用物品集结

### 核心代码

```python
# agent/utils/mfa_config.py

BATTLE_TASKS = {"集结巨兽", "自动野兽", "自动灯塔", "使用物品集结"}

def has_battle_tasks() -> bool | None:
    """检测当前实例是否启用了战斗任务
    
    Returns:
        True: 有战斗任务被启用
        False: 无战斗任务被启用
        None: 非MFAAvalonia环境（保留原始行为）
    """
    instance_id = os.environ.get("MFA_INSTANCE_ID")
    if not instance_id:
        return None  # 非MFA环境，不做干预
    
    data_root = os.environ.get("MFA_DATA_ROOT", "")
    config_path = os.path.join(data_root, "config", "instances", f"{instance_id}.json")
    
    if not os.path.exists(config_path):
        return None
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    for task in config.get("TaskItems", []):
        if task.get("default_check", False) and task.get("name", "") in BATTLE_TASKS:
            return True
    
    return False
```

### 在 Custom Action 中使用

```python
class MakeSureQueueAvailable(CustomActionHandler):
    def run(self, context, task_id, param, box, reco_detail):
        battle_status = has_battle_tasks()
        if battle_status is False:
            logger.info("后续无战斗任务，跳过确保空闲队列")
            return CustomAction.RunResult(success=True)
        # ... 正常逻辑
```

---

## 4. 实例配置文件中 `check` 和 `default_check` 的区别？

### 问题

在读取实例配置文件时，任务的启用状态字段是 `check` 还是 `default_check`？

### 解答

是 **`default_check`**，不是 `check`。

MFAAvalonia 的 C# 模型 `MaaInterfaceTask` 中，属性定义如下：

```csharp
[JsonProperty("default_check")]
public bool Check { get; set; } = true;
```

C# 属性名为 `Check`，但通过 `[JsonProperty("default_check")]` 特性，序列化到 JSON 时使用的键名是 `default_check`。因此，JSON 文件中的结构为：

```json
{
  "TaskItems": [
    {
      "name": "自动灯塔",
      "default_check": false
    },
    {
      "name": "集结巨兽",
      "default_check": true
    }
  ]
}
```

### 踩坑记录

最初使用 `task.get("check", True)` 读取启用状态，由于 JSON 中实际键名是 `default_check`，`check` 键不存在，默认值 `True` 总是被返回，导致**所有战斗任务都被误判为已启用**。

修正为 `task.get("default_check", False)` 后，问题解决。

---

## 5. `CustomAction.RunResult(success=True/False)` 对任务执行有什么影响？

### 问题

在 Custom Action 中返回 `RunResult(success=True)` 或 `RunResult(success=False)` 时，True/False 的值是否会对 Pipeline 任务的执行产生额外影响？

### 解答

**是的，有直接影响。** `success` 参数决定了 Pipeline 的执行路径：

#### `success=True` — 节点执行成功

- 节点标记为 `completed = true`
- Pipeline 沿该节点的 **`next`** 列表继续执行
- 发送 `MaaMsg_Node_PipelineNode_Succeeded` 回调通知

```
当前节点 → [next 列表中的节点] → 继续正常流程
```

#### `success=False` — 节点执行失败

- 节点标记为 `completed = false`
- Pipeline 沿该节点的 **`on_error`** 列表执行（而非 `next`）
- 发送 `MaaMsg_Node_PipelineNode_Failed` 回调通知
- 如果配置了 `save_on_error`，会自动保存截图到日志目录
- **不会自动重试**当前节点

```
当前节点 → [on_error 列表中的节点] → 错误处理流程
```

#### 不同场景下的行为

| 场景 | 行为 |
|---|---|
| `on_error` 已定义（有节点） | 沿 `on_error` 路径执行，可用于自定义错误恢复 |
| `on_error` 为空（默认） | `next` 为空 → **任务终止** |
| 错误处理中再次失败 | 检测到"错误处理循环" → **立即中止任务** |

#### 源码依据

**Python 绑定**（`source/binding/Python/maa/custom_action.py`）：
```python
if isinstance(result, CustomAction.RunResult):
    return int(result.success)       # True→1, False→0
elif isinstance(result, bool):
    return int(result)               # 直接转换
elif result is None:
    return int(True)                 # None 默认为成功
```

**C++ Pipeline 执行逻辑**（`source/MaaFramework/Task/PipelineTask.cpp`）：
```cpp
if (node_detail.completed) {
    next = node.next;           // 成功 → 正常路径
} else {
    LogWarn << "node not completed, handle error";
    error_handling = true;
    next = node.on_error;       // 失败 → 错误处理路径
    save_on_error(node.name);   // 保存诊断截图
}
```

#### 实际使用建议

| 返回值 | 适用场景 |
|---|---|
| `RunResult(success=True)` | 动作正常完成，或主动跳过（如无战斗任务时跳过队列检查） |
| `RunResult(success=False)` | 动作执行真正失败，需要进入错误处理流程 |

> 💡 **在 MWJDR 中**，"确保有空闲队列"节点在无战斗任务时返回 `success=True` 来跳过执行。这是因为"不需要执行"不等于"执行失败"，我们希望 Pipeline 正常继续后续流程，而不是进入错误处理。

---

## 6. `_direct` API 与普通 Pipeline 调用的区别？

### 问题

`run_recognition_direct` / `run_action_direct` 这类 `_direct` 方法与普通的 Pipeline 调用有什么区别？

### 解答

### 普通 Pipeline 调用

通过 `context.run_task("节点名称")` 执行 Pipeline JSON 中定义的节点，框架会自动完成：
1. 识别（Recognition）— 根据节点中定义的识别类型和参数
2. 执行（Action）— 根据节点中定义的动作类型和参数
3. 流程控制 — 自动跟随 `next`、`on_error` 等路径

```
Pipeline JSON 定义 → context.run_task() → 框架自动调度
```

### `_direct` API

直接调用识别或动作，**绕过 Pipeline JSON 定义**，参数完全由代码控制：

- `run_recognition_direct(JRecognitionType, JParam, img)` — 直接对图像执行识别
- `run_action_direct(JActionType, JParam, box, reco_detail)` — 直接执行动作

```
代码中传入参数 → _direct API → 直接执行
```

### 对比

| 特性 | Pipeline 调用 | `_direct` API |
|---|---|---|
| 定义位置 | Pipeline JSON 文件 | Python 代码中 |
| 参数来源 | JSON 配置 | 代码动态构造 |
| 流程控制 | 框架自动（next/on_error） | 代码手动控制 |
| 适用场景 | 固定的自动化流程 | 需要动态判断逻辑的场景 |
| 灵活性 | 较低（配置驱动） | 较高（代码驱动） |

### 适用场景

- **Pipeline 调用**：适用于固定流程，如"打开界面→点击按钮→等待响应"
- **`_direct` API**：适用于需要代码逻辑判断的场景，如"根据识别结果动态选择不同操作"、"临时执行一次性操作无需定义 Pipeline 节点"

在 MWJDR 中，`_direct` API 主要用于 Custom Action 内部，当需要执行临时操作但不想在 Pipeline JSON 中创建临时节点时使用。

---

## 7. JRecognitionType / JActionType 的作用？

### 问题

`JRecognitionType` 和 `JActionType` 这两个枚举类型是什么？与 `_direct` API 有什么关系？

### 解答

它们是 MWJDR 项目自定义的 **StrEnum 类型**，用于 `_direct` API 调用时指定识别或动作的类型。

### JRecognitionType（识别类型枚举）

定义了所有可用的识别方式，每个枚举值对应 Pipeline JSON 中 `recognition` 字段的一个取值：

```python
class JRecognitionType(StrEnum):
    TemplateMatch = "TemplateMatch"    # 模板匹配
    OCR = "OCR"                        # 文字识别
    # ... 其他识别类型
```

### JActionType（动作类型枚举）

定义了所有可用的动作方式，每个枚举值对应 Pipeline JSON 中 `action` 字段的一个取值：

```python
class JActionType(StrEnum):
    Click = "Click"                    # 点击
    Swipe = "Swipe"                    # 滑动
    Custom = "Custom"                  # 自定义动作
    # ... 其他动作类型
```

### 与 `_direct` API 的关系

`_direct` API 的第一个参数就是这些枚举类型：

```python
# 直接执行模板匹配识别
result = run_recognition_direct(
    JRecognitionType.TemplateMatch,   # 识别类型
    {"template": "button.png"},       # 识别参数
    screenshot_image                  # 输入图像
)

# 直接执行点击动作
run_action_direct(
    JActionType.Click,                # 动作类型
    {},                               # 动作参数
    result.box,                       # 目标区域
    result.reco_detail                # 识别详情
)
```

本质上，这些枚举就是 Pipeline JSON 中字符串值的代码化表达，使得 `_direct` API 可以用类型安全的方式指定操作类型。

---

## 附录：关键文件索引

| 文件 | 说明 |
|---|---|
| `agent/main.py` | Agent 入口，保存 `MFA_DATA_ROOT` 环境变量 |
| `agent/utils/mfa_config.py` | MFAAvalonia 实例配置读取工具 |
| `agent/custom/action/common.py` | 通用 Custom Action，包含 `MakeSureQueueAvailable` |
| `agent/custom/action/` | Custom Action 目录 |
| `agent/pipeline/` | Pipeline JSON 定义目录 |
| `config/instances/{id}.json` | MFAAvalonia 实例配置文件 |

---

## 8. Custom Action 中使用 `context.run_task()` 递归调用导致重复执行

### 问题

联盟总动员任务中，当两个槽位都已找到满意的任务后，仍然会重复执行若干次才停止。为什么？

### 解答

这是一个 **Custom Action 递归调用与 Pipeline 循环机制冲突** 的典型问题。

#### 错误的写法

在 Custom Action 内部使用 `context.run_task("入口节点")` 实现循环：

```python
# ❌ 错误示范
@AgentServer.custom_action("联盟总动员_扫描")
class UniteScan(CustomAction):
    def run(self, context, argv):
        # ... 扫描逻辑 ...
        
        if min(need_wait_seconds) != 86400:
            time.sleep(min(need_wait_seconds))
            context.run_task("联盟总动员_入口")  # ← 递归调用入口
            return CustomAction.RunResult(success=True)
        else:
            return CustomAction.RunResult(success=False)
```

#### 问题根因

当两个槽位都满意时，内层递归的 `context.run_task("联盟总动员_入口")` 执行后最终返回 `success=False`，这个 `False` 只终止了内层调用。但**外层 Custom Action 仍然返回 `success=True`**，Pipeline 认为 `联盟总动员_执行扫描` 节点执行成功，继续沿 `next` 走，最终通过 `[JumpBack]` 节点重新进入入口，造成已完成的任务被重复执行。

```
外层: 联盟总动员_执行扫描 → return success=True → Pipeline 走 next → [JumpBack]重新进入入口
  └─ 内层: context.run_task("联盟总动员_入口") → 扫描 → return success=False → 仅终止内层
```

#### 正确的写法

**不要在 Custom Action 中递归调用入口**，而是利用 Pipeline 的 `next` 机制自然循环：

**1. Pipeline JSON 中为 Custom Action 节点定义 `next`：**

```json
"联盟总动员_执行扫描": {
    "action": "Custom",
    "custom_action": "联盟总动员_扫描",
    "next": [
        "联盟总动员_入口"   // ← success=True 时 Pipeline 自动回到入口
    ]
}
```

**2. Custom Action 中直接返回，不做递归调用：**

```python
# ✅ 正确写法
@AgentServer.custom_action("联盟总动员_扫描")
class UniteScan(CustomAction):
    def run(self, context, argv):
        # ... 扫描逻辑 ...
        
        if min(need_wait_seconds) != 86400:
            time.sleep(min(need_wait_seconds))
            return CustomAction.RunResult(success=True)   # ← Pipeline 走 next → 回到入口
        else:
            return CustomAction.RunResult(success=False)  # ← Pipeline 走 on_error（空）→ 任务终止
```

#### 执行流程对比

| 方式 | 需要继续扫描 | 两个槽位都满意 |
|---|---|---|
| ❌ 递归调用 | 内层递归 + 外层 success=True → 可能重复 | 内层 False 仅终止内层，外层 True 导致重复 |
| ✅ Pipeline next | return True → Pipeline 走 next → 入口 | return False → Pipeline 走 on_error（空）→ 终止 |

#### 核心原则

> **Custom Action 中避免使用 `context.run_task()` 调用自身入口节点来循环**。应通过 `return RunResult(success=True/False)` 配合 Pipeline 的 `next` / `on_error` 机制控制流程。`success=True` → 走 `next` 继续循环；`success=False` → 走 `on_error` 终止任务。

这个原则适用于所有需要在 Custom Action 中实现"循环直到条件满足"的场景，例如集结巨兽的出征循环、物品集结的体力循环等。

---

## 9. Custom Action 中应避免的 `context.run_task()` 递归调用模式

### 问题

除了联盟总动员的重复执行 bug，项目中还存在大量 `context.run_task("入口节点")` 的递归调用，虽然暂未引发 bug，但本质上都存在相同的风险，应当统一消除。

### 涉及的文件和调用

| 文件 | Custom Action | 递归调用 | 替换方案 |
|---|---|---|---|
| `monster.py` | 设置怪兽次数 | `context.run_task("自动集结_巨兽入口")` | `success=True` + Pipeline `next` |
| `monster.py` | 开始出征 | `context.run_task("自动集结_巨兽入口")` ×2 | `success=True` + Pipeline `next` |
| `itemBattle.py` | 识别体力 | `context.run_task("集结物品入口")` | `success=True` + Pipeline `next` |
| `itemBattle.py` | 物品集结 | `context.run_task("集结物品_识别体力入口")` + `context.run_task("集结物品入口")` | `success=True` + Pipeline `next` |
| `beast.py` | 野兽开始出征 | `context.run_task("自动野兽_入口")` | `success=True` + Pipeline `next` |
| `light.py` | 灯塔开始出征 | `context.run_task("灯塔入口")` | `success=True` + Pipeline `next` |

### 修改模式

**1. Python 代码：移除递归调用**

```python
# ❌ 修改前：递归调用入口 + success=True
context.run_task("自动集结_巨兽入口")
return CustomAction.RunResult(success=True)

# ✅ 修改后：直接返回 success=True，由 Pipeline next 回到入口
return CustomAction.RunResult(success=True)
```

**2. Pipeline JSON：为 Custom Action 节点添加 `next`**

```json
// ❌ 修改前：无 next，依赖 Python 递归调用
"自动集结_准备出征": {
    "action": "Custom",
    "custom_action": "开始出征"
}

// ✅ 修改后：定义 next，由 Pipeline 控制循环
"自动集结_准备出征": {
    "action": "Custom",
    "custom_action": "开始出征",
    "next": ["自动集结_巨兽入口"]
}
```

### 特殊情况：与别人队伍重复

`开始出征` 中有一处特殊逻辑：发现与别人队伍重复时，点击取消后需要重新选择巨兽。原来的写法是递归调用入口后继续执行后续出征逻辑，这实际上存在隐患——递归执行完入口路径后回到当前代码继续执行，可能导致计数混乱。

修改为发现重复后直接 `return success=True`，由 Pipeline next 回到入口重新走完整流程，语义更清晰。

```python
# ❌ 修改前：递归调用入口后继续往下执行
if detail.hit:
    context.tasker.controller.post_click(detail.box.x, detail.box.y).wait()
    context.run_task("自动集结_巨兽入口")
    # 继续执行出征计数、等待行军等逻辑...

# ✅ 修改后：直接返回，由 Pipeline 重新走完整流程
if detail.hit:
    context.tasker.controller.post_click(detail.box.x, detail.box.y).wait()
    return CustomAction.RunResult(success=True)
```

### 修改后的 Pipeline next 映射表

| Pipeline 节点 | next 目标 | 含义 |
|---|---|---|
| `自动集结_设置怪兽次数` | `自动集结_巨兽入口` | 未达上限，继续出征 |
| `自动集结_准备出征` | `自动集结_巨兽入口` | 出征完成，开始下一轮 |
| `集结物品_识别体力` | `集结物品入口` | 体力够，开始找物品 |
| `集结物品_准备出征` | `集结物品_识别体力入口` | 出征完成，重新识别体力 |
| `自动野兽_准备出征` | `自动野兽_入口` | 出征完成，继续下一轮 |
| `灯塔准备出征` | `灯塔入口` | 出征完成，继续下一轮 |

---

## 10. 行军识别无限等待问题与超时机制

### 问题

巨兽和物品集结在点击出征后，会等待识别"行军中"状态。原来的实现是一个无限循环：

```python
# ❌ 无限等待，可能永远卡住
detail = None
while detail is None or not detail.hit:
    time.sleep(1)
    img = context.tasker.controller.post_screencap().wait().get()
    detail = context.run_recognition("自动集结_行军中", img)
```

如果行军状态识别不到（界面变化、识别率问题等），程序会无限等待，永远不会继续执行。

### 解决方案

增加 301 秒（5 分 01 秒）超时机制。从点击出征开始计时，超过 301 秒未识别到行军，则认为行军已经开始，继续执行后续逻辑。

```python
# ✅ 增加超时机制
march_start_time = time.time()
time.sleep(80)
context.run_task("转到城外")

detail = None
while detail is None or not detail.hit:
    if time.time() - march_start_time >= 301:
        logger.info("已超过5分01秒未识别到行军，认为行军已经开始")
        break
    time.sleep(1)
    img = context.tasker.controller.post_screencap().wait().get()
    detail = context.run_recognition("自动集结_行军中", img)

logger.debug("已识别到行军")
time.sleep(return_time*2 + 0.5)
```

### 设计要点

- **超时时间 301 秒**：从点击出征开始计算，包含 80s 初始等待 + 约 221s 识别循环
- **超时后行为与识别到一致**：无论是否识别到行军，都认为行军已开始，后续等待返回时间的逻辑不变
- **不区分识别结果**：`march_found` 等中间变量无意义，因为两种情况（识别到 / 超时）的后续行为完全一致

### 适用范围

此超时机制应用于巨兽 (`monster.py`) 和物品集结 (`itemBattle.py`) 两个战斗模块。野兽和灯塔的出征逻辑不同（无行军等待环节），不需要此机制。

---

## 11. context.run_recognition 返回 None 的条件

### 问题

`context.run_recognition(entry, img)` 什么情况下返回 `None`？

### 解答

`context.run_recognition` 在以下条件之一时返回 `None`：

| 条件 | 说明 |
|---|---|
| entry 不存在 | Pipeline JSON 中没有定义该名称的节点 |
| 节点被禁用 | 节点的 `enabled` 字段为 `false` |
| 图片为空 | 传入的 `img` 参数为 `None` 或空 |
| reco_id 查询失败 | 框架内部无法获取识别器 ID |

返回 `None` 与返回 `RecognitionDetail(hit=False)` 是不同的：
- `None`：识别根本没有执行
- `hit=False`：识别执行了但未匹配到目标

### 实现要点

```python
detail = context.run_recognition("某个节点", img)
if detail is None:
    # 节点不存在、被禁用或图片为空
    logger.debug("识别未执行")
    return False
if not detail.hit:
    # 识别执行了但未命中
    logger.debug("识别未命中")
    return False
# 识别命中
box = detail.box
```

> ⚠️ 必须先检查 `detail is None`，否则对 `None` 调用 `.hit` 会抛出 `AttributeError`。

---

## 12. JumpBack 机制与嵌套节点执行顺序

### 问题

当一个节点拥有 `is_jump_back: true`（即节点名以 `[JumpBack]` 前缀标记）时，执行顺序是怎样的？嵌套的 JumpBack 如何处理？

### 解答

JumpBack 的含义是：**识别成功后，重新从当前父节点 `next` 列表的开头执行**。

#### 基本规则

1. JumpBack 回到**直接父节点**的 `next` 列表开头，不是祖父节点
2. 嵌套的 JumpBack 先处理内层，再处理外层
3. DirectHit 节点（无 `recognition` 字段）总是匹配成功，配合 JumpBack 会形成无限循环，**必须**在其前放置有条件的识别节点

#### 示例

```json
"入口": {
    "next": [
        "每日检查",
        "已在界面",
        "[JumpBack]点击商店",
        "[JumpBack]后退"
    ]
}
```

执行顺序：
1. 执行 `每日检查`（Custom Action），若 `success=True` → 继续
2. 执行 `已在界面`（OCR），若识别到 → 进入其 `next`
3. 若 `已在界面` 未识别到 → 执行 `[JumpBack]点击商店`
4. `[JumpBack]点击商店` 识别成功 → **回到 `入口.next` 开头**，重新从 `每日检查` 开始
5. 但 `每日检查` 在第二轮时如果返回 `success=True`，会直接跳到 `已在界面`，不会再触发 `[JumpBack]点击商店`

#### 注意事项

- JumpBack 是 Pipeline 级别的循环控制，不要与 Custom Action 内部的 Python 循环混淆
- 当入口的 `next` 只有 `[每日检查]` 一个元素时，每日检查返回 `False` → 无后续节点 → 任务终止

---

## 13. detail.box 与 detail.best_result.box 的关系

### 问题

`context.run_recognition` 返回的 `detail.box` 和 `detail.best_result.box` 是否相同？

### 解答

**是的，它们是相同的值。**

`detail.box` 是 `detail.best_result.box` 的快捷访问方式，两者指向同一个 `Rect` 对象。

```python
detail = context.run_recognition("某节点", img)
assert detail.box == detail.best_result.box  # True
```

`best_result` 是所有识别结果中评分最高的一个，而 `box` 直接返回这个最佳结果的区域。在绝大多数场景下，只需使用 `detail.box` 即可。

---

## 14. ColorMatch 取色识别 API

### 问题

如何在 MaaFramework Python 绑定中使用取色（ColorMatch）识别？如何指定颜色范围？

### 解答

MaaFramework 提供了 `JRecognitionType.ColorMatch` 和 `JColorMatch` 参数类，用于在指定区域内检测颜色是否在给定范围内。

### JColorMatch 参数

```python
from maa.pipeline import JRecognitionType, JColorMatch

@dataclass
class JColorMatch:
    lower: List[List[int]]  # 颜色下界，每个内层列表为 [R, G, B]（method=4 时）
    upper: List[List[int]]  # 颜色上界，格式同 lower
    roi: JTarget = (0, 0, 0, 0)      # 检测区域 (x, y, w, h)
    roi_offset: JRect = (0, 0, 0, 0) # ROI 偏移
    order_by: str = "Horizontal"      # 结果排序方式
    method: int = 4                   # 颜色空间：4 = RGB（默认）
    count: int = 1                    # 最少匹配像素数
    index: int = 0                    # 使用第几个结果
    connected: bool = False           # 是否使用连通分量分析
```

### 使用示例

```python
img = context.tasker.controller.post_screencap().wait().get()

# 精确颜色匹配（单色）
detail = context.run_recognition_direct(
    JRecognitionType.ColorMatch,
    JColorMatch(
        lower=[[37, 183, 86]],      # [R, G, B]
        upper=[[37, 183, 86]],
        roi=[510, 365, 36, 36],
        method=4,
    ),
    img,
)

# 颜色范围匹配
detail = context.run_recognition_direct(
    JRecognitionType.ColorMatch,
    JColorMatch(
        lower=[[4, 170, 224]],      # [R, G, B] 下界
        upper=[[5, 204, 237]],      # [R, G, B] 上界
        roi=[100, 200, 50, 50],
        method=4,
        count=1,                    # 至少1个像素匹配
    ),
    img,
)

if detail and detail.hit:
    # 匹配成功，detail.best_result.count 为匹配像素数
    pass
```

### 返回结果

ColorMatch 的结果类型为 `ColorMatchResult`（= `BoxAndCountResult`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `box` | `Rect` | 匹配区域的边界框 |
| `count` | `int` | 匹配的像素数量 |

### Pipeline JSON 等价写法

```json
{
    "recognition": "ColorMatch",
    "lower": [[4, 170, 224]],
    "upper": [[5, 204, 237]],
    "roi": [100, 200, 50, 50],
    "method": 4
}
```

> 💡 `method=4` 表示 RGB 颜色空间，是项目中最常用的方式。`lower`/`upper` 中的颜色值为 `[R, G, B]` 顺序。

---

## 15. Rect 偏移量计算规则

### 问题

当需要基于一个已识别的 `Rect`（box）计算偏移区域时，偏移量 `[dx, dy, dw, dh]` 如何与 box 的 `[x, y, w, h]` 运算？

### 解答

偏移量的四项与 box 的四项**分别相加**：

```
结果 Rect = (box.x + dx, box.y + dy, box.w + dw, box.h + dh)
```

即：
- `x' = box.x + dx` — 左上角 x 坐标偏移
- `y' = box.y + dy` — 左上角 y 坐标偏移
- `w' = box.w + dw` — 宽度偏移
- `h' = box.h + dh` — 高度偏移

### 示例

已知 50% 标签的 box 和偏移量 `[51, 42, 57, 72]`：

```python
box = discount_detail.box  # 例如 Rect(x=100, y=400, w=80, h=30)

# 物品图标区域：偏移 [51, 42, 57, 72]
item_roi = [box.x + 51, box.y + 42, box.w + 57, box.h + 72]
# = [151, 442, 137, 102]

# 购买按钮区域：偏移 [57, 212, 53, -16]
purchase_rect = Rect(
    box.x + 57,
    box.y + 212,
    box.w + 53,
    box.h - 16,  # 注意：-16 表示高度缩小
)
# = Rect(157, 612, 133, 14)
```

### 注意事项

- 当 `dh` 为负数时（如 `-16`），高度会缩小，需确保 `box.h + dh > 0`
- 偏移量是相对于 box 的**绝对偏移**，不是比例偏移
- 在 `run_recognition_direct` 的 `roi` 参数中直接传入计算后的 `[x, y, w, h]` 列表即可

---

## 16. override_pipeline 三层级作用域与跨任务持久化

### 问题

在 Custom Action 中调用 `context.override_pipeline({"节点": {"enabled": False}})` 禁用节点后，当前任务结束（如 `RunResult(success=False)` 触发任务终止），下一个任务执行时该节点仍然会执行。为什么 override 不持久化？有没有全局的 context 可以让 override 跨任务生效？

### 解答

MaaFramework 的 `override_pipeline` 有**三个层级**，作用域和持久化行为完全不同。项目中常用的 `context.override_pipeline()` 是 Context 级别，作用域仅限当前任务，任务结束后 Context 被销毁，override 随之消失。

#### 三层级对比

| API | 作用域 | 跨任务持久化 | 调用方式 |
|-----|--------|------------|---------|
| **`Resource.override_pipeline()`** | **全局**（所有使用该 Resource 的任务） | ✅ **是** | `context.tasker.resource.override_pipeline(...)` |
| `Tasker.override_pipeline(task_id, ...)` | 单个运行中的任务 | ❌ 否 | `context.tasker.override_pipeline(task_id, ...)` |
| `Context.override_pipeline(...)` | 当前上下文（任务内） | ❌ 否 | `context.override_pipeline(...)` |

#### 源码原理

**Context 级别（不持久化）**：

每次 `post_task()` 创建新的 `PipelineTask`，同时创建新的 `Context`（`Context::create(task_id_, tasker)`）。Context 内部持有 `pipeline_override_` 映射表，任务结束后 Context 被销毁，override 消失。

```cpp
// Context.cpp — get_pipeline_data() 查找顺序
std::optional<PipelineData> Context::get_pipeline_data(const std::string& node_name) const
{
    // 1. 先查 Context 级别 override（任务内）
    auto override_it = pipeline_override_.find(node_name);
    if (override_it != pipeline_override_.end()) {
        return override_it->second;
    }
    // 2. 再查 Resource 级别（全局，跨任务）
    auto& raw_pp_map = tasker_->resource()->pipeline_res().get_pipeline_data_map();
    auto raw_it = raw_pp_map.find(node_name);
    if (raw_it != raw_pp_map.end()) {
        return raw_it->second;
    }
    ...
}
```

**Resource 级别（持久化）**：

`ResourceMgr::override_pipeline()` 调用 `PipelineResMgr::parse_and_override()`，直接修改 Resource 的 `pipeline_data_map_`。由于 Resource 是长生命周期对象，绑定在 Tasker 上，所有后续任务创建的 Context 都会通过上面的查找顺序回查到 Resource 的数据，因此 override 对所有后续任务生效。

```cpp
// ResourceMgr.cpp
bool ResourceMgr::override_pipeline(const json::value& pipeline_override)
{
    return pipeline_res_.parse_and_override(pipeline_override, existing_keys, default_pipeline_);
    // 直接修改 pipeline_data_map_，全局持久化
}
```

#### Python binding 验证

```python
from maa.resource import Resource
from maa.tasker import Tasker
from maa.context import Context

# Resource 有 override_pipeline 方法 ✅
Resource.override_pipeline(self, pipeline_override: Dict) -> bool

# Context 到 Resource 的完整链路 ✅
context.tasker       → Tasker (property)
context.tasker.resource → Resource (property, returns maa.resource.Resource)
context.tasker.resource.override_pipeline({"节点": {"enabled": False}}) → bool
```

#### 使用方法

在 Custom Action 中实现跨任务的节点禁用：

```python
# ❌ 不持久化：仅当前任务内生效
context.override_pipeline({"自动集结_巨兽入口": {"enabled": False}})

# ✅ 持久化：全局生效，所有后续任务都会看到
context.tasker.resource.override_pipeline({"自动集结_巨兽入口": {"enabled": False}})
```

#### 实际应用：体力耗尽时禁用后续战斗任务

项目中的 `disable_battle_tasks()` 原来通过修改 MFAAvalonia 实例配置文件的 `default_check=False` 来禁用战斗任务，但 **MFA 只读取一次配置文件**，修改后不会重新加载，导致禁用无效。

正确做法是使用 `Resource.override_pipeline()`：

```python
def disable_battle_tasks_by_override(context: Context, current_entry: str = "") -> bool:
    """体力耗尽时，通过 Resource.override_pipeline 全局禁用后续战斗任务"""
    override = {}
    for entry in BATTLE_TASK_ENTRIES:
        override[entry] = {"enabled": False}

    resource = context.tasker.resource
    return resource.override_pipeline(override)
```

#### 注意事项

- Resource 级别的 override **不可撤销**（没有 `clear_override` 或 `revert_pipeline` 方法）
- 恢复只能通过再次调用：`resource.override_pipeline({"节点": {"enabled": True}})`
- 或者重新加载 Resource：`resource.clear()` + 重新 `post_bundle()`
- GitHub Issue [#1219](https://github.com/MaaXYZ/MaaFramework/issues/1219) 已提出"全局 Context"需求，目前尚未实现

#### 补充：Pipeline flat 格式 target 字段歧义

在 Pipeline JSON 的 flat 格式中，`target` 字段存在歧义——可能被框架解释为识别目标（ROI 约束）而非动作目标（点击位置）。例如：

```json
"关闭搜索": {
    "recognition": "TemplateMatch",
    "template": "搜索.png",
    "roi": [255, 1138, 217, 142],
    "action": "Click",
    "target": [628, 727, 15, 18]
}
```

此处 `target` 可能被解释为识别时的 ROI 约束（将搜索区域限制为 [628,727,15,18]），导致搜索区域与 roi 不重叠而匹配失败。应使用 nested 格式明确区分：

```json
"关闭搜索": {
    "recognition": "TemplateMatch",
    "template": "搜索.png",
    "roi": [255, 1138, 217, 142],
    "action": "Click",
    "target": true,
    "action_target": [628, 727, 15, 18]
}
```
