package action

import (
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// RegisterMonsterActions 注册集结巨兽相关 action
func RegisterMonsterActions() {
	_ = maa.AgentServerRegisterCustomAction("设置怪兽次数",
		maa.CustomActionFunc(setMonsterCount))
	_ = maa.AgentServerRegisterCustomAction("开始出征",
		maa.CustomActionFunc(beginCombat))
}

// 设置怪兽次数
func setMonsterCount(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	text, _ := utils.OcrUntilConsistentByTask(ctx, "自动集结_识别次数", nil, `\d+`, 0, 0)
	if text == "" {
		utils.Warning("识别怪兽次数失败")
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
		return true
	}
	remaining := atoiLocal(text)
	combatCount.Reset()

	if remaining <= 0 {
		utils.Info("已达到出征次数上限: 10 次,停止出征")
		_, _ = ctx.RunTask("后退")
		time.Sleep(500 * time.Millisecond)
		utils.ClickRect(ctx, maa.Rect{628, 727, 15, 18})
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
		return true
	}
	combatCount.Reset()
	combatCount.Init(remaining)
	utils.Infof("已识别当前怪兽还剩余%d次", remaining)
	_ = ctx.OverridePipeline(map[string]any{"自动集结_查看次数": map[string]any{"enabled": false}})
	_, _ = ctx.RunTask("后退")
	time.Sleep(500 * time.Millisecond)

	// 注:Python 版此处 click_rect 漏传 context(实际不触发);Go 版保留逻辑
	if combatCount.IsReachLimit() {
		utils.ClickRect(ctx, maa.Rect{628, 727, 15, 18})
	}

	return true
}

// 开始出征
func beginCombat(ctx *maa.Context, arg *maa.CustomActionArg) bool {

	repeatLimit := jsonParamInt(arg.CustomActionParam, "出征次数", 0)
	canLimit := jsonParamInt(arg.CustomActionParam, "罐头数量", 0)
	advancedMode := jsonParamInt(arg.CustomActionParam, "高级模式", 0)
	use19Can := 0
	if NodeEnabled(ctx, "自动集结_使用19点罐头") {
		use19Can = 1
	}

	if repeatLimit != 0 {
		combatCount.Init(repeatLimit)
	}
	if canLimit != 0 {
		combatCount.Init(canLimit)
	}

	_, minutes, seconds := utils.GetTimeFromOCR(ctx, "识别集结时间", 200)
	returnTime := minutes*60 + seconds
	utils.Debugf("单次行军耗时:%d", returnTime)

	// 开始出征
	_, _ = ctx.RunTask("点击出征")
	time.Sleep(500 * time.Millisecond)

	img, _ := utils.ScreenCap(ctx)
	detail, _ := ctx.RunRecognition("体力不足", img)
	if detail != nil && detail.Hit {
		utils.Debugf("体力不足,尝试领取免费体力:%s", utils.BestText(detail))
		detail, _ = ctx.RunRecognition("是否有免费体力", img)
		if detail != nil && detail.Hit {
			currentHour := time.Now().Hour()
			canUseFree := false
			if currentHour < 19 {
				canUseFree = true
				utils.Debug("0点~19点,无条件领取免费体力")
			} else {
				if use19Can == 1 {
					canUseFree = true
					utils.Debug("19点罐头选项已启用,领取免费体力")
				} else {
					utils.Debug("19点罐头选项未启用,不领取免费体力")
				}
			}

			if !canUseFree {
				utils.Info("免费罐头未启用,不领取免费体力,停止出征")
				monsterEnd(ctx)
				_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
				return true
			}
			utils.Debug("领取免费体力")
			_, _ = ctx.RunTask("免费体力")
			_, _ = ctx.RunTask("点击出征")
		} else if canLimit != 0 {
			utils.Debug("无免费体力,尝试使用罐头")
			if canLimit > 0 && combatCount.IsReachLimit() {
				utils.Infof("已达到罐头使用次数上限:%d次,停止出征", canLimit)
				monsterEnd(ctx)
				_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
				return true
			}

			text, _ := utils.OcrUntilConsistentByTask(ctx, "识别罐头数量", nil, `\d+([,.]\d+)*`, 0, 0)
			maxCan := 0
			if text != "" {
				maxCan = atoiLocal(stripCommaDot(text))
			}
			if maxCan < 2 {
				utils.Info("罐头已用完")
				monsterEnd(ctx)
				_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
				return true
			}

			c := min(20, combatCount.Limit-combatCount.Count, maxCan)
			_, _ = ctx.RunTask("使用罐头", map[string]any{"使用罐头": map[string]any{"repeat": c}})
			combatCount.AddCount(c)
			utils.Infof("使用罐头 %d 次,当前次数限制为 %d 次", c, combatCount.Count)
			_, _ = ctx.RunTask("点击出征")
		} else if repeatLimit > 0 && advancedMode == 1 && !combatCount.IsReachLimit() {
			text, _ := utils.OcrUntilConsistentByTask(ctx, "识别罐头数量", nil, `\d+([,.]\d+)*`, 0, 0)
			maxCan := 0
			if text != "" {
				maxCan = atoiLocal(stripCommaDot(text))
			}
			utils.Debugf("罐头数量:%d", maxCan)
			if maxCan < 2 {
				utils.Info("罐头已用完")
				monsterEnd(ctx)
				_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
				return true
			}
			c := min(20, (combatCount.Limit-combatCount.Count)*2, maxCan)
			_, _ = ctx.RunTask("使用罐头", map[string]any{"使用罐头": map[string]any{"repeat": c}})
			utils.Infof("使用罐头 %d 次", c)
			_, _ = ctx.RunTask("点击出征")
		} else {
			utils.Debug("无体力,结束")
			monsterEnd(ctx)
			_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
			return false
		}
	}

	img, _ = utils.ScreenCap(ctx)
	detail, _ = ctx.RunRecognition("自动集结_与别人队伍重复", img)
	if detail != nil && detail.Hit {
		utils.ClickRect(ctx, detail.Box)
		return true
	}

	if repeatLimit != 0 {
		combatCount.AddCount(1)
		utils.Infof("已出征 %d 次", combatCount.Count)
	}

	// 80s后查看集结状态
	marchStart := time.Now()
	time.Sleep(80 * time.Second)
	_, _ = ctx.RunTask("转到城外")

	detail = nil
	for detail == nil || !detail.Hit {
		if time.Since(marchStart) >= 181*time.Second {
			utils.Info("已超过3分01秒未识别到行军,认为行军已经开始")
			break
		}
		time.Sleep(1 * time.Second)
		img, _ := utils.ScreenCap(ctx)
		detail, _ = ctx.RunRecognition("自动集结_行军中", img)
	}
	utils.Infof("开始行军,等待 %d 秒", returnTime*2)
	time.Sleep(time.Duration(returnTime*2)*time.Second + 500*time.Millisecond)

	// 判断作战次数是否达到上限
	if repeatLimit != 0 && combatCount.IsReachLimit() {
		if advancedMode == 1 {
			utils.Infof("已达到出征次数上限:%d次,停止出征", combatCount.Limit)
			combatCount.Reset()
			_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
			return true
		}
		utils.Info("已到达次数上限,重新查看次数")
		_ = ctx.OverridePipeline(map[string]any{"自动集结_查看次数": map[string]any{"enabled": true}})
		return true
	}

	return true
}

func monsterEnd(ctx *maa.Context) {
	utils.DisableBattleTasks(ctx, "自动集结_巨兽入口")
	combatCount.Reset()
}

func stripCommaDot(s string) string {
	out := make([]byte, 0, len(s))
	for i := 0; i < len(s); i++ {
		if s[i] != ',' && s[i] != '.' {
			out = append(out, s[i])
		}
	}
	return string(out)
}
