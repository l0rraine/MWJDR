package utils

import (
	"encoding/json"
	"os"
	"path/filepath"

	"github.com/MaaXYZ/maa-framework-go/v4"
)

// MFAAvalonia 实例配置读取
// 环境变量: MFA_INSTANCE_ID / MFA_INSTANCE_NAME / MFA_DATA_ROOT
// 实例配置文件: {MFA_DATA_ROOT}/config/instances/{MFA_INSTANCE_ID}.json

// 战斗任务的 entry 名称(对应 interface.json 中 task[].entry)
var battleTaskEntries = map[string]bool{
	"自动集结_巨兽入口":   true, // 集结巨兽
	"自动野兽_入口":     true, // 自动野兽
	"灯塔入口":        true, // 自动灯塔
	"集结物品_识别体力入口": true, // 使用物品集结
}

func GetInstanceID() string {
	return os.Getenv("MFA_INSTANCE_ID")
}

func GetDataRoot() string {
	dataRoot := os.Getenv("MFA_DATA_ROOT")
	if dataRoot != "" {
		if st, err := os.Stat(dataRoot); err == nil && st.IsDir() {
			return dataRoot
		}
	}
	return ""
}

// findInstanceConfig 查找实例配置文件: 1. MFA_DATA_ROOT 2. 项目根目录向上搜索
func findInstanceConfig(instanceID string) string {
	if dataRoot := GetDataRoot(); dataRoot != "" {
		p := filepath.Join(dataRoot, "config", "instances", instanceID+".json")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	// 策略2: 从 agent-go/ 向上搜索(替代 Python 的 __file__ 推导)
	exe, err := os.Executable()
	if err != nil {
		return ""
	}
	dir := filepath.Dir(exe)
	for i := 0; i < 5; i++ {
		p := filepath.Join(dir, "config", "instances", instanceID+".json")
		if _, err := os.Stat(p); err == nil {
			return p
		}
		dir = filepath.Dir(dir)
	}
	return ""
}

// HasBattleTasks 检查当前实例是否启用了战斗任务
// 返回 (结果, 是否可判断);ok=false 表示非 MFAAvalonia 环境或读取失败
func HasBattleTasks() (bool, bool) {
	instanceID := GetInstanceID()
	if instanceID == "" {
		Debug("非 MFAAvalonia 环境,无法判断战斗任务")
		return false, false
	}
	configPath := findInstanceConfig(instanceID)
	if configPath == "" {
		Warningf("未找到实例配置文件: instance_id=%s", instanceID)
		return false, false
	}
	raw, err := os.ReadFile(configPath)
	if err != nil {
		Warningf("读取实例配置失败: %v", err)
		return false, false
	}
	var config map[string]any
	if err := json.Unmarshal(raw, &config); err != nil {
		Warningf("解析实例配置失败: %v", err)
		return false, false
	}

	taskItems, _ := config["TaskItems"].([]any)
	if len(taskItems) == 0 {
		Debug("实例配置中无 TaskItems")
		return false, false
	}

	for _, t := range taskItems {
		task, ok := t.(map[string]any)
		if !ok {
			continue
		}
		entry, _ := task["entry"].(string)
		if !battleTaskEntries[entry] {
			continue
		}
		defaultCheck, _ := task["default_check"].(bool)
		if defaultCheck {
			name, _ := task["name"].(string)
			Debugf("发现已启用的战斗任务: %s", name)
			return true, true
		}
	}
	return false, true
}

// DisableBattleTasks 体力耗尽时,自动禁用当前任务之后已启用的战斗任务
// 返回 true 表示成功禁用
func DisableBattleTasks(ctx *maa.Context, currentEntry string) bool {
	instanceID := GetInstanceID()
	if instanceID == "" {
		Debug("非 MFAAvalonia 环境,跳过禁用战斗任务")
		return false
	}
	configPath := findInstanceConfig(instanceID)
	if configPath == "" {
		Warningf("未找到实例配置文件,无法禁用战斗任务: instance_id=%s", instanceID)
		return false
	}
	raw, err := os.ReadFile(configPath)
	if err != nil {
		Warningf("读取实例配置失败,无法禁用战斗任务: %v", err)
		return false
	}
	var config map[string]any
	if err := json.Unmarshal(raw, &config); err != nil {
		Warningf("解析实例配置失败,无法禁用战斗任务: %v", err)
		return false
	}

	taskItems, _ := config["TaskItems"].([]any)
	if len(taskItems) == 0 {
		return false
	}

	// 查找当前任务位置
	currentIndex := -1
	for i, t := range taskItems {
		if task, ok := t.(map[string]any); ok {
			if entry, _ := task["entry"].(string); entry == currentEntry {
				currentIndex = i
				break
			}
		}
	}
	if currentIndex == -1 {
		Warningf("未在配置文件中找到当前任务 '%s',将禁用所有已启用的战斗任务", currentEntry)
	}

	// 禁用当前任务之后的战斗任务
	disabled := make([]string, 0)
	for i, t := range taskItems {
		task, ok := t.(map[string]any)
		if !ok {
			continue
		}
		entry, _ := task["entry"].(string)
		if currentIndex != -1 && i <= currentIndex {
			continue
		}
		if !battleTaskEntries[entry] {
			continue
		}
		if defaultCheck, _ := task["default_check"].(bool); defaultCheck {
			_ = ctx.GetTasker().GetResource().OverridePipeline(
				map[string]any{entry: map[string]any{"enabled": false}})
			Infof("已自动禁用战斗任务: %s", entry)
			name, _ := task["name"].(string)
			disabled = append(disabled, name)
		}
	}

	if len(disabled) == 0 {
		Debug("没有需要禁用的战斗任务")
		return false
	}
	Infof("体力耗尽,已自动禁用后续战斗任务: %v", disabled)
	return true
}
