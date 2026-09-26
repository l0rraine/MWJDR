package action

import (
	"math"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// RegisterItemBattleActions 注册使用物品集结相关 action
func RegisterItemBattleActions() {
	_ = maa.AgentServerRegisterCustomAction("识别体力",
		maa.CustomActionFunc(recoVigor))
	_ = maa.AgentServerRegisterCustomAction("物品集结",
		maa.CustomActionFunc(itemCombat))
}

// 识别体力
func recoVigor(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	cost := jsonParamInt(arg.CustomActionParam, "体力消耗", 0)
	text := utils.OcrUntilConsistent(ctx, maa.Rect{583, 21, 87, 36}, `\d+`, 3, 30)
	if text == "" {
		utils.Warning("识别体力失败")
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
		return true
	}
	left := atoiLocal(text)
	remaining := int(math.Floor(float64(left) / float64(cost)))
	combatCount.Reset()
	combatCount.Init(remaining)
	utils.Infof("剩余体力:%d,可出征%d次", left, remaining)
	return true
}

// 物品集结
func itemCombat(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	_, _ = utils.ScreenCap(ctx)
	_, minutes, seconds := utils.GetTimeFromOCR(ctx, "识别集结时间", 200)
	returnTime := minutes*60 + seconds
	utils.Debugf("返回时间:%d", returnTime)

	// 开始出征
	_, _ = ctx.RunTask("点击出征")
	time.Sleep(500 * time.Millisecond)

	img, _ := utils.ScreenCap(ctx)
	detail, _ := ctx.RunRecognition("体力不足", img)
	if detail != nil && detail.Hit {
		utils.Debugf("体力不足,尝试领取免费体力:%s", utils.BestText(detail))
		detail, _ = ctx.RunRecognition("是否有免费体力", img)
		if detail != nil && detail.Hit {
			utils.Debug("领取免费体力")
			_, _ = ctx.RunTask("免费体力")
			return true
		}
		utils.Infof("体力耗尽,共使用物品集结 %d次,停止出征", combatCount.Count)
		utils.DisableBattleTasks(ctx, "集结物品_识别体力入口")
		combatCount.Reset()
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
		return true
	}

	combatCount.AddCount(1)
	utils.Infof("已出征 %d 次", combatCount.Count)

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
	utils.Debug("已识别到行军")
	time.Sleep(time.Duration(returnTime*2)*time.Second + 500*time.Millisecond)

	if combatCount.Count >= combatCount.Limit {
		utils.Infof("体力耗尽,共使用物品集结 %d次,停止出征", combatCount.Count)
		utils.DisableBattleTasks(ctx, "集结物品_识别体力入口")
		combatCount.Reset()
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
		return true
	}

	return true
}
