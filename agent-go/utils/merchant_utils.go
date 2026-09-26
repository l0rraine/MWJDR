package utils

import (
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"
)

// 任务公共工具函数:商店购买、海岛打理等共享

const TaskCategory = "shopping"

// AddOffset box 与 offset 逐项相加
func AddOffset(box maa.Rect, offset [4]int) [4]int {
	return [4]int{box[0] + offset[0], box[1] + offset[1], box[2] + offset[2], box[3] + offset[3]}
}

// SaveTaskDate 保存任务完成日期到数据文件
func SaveTaskDate(taskName string) {
	accountID := CurrentAccountID()
	data := LoadData()
	tsMs := time.Now().UnixMilli()
	SetTimestamp(data, TaskCategory, accountID, taskName, tsMs)
	if SaveData(data) {
		Debug(taskName + "完成日期已记录")
	} else {
		Warning(taskName + "完成日期记录失败")
	}
}

// DisableSwitch 禁用 pipeline 开关节点
func DisableSwitch(ctx *maa.Context, switchName string) {
	_ = ctx.OverridePipeline(map[string]any{switchName: map[string]any{"enabled": false}})
	_ = ctx.GetTasker().GetResource().OverridePipeline(map[string]any{switchName: map[string]any{"enabled": false}})
}

// DailyCheck 通用每日检查:今日已完成则禁用开关并跳过
// 返回 true 表示今日已完成(应跳过)
func DailyCheck(ctx *maa.Context, taskName, switchName string,
	currentNode, skipNext string) bool {
	accountID := CurrentAccountID()
	data := LoadData()
	ts := GetTimestamp(data, TaskCategory, accountID, taskName)

	if IsToday(ts, "Asia/Shanghai") {
		Infof("%s今日已完成,跳过 (timestamp=%d)", taskName, ts)
		DisableSwitch(ctx, switchName)
		if currentNode != "" && skipNext != "" {
			_ = ctx.OverrideNext(currentNode, []maa.NextItem{{Name: skipNext}})
		}
		return true
	}

	Infof("%s今日未完成,开始执行", taskName)
	return false
}
