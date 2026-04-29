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
