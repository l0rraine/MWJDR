package action

import (
	"math/rand"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// RegisterTravelActions 注册自动游历相关 action
func RegisterTravelActions() {
	_ = maa.AgentServerRegisterCustomAction("挖掘宝藏",
		maa.CustomActionFunc(doDig))
	_ = maa.AgentServerRegisterCustomAction("米娅宝藏",
		maa.CustomActionFunc(miaTreasure))
}

// 挖掘宝藏
func doDig(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	board := [8][4]int{
		{279, 729, 77, 77}, {280, 812, 78, 75}, {283, 893, 72, 74}, {200, 894, 76, 73},
		{364, 812, 74, 72}, {362, 894, 76, 72}, {361, 975, 79, 74}, {445, 814, 75, 73},
	}
	for i := 0; i < 8; i++ {
		utils.Debugf("查看地块%d", i+1)
		img, err := utils.ScreenCap(ctx)
		if err != nil {
			continue
		}
		detail, _ := ctx.RunRecognition("自动游历_挖宝_空白地块", img,
			map[string]any{"自动游历_挖宝_空白地块": map[string]any{"roi": board[i]}})
		if detail != nil && detail.Hit {
			utils.ClickRect(ctx, detail.Box)
			utils.Debugf("点击地块%d", i+1)
			time.Sleep(1 * time.Second)
		}
	}
	return true
}

// 米娅宝藏:随机选 6 个点点击
func miaTreasure(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	board := [10][4]int{
		{175, 801, 46, 45}, {338, 808, 46, 46}, {503, 815, 37, 40}, {90, 949, 48, 45},
		{250, 951, 60, 39}, {423, 950, 39, 38}, {580, 959, 39, 30}, {172, 1094, 39, 34},
		{336, 1088, 41, 48}, {510, 1090, 36, 39},
	}
	// random.sample(board, 6):不放回抽样
	perm := rand.Perm(len(board))
	selected := make([][4]int, 0, 6)
	for _, idx := range perm[:6] {
		selected = append(selected, board[idx])
	}
	utils.Debugf("selected: %v", selected)
	for _, item := range selected {
		utils.ClickRect(ctx, item)
		time.Sleep(300 * time.Millisecond)
	}
	return true
}
