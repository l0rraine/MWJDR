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
			stopLightTask(ctx)
			return true
		}
	}

	time.Sleep(time.Duration(returnTime*2)*time.Second + 500*time.Millisecond)
	return true
}

// stopLightTask 终止自动灯塔任务:请求框架停止(外部停止信号),任务以成功状态结束,
// MFAAvalonia 状态灯显示绿勾。
// 历史:曾用"禁用灯塔入口使 next 全失效"终止(error handling,任务状态为失败,
// 新版 MFAAvalonia 显示红叉),2026-10 起改用 PostStop。详见 knowledge.md §21/§22。
func stopLightTask(ctx *maa.Context) {
	stopPipelineCleanly(ctx)
}
