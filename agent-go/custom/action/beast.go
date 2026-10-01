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
			utils.DisableBattleTasks(ctx, "自动野兽_入口")
			stopBeastTask(ctx)
			return true
		}
	}

	time.Sleep(time.Duration(returnTime*2)*time.Second + 500*time.Millisecond)
	return true
}

// stopBeastTask 终止自动野兽任务:禁用"自动野兽_入口"("自动野兽_准备出征"的 next 唯一引用),
// 使 next 列表全部失效,核心 error handling 立即终止,不再弹栈重跑。
// 不能依赖 OverrideNext(空):入口链路经 [JumpBack] 节点压栈,next 为空会弹栈回入口重跑。
func stopBeastTask(ctx *maa.Context) {
	_ = ctx.OverridePipeline(map[string]any{"自动野兽_入口": map[string]any{"enabled": false}})
}
