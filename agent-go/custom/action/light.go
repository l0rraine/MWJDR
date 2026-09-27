package action

import (
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// RegisterLightActions 注册自动灯塔 action
func RegisterLightActions() {
	_ = maa.AgentServerRegisterCustomAction("灯塔开始出征",
		maa.CustomActionFunc(lightBeginCombat))
}

// 灯塔开始出征
func lightBeginCombat(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	_, minutes, seconds := utils.GetTimeFromOCR(ctx, "识别集结时间", 200)
	returnTime := minutes*60 + seconds
	utils.Debugf("返回时间:%d", returnTime)

	// 开始出征
	_, _ = ctx.RunTask("点击出征")
	time.Sleep(500 * time.Millisecond)

	img, _ := utils.ScreenCap(ctx)
	detail, _ := ctx.RunRecognition("体力不足", img)
	if detail != nil && detail.Hit {
		detail, _ = ctx.RunRecognition("是否有免费体力", img)
		if detail != nil && detail.Hit {
			_, _ = ctx.RunTask("免费体力")
			_, _ = ctx.RunTask("点击出征")
		} else {
			utils.DisableBattleTasks(ctx, "灯塔入口")
			_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
			return true
		}
	}

	time.Sleep(time.Duration(returnTime*2)*time.Second + 500*time.Millisecond)
	return true
}
