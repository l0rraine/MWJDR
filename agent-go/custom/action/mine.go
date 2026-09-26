package action

import (
	"image"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// 挖矿相关全局状态(替代 Python mine.py 模块级变量)
var (
	mineRecallRegion = [6][4]int{
		{200, 544, 43, 56}, {200, 484, 43, 56}, {200, 424, 43, 56},
		{200, 364, 43, 56}, {200, 304, 43, 56}, {200, 244, 43, 56},
	}
	lastMines      []string
	currentMines   []string
	nextMine       = ""
	maxMineTeams   = 4
	allMines       = []string{"肉", "木", "煤", "铁"}
	mines          = append([]string{}, allMines...)
	lastWrongHeroT int64 // unix 秒
	mineLevel      = 0
	mineNodeMap    = map[string]string{
		"挖矿_矿_肉": "肉",
		"挖矿_矿_木": "木",
		"挖矿_矿_煤": "煤",
		"挖矿_矿_铁": "铁",
	}
)

// RegisterMineActions 注册挖矿相关 action 与 recognition
func RegisterMineActions() {
	_ = maa.AgentServerRegisterCustomRecognition("挖矿_去掉英雄识别",
		maa.CustomRecognitionFunc(mineRemoveHeroReco))
	_ = maa.AgentServerRegisterCustomRecognition("挖矿_识别队伍",
		maa.CustomRecognitionFunc(mineRecoTeam))
	_ = maa.AgentServerRegisterCustomRecognition("挖矿_识别矿图标",
		maa.CustomRecognitionFunc(mineRecoMine))
	_ = maa.AgentServerRegisterCustomAction("挖矿_设置等级",
		maa.CustomActionFunc(mineSetLevel))
	_ = maa.AgentServerRegisterCustomAction("挖矿_降级搜索",
		maa.CustomActionFunc(mineDowngradeSearch))
}

// readMineConfig 读取用户勾选的矿种 MINES
func readMineConfig(ctx *maa.Context) {
	m := make([]string, 0)
	defer func() {
		if r := recover(); r != nil {
			m = nil
		}
	}()
	for _, name := range NodeNextNames(ctx, "挖矿_矿种选项") {
		if name == "" {
			continue
		}
		mineName, ok := mineNodeMap[name]
		if !ok {
			continue
		}
		if NodeEnabled(ctx, name) {
			m = append(m, mineName)
		}
	}
	if len(m) > 0 {
		mines = m
	} else {
		mines = append([]string{}, allMines...)
	}
}

// getCurrentMines 识别当前正在挖的矿
func getCurrentMines(ctx *maa.Context, img image.Image) []string {
	m := make([]string, 0)
	for _, mineName := range mines {
		d, _ := ctx.RunRecognition("挖矿_识别在挖矿", img,
			map[string]any{
				"挖矿_识别在挖矿": map[string]any{
					"recognition": "TemplateMatch",
					"template":    mineName + ".png",
					"roi":         []int{12, 248, 45, 361},
					"threshold":   0.8,
				},
			})
		if d != nil && d.Hit {
			m = append(m, mineName)
		}
	}
	return m
}

// 挖矿_去掉英雄识别:识别是否有英雄,无英雄时记录时间
func mineRemoveHeroReco(ctx *maa.Context, arg *maa.CustomRecognitionArg) (*maa.CustomRecognitionResult, bool) {
	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return nil, true
	}
	detail, _ := ctx.RunRecognition("挖矿_英雄颜色", img,
		map[string]any{
			"挖矿_英雄颜色": map[string]any{
				"recognition": "ColorMatch",
				"roi":         []int{99, 352, 14, 14},
				"upper":       []int{96, 160, 223},
				"lower":       []int{87, 152, 219},
			},
		})
	if detail != nil && detail.Hit {
		return &maa.CustomRecognitionResult{Box: detail.Box, Detail: ""}, true
	}
	lastWrongHeroT = time.Now().Unix()
	utils.Debugf("未识别到英雄颜色,记录时间 %d", lastWrongHeroT)
	return nil, true
}

// 挖矿_识别队伍
func mineRecoTeam(ctx *maa.Context, arg *maa.CustomRecognitionArg) (*maa.CustomRecognitionResult, bool) {
	// 距离上次识别失败不足1分钟,直接返回失败
	if lastWrongHeroT > 0 && time.Since(time.Unix(lastWrongHeroT, 0)) < 60*time.Second {
		utils.Debugf("距离上次英雄识别失败仅 %.1fs,跳过挖矿",
			time.Since(time.Unix(lastWrongHeroT, 0)).Seconds())
		return nil, true
	}

	// 读取队伍上限 max_teams
	maxMineTeams = jsonParamInt(arg.CustomRecognitionParam, "max_teams", 4)

	// 读取用户勾选的矿种
	readMineConfig(ctx)

	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return nil, true
	}

	if len(lastMines) == 0 {
		lastMines = getCurrentMines(ctx, img)
	}

	// 队列判断
	if utils.Queue.IsFull() {
		return nil, true
	}
	if utils.Queue.IfFail == 1 {
		return nil, true
	}

	currentMines = nil
	currentMines = getCurrentMines(ctx, img)

	if len(currentMines) >= maxMineTeams {
		if len(lastMines) == 0 {
			lastMines = append([]string{}, currentMines...)
		}
		return nil, true
	}

	nextMine = ""
	freeMines := make([]string, 0)
	for _, mineName := range mines {
		if !containsStr(currentMines, mineName) {
			freeMines = append(freeMines, mineName)
		}
	}

	for _, mineName := range freeMines {
		if !containsStr(lastMines, mineName) {
			nextMine = mineName
			break
		}
	}
	if nextMine == "" && len(freeMines) > 0 {
		nextMine = freeMines[0]
	}

	if nextMine != "" {
		utils.Debugf("LAST_MINES=%v,CURRENT_MINES=%v", lastMines, currentMines)
		utils.Infof("派出挖矿队伍:%s", nextMine)
		currentMines = append(currentMines, nextMine)
		lastMines = append([]string{}, currentMines...)
		// 返回任意非 None box 表示命中
		return &maa.CustomRecognitionResult{Box: maa.Rect{0, 0, 1, 1}, Detail: ""}, true
	}
	return nil, true
}

// 挖矿_识别矿图标
func mineRecoMine(ctx *maa.Context, arg *maa.CustomRecognitionArg) (*maa.CustomRecognitionResult, bool) {
	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return nil, true
	}
	detail, _ := ctx.RunRecognition("识别要挖的矿", img,
		map[string]any{
			"识别要挖的矿": map[string]any{
				"recognition": "TemplateMatch",
				"roi":         []int{86, 820, 634, 176},
				"template":    nextMine + "矿.png",
			},
		})
	if detail == nil {
		return nil, true
	}
	return &maa.CustomRecognitionResult{Box: detail.Box, Detail: ""}, true
}

// 挖矿_设置等级:调整矿等级至默认值并搜索
func mineSetLevel(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	_, err := utils.ScreenCap(ctx)
	if err != nil {
		return true
	}

	text, _ := utils.OcrUntilConsistentByTask(ctx, "挖矿_识别矿等级",
		map[string]any{
			"挖矿_识别矿等级": map[string]any{
				"recognition": "OCR",
				"expected":    `\d+`,
				"roi":         []int{584, 1029, 44, 48},
			},
		}, `\d`, 0, 0)
	mineLevel = atoiLocal(text)
	if mineLevel == 0 {
		mineLevel = 1
	}

	defaultLevel := jsonParamInt(arg.CustomActionParam, "level", 8)
	utils.Debugf("挖矿_设置等级: %d, 当前等级=%d", defaultLevel, mineLevel)

	decreaseROI := maa.Rect{53, 1042, 33, 28}
	increaseROI := maa.Rect{477, 1046, 16, 15}

	if mineLevel != defaultLevel && mineLevel > 0 {
		diff := 0
		actionName := ""
		if mineLevel > defaultLevel {
			diff = mineLevel - defaultLevel
			actionName = "挖矿_减少等级"
			utils.Infof("矿等级 %d -> %d,减少 %d 次", mineLevel, defaultLevel, diff)
		} else {
			diff = defaultLevel - mineLevel
			actionName = "挖矿_增加等级"
			utils.Infof("矿等级 %d -> %d,增加 %d 次", mineLevel, defaultLevel, diff)
		}
		var roi maa.Rect
		if actionName == "挖矿_减少等级" {
			roi = decreaseROI
		} else {
			roi = increaseROI
		}
		for i := 0; i < diff; i++ {
			_, _ = ctx.RunAction(actionName, maa.Rect{}, "",
				map[string]any{actionName: map[string]any{"action": "Click", "target": roi}})
			time.Sleep(100 * time.Millisecond)
		}
	} else {
		utils.Debugf("矿等级 %d == 默认 %d,无需调整", mineLevel, defaultLevel)
	}

	// 点击搜索按钮
	_, _ = ctx.RunAction("挖矿_点击搜索", maa.Rect{}, "", nil)
	time.Sleep(1 * time.Second)
	return true
}

// 挖矿_降级搜索:点搜索后若未识别到"采集",循环降级搜索
func mineDowngradeSearch(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	if mineTryCollect(ctx) {
		return true
	}

	maxDown := mineLevel
	if maxDown <= 0 {
		maxDown = 8
	}
	downgradeROI := maa.Rect{53, 1042, 33, 28}

	for i := 0; i < maxDown; i++ {
		_, _ = ctx.RunAction("挖矿_降级点击", maa.Rect{}, "",
			map[string]any{"挖矿_降级点击": map[string]any{"action": "Click", "target": downgradeROI}})
		time.Sleep(500 * time.Millisecond)
		_, _ = ctx.RunAction("挖矿_点击搜索", maa.Rect{}, "", nil)
		time.Sleep(1 * time.Second)
		if mineTryCollect(ctx) {
			return true
		}
	}

	utils.Warning("降级搜索超过最大次数仍未识别到采集")
	return true
}

// mineTryCollect 识别"采集"并点击,返回是否识别到
func mineTryCollect(ctx *maa.Context) bool {
	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return false
	}
	detail, _ := ctx.RunRecognition("挖矿_点击采集", img)
	if detail != nil && detail.Hit {
		_, _ = ctx.RunAction("挖矿_点击采集", maa.Rect{}, "",
			map[string]any{"挖矿_点击采集": map[string]any{"target": detail.Box}})
		return true
	}
	return false
}

func containsStr(list []string, s string) bool {
	for _, v := range list {
		if v == s {
			return true
		}
	}
	return false
}
