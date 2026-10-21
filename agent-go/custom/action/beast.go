package action

import (
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// RegisterBeastActions 注册自动野兽 action
func RegisterBeastActions() {
	_ = maa.AgentServerRegisterCustomAction("野兽开始出征",
		maa.CustomActionFunc(beastBeginCombat))
}

// 野兽开始出征
func beastBeginCombat(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	utils.Debugf("%v", jsonParam(arg.CustomActionParam))

	_, minutes, seconds := utils.GetTimeFromOCR(ctx, "识别集结时间", 200)
	returnTime := minutes*60 + seconds

	// 开始出征
	_, _ = ctx.RunTask("点击出征")
	time.Sleep(500 * time.Millisecond)

	img, _ := utils.ScreenCap(ctx)
	detail, _ := ctx.RunRecognition("体力不足", img)
	if detail != nil && detail.Hit {
		utils.Debugf("野兽体力不足,尝试领取免费体力:%s", utils.BestText(detail))
		detail, _ = ctx.RunRecognition("是否有免费体力", img)
		if detail != nil && detail.Hit {
			_, _ = ctx.RunTask("免费体力")
			_, _ = ctx.RunTask("点击出征")
		} else {
			utils.Debug("野兽无免费体力,停止出征")
			stopBeastTask(ctx)
			return true
		}
	}

	time.Sleep(time.Duration(returnTime*2)*time.Second + 500*time.Millisecond)
	return true
}

// stopBeastTask 终止自动野兽任务:请求框架停止(外部停止信号),任务以成功状态结束,
// MFAAvalonia 状态灯显示绿勾。
// 历史:曾用"禁用自动野兽_入口使 next 全失效"终止(error handling,任务状态为失败,
// 新版 MFAAvalonia 显示红叉),2026-10 起改用 PostStop。详见 knowledge.md §21/§22。
func stopBeastTask(ctx *maa.Context) {
	stopPipelineCleanly(ctx)
}
