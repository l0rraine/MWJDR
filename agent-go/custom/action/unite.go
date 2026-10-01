package action

import (
	"encoding/json"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// RegisterUniteActions 注册联盟总动员 action
func RegisterUniteActions() {
	_ = maa.AgentServerRegisterCustomAction("联盟总动员_扫描",
		maa.CustomActionFunc(uniteScan))
}

// 联盟总动员_扫描
func uniteScan(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	leftSlot := NodeEnabled(ctx, "联盟总动员_参数_是否启用第一栏位")
	rightSlot := NodeEnabled(ctx, "联盟总动员_参数_是否启用第二栏位")

	slotList := make([]int, 0, 2)
	if leftSlot {
		slotList = append(slotList, 0)
	}
	if rightSlot {
		slotList = append(slotList, 1)
	}
	utils.Debugf("栏位启用状态: 左=%v, 右=%v", leftSlot, rightSlot)

	questROI := [2][4]int{{138, 656, 115, 85}, {472, 666, 106, 71}}
	rateROI := [2][4]int{{27, 577, 113, 120}, {346, 576, 108, 113}}
	timeROI := [2][4]int{{161, 652, 123, 82}, {483, 648, 115, 79}}
	runningROI := [2][4]int{{71, 803, 32, 21}, {394, 803, 32, 21}}
	_ = questROI

	img, _ := utils.ScreenCap(ctx)
	detail, _ := ctx.RunRecognition("联盟总动员_巴尔德", img)
	if detail != nil && detail.Hit {
		utils.Debug("发现巴尔德,修正坐标")
		rateROI[0][1] += 60
		rateROI[1][1] += 60
		timeROI[0][1] += 60
		timeROI[1][1] += 60
		runningROI[0][1] += 60
		runningROI[1][1] += 60
	}

	needWaitSeconds := [2]int{86400, 86400}
	for _, i := range slotList {
		utils.Debugf("正在识别%d号位置", i+1)
		img, _ := utils.ScreenCap(ctx)

		detail, _ = ctx.RunRecognition("联盟总动员_识别时间", img,
			map[string]any{"联盟总动员_识别时间": map[string]any{"roi": timeROI[i]}})
		if detail != nil && detail.Hit {
			hours, minutes, seconds := utils.SplitTimeStr(utils.BestText(detail))
			needWaitSeconds[i] = hours*3600 + minutes*60 + seconds
			// 大于5分钟说明此位置任务已做完
			if needWaitSeconds[i] > 300 {
				needWaitSeconds[i] = 86400
			}
			utils.Debugf("%d号位置需要等待%d秒", i+1, needWaitSeconds[i])
			continue
		}

		detail, _ = ctx.RunRecognition("联盟总动员_正在执行", img,
			map[string]any{"联盟总动员_正在执行": map[string]any{"roi": runningROI[i]}})
		if detail != nil && detail.Hit {
			needWaitSeconds[i] = 86400
			utils.Debugf("%d号位置正在执行", i+1)
			continue
		}

		refresh := 0
		matched := ""

		detail, _ = ctx.RunRecognition("联盟总动员_识别200%倍率", img,
			map[string]any{"联盟总动员_识别200%倍率": map[string]any{"roi": rateROI[i]}})
		rate := "120%"
		if detail != nil && detail.Hit {
			rate = "200%"
		}

		// 确保接下来处于任务详情页面
		_, _ = ctx.RunActionDirect(maa.ActionTypeClick,
			&maa.ClickParam{Target: maa.NewTargetRect(timeROI[i])}, maa.Rect{}, nil)

		// 读取启用任务的 expected 列表
		flattened := uniteEnabledExpected(ctx)
		if len(flattened) == 0 {
			refresh = 1
		} else {
			img, _ = utils.ScreenCap(ctx)
			detail, _ = ctx.RunRecognition("联盟总动员_识别描述", img,
				map[string]any{"联盟总动员_识别描述": map[string]any{"expected": flattened}})
			if detail == nil || !detail.Hit {
				refresh = 1
			} else {
				matched = utils.BestText(detail)
				needWaitSeconds[i] = 86400
			}
		}

		if refresh == 1 {
			utils.Debugf("开始刷新位置%d", i+1)
			_, _ = ctx.RunTask("联盟总动员_开始刷新")
			detail = nil
			for detail == nil || !detail.Hit {
				img, _ := utils.ScreenCap(ctx)
				detail, _ = ctx.RunRecognition("联盟总动员_识别时间", img,
					map[string]any{"联盟总动员_识别时间": map[string]any{"roi": timeROI[i]}})
				time.Sleep(1 * time.Second)
			}
			_, minutes, seconds := utils.SplitTimeStr(utils.BestText(detail))
			needWaitSeconds[i] = minutes*60 + seconds
			utils.Debugf("%d号位置需要等待:%d:%d,共计%d秒", i+1, minutes, seconds, needWaitSeconds[i])
		} else {
			utils.Infof("%d号位置已刷新出%s,倍率%s", i+1, matched, rate)
			_, _ = ctx.RunTask("点击左上角")
		}
	}

	if minInt(needWaitSeconds[0], needWaitSeconds[1]) != 86400 {
		utils.Debugf("开始等待%d秒", minInt(needWaitSeconds[0], needWaitSeconds[1]))
		time.Sleep(time.Duration(minInt(needWaitSeconds[0], needWaitSeconds[1])) * time.Second)
		return true
	}
	utils.Info("已全部得到满意的结果,停止刷新")
	stopUniteTask(ctx)
	return true
}

// stopUniteTask 终止当前联盟总动员流程:禁用入口节点,使"联盟总动员_执行扫描"的 next 列表
// 全部失效,核心 run_reco_and_action 返回无效 NodeDetail 进入 error handling,任务立即终止。
// 不能依赖 OverrideNext(空列表):入口链路经 [JumpBack]联盟总动员_点击活动 等节点压栈,
// next 为空会弹栈回到入口白跑一轮(每轮弹1个),直到栈耗尽才停——这正是"已全部满意后
// 仍重复查看任务几次"的原因;栈内残留条目耗尽前任务不会终止。
func stopUniteTask(ctx *maa.Context) {
	_ = ctx.OverridePipeline(map[string]any{"联盟总动员_入口": map[string]any{"enabled": false}})
}

// uniteEnabledExpected 收集所有启用任务的 OCR expected 文本(flattened)
func uniteEnabledExpected(ctx *maa.Context) []string {
	out := make([]string, 0)
	for _, name := range NodeNextNames(ctx, "联盟总动员_点击详情") {
		raw, err := ctx.GetNodeJSON(name)
		if err != nil {
			continue
		}
		var node map[string]any
		if err := json.Unmarshal([]byte(raw), &node); err != nil {
			continue
		}
		if enabled, _ := node["enabled"].(bool); !enabled {
			continue
		}
		recog, _ := node["recognition"].(map[string]any)
		param, _ := recog["param"].(map[string]any)
		exp, _ := param["expected"].([]any)
		for _, e := range exp {
			if s, ok := e.(string); ok {
				out = append(out, s)
			}
		}
	}
	return out
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
