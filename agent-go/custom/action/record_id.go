package action

import (
	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// 角色 ID 的 OCR 区域与格式(替代 Python custom/reco/record_id.py 的类变量)
var (
	idROI     = maa.Rect{343, 893, 167, 44}
	idPattern = `\d+`
)

// RegisterRecordIDActions 注册角色ID相关 action
func RegisterRecordIDActions() {
	_ = maa.AgentServerRegisterCustomAction("开始是否识别角色ID",
		maa.CustomActionFunc(startRecordIDOrNot))
	_ = maa.AgentServerRegisterCustomAction("识别角色ID",
		maa.CustomActionFunc(recordID))
}

// 开始是否识别角色ID:根据是否有战斗任务决定是否识别角色ID
func startRecordIDOrNot(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	battleStatus, ok := utils.HasBattleTasks()
	if ok && battleStatus {
		utils.Debug("后续有战斗任务,跳过识别角色ID")
		_ = ctx.OverridePipeline(map[string]any{"识别角色ID_开始": map[string]any{"enabled": false}})
		_ = ctx.GetTasker().GetResource().OverridePipeline(map[string]any{"识别角色ID_开始": map[string]any{"enabled": false}})
		_ = ctx.GetTasker().GetResource().OverridePipeline(map[string]any{"查看队列_记录角色ID": map[string]any{"enabled": true}})
	} else {
		_ = ctx.OverridePipeline(map[string]any{"识别角色ID_开始": map[string]any{"enabled": true}})
		_ = ctx.GetTasker().GetResource().OverridePipeline(map[string]any{"识别角色ID_开始": map[string]any{"enabled": true}})
		_ = ctx.GetTasker().GetResource().OverridePipeline(map[string]any{"查看队列_记录角色ID": map[string]any{"enabled": false}})
	}
	return true
}

// 识别角色ID
func recordID(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	accountID := utils.OcrUntilConsistent(ctx, idROI, idPattern, 3, 30)
	if accountID != "" {
		utils.AccountID = accountID
		utils.Infof("识别到角色ID:%s", accountID)
	} else {
		utils.Warning("未能识别到角色ID,将使用默认存储")
		utils.AccountID = ""
	}
	return true
}
