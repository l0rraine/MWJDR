package action

import (
	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// 当前使用的队伍编号(替代 Python garrison.py 全局变量)
var garrisonTeam = 1

// RegisterGarrisonActions 注册王城驻防相关 action 与 recognition
func RegisterGarrisonActions() {
	_ = maa.AgentServerRegisterCustomAction("王城驻防_设置间隔",
		maa.CustomActionFunc(garrisonSetInterval))
	_ = maa.AgentServerRegisterCustomRecognition("王城驻防_检测",
		maa.CustomRecognitionFunc(garrisonDetect))
	_ = maa.AgentServerRegisterCustomAction("王城驻防_选队出征",
		maa.CustomActionFunc(garrisonDeploy))
}

// 王城驻防_设置间隔:秒 → 毫秒,override 王城驻防_等待.pre_delay
func garrisonSetInterval(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	interval := jsonParamInt(arg.CustomActionParam, "interval", 60)
	_ = ctx.OverridePipeline(map[string]any{
		"王城驻防_等待": map[string]any{"pre_delay": interval * 1000},
	})
	return true
}

// 王城驻防_检测:队列不满 + 存在驻防按钮时返回 box
func garrisonDetect(ctx *maa.Context, arg *maa.CustomRecognitionArg) (*maa.CustomRecognitionResult, bool) {
	// 队列判断:直接读 QueueStatus 缓存
	if utils.Queue.IsFull() {
		return nil, true
	}

	// 模板匹配驻防按钮
	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return nil, true
	}
	detail, _ := ctx.RunRecognition("王城驻防_识别按钮", img,
		map[string]any{
			"王城驻防_识别按钮": map[string]any{
				"recognition": "TemplateMatch",
				"template":    "驻防.png",
				"roi":         []int{7, 230, 56, 373},
				"threshold":   0.8,
			},
		})
	if detail == nil || !detail.Hit {
		return nil, true
	}

	return &maa.CustomRecognitionResult{Box: detail.Box, Detail: ""}, true
}

// 王城驻防_选队出征
func garrisonDeploy(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	team := jsonParamInt(arg.CustomActionParam, "team", 0)
	garrisonTeam = team

	// 选队
	if garrisonTeam > 0 && garrisonTeam < len(teamROI) {
		_, _ = ctx.RunAction("王城驻防_选择队伍", maa.Rect{}, "",
			map[string]any{"王城驻防_选择队伍": map[string]any{"target": teamROI[garrisonTeam]}})
	}
	// 点击出征
	_, _ = ctx.RunAction("王城驻防_点击出征", maa.Rect{}, "", nil)
	utils.Infof("王城驻防: 已派遣,队伍=%d", garrisonTeam)
	return true
}
