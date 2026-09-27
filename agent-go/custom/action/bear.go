package action

import (
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// 打熊相关全局状态(替代 Python bear.py 模块级变量)
var (
	bearStartTime        = "21:00"
	bearTruck1           []string // 大车头
	bearTruck2           []string // 小车头
	bearTeamOrder        []int
	bearSendTeams        = 0
	bearTotalTeams       = 0
	bearLastStage        = 0
	bearReserveTeam      = 1
	bearFoundLeadTruck   = map[string]float64{}
	bearCurrentTruck     = ""
	bearOver40sNotified  = map[string]bool{}
	bearLeadTruckOfStage = 0
)

const stageSeconds = 5*60 + 14 // 314 秒

// RegisterBearActions 注册打熊相关 action
func RegisterBearActions() {
	_ = maa.AgentServerRegisterCustomAction("熊_无剩余队列",
		maa.CustomActionFunc(bearSetSendTeams))
	_ = maa.AgentServerRegisterCustomAction("熊_初始化参数",
		maa.CustomActionFunc(bearInitPara))
	_ = maa.AgentServerRegisterCustomAction("熊_计算队伍",
		maa.CustomActionFunc(bearComputeTeam))
	_ = maa.AgentServerRegisterCustomAction("熊_记录队伍",
		maa.CustomActionFunc(bearRecordTeam))
	_ = maa.AgentServerRegisterCustomAction("熊_加入集结",
		maa.CustomActionFunc(bearJoinGather))
}

func parseHHMM(s string) (int, int) {
	parts := strings.Split(s, ":")
	h, m := 0, 0
	if len(parts) > 0 {
		h = atoiLocal(parts[0])
	}
	if len(parts) > 1 {
		m = atoiLocal(parts[1])
	}
	return h, m
}

func bearStageStart(startTimeStr string) time.Time {
	now := time.Now()
	h, m := parseHHMM(startTimeStr)
	return time.Date(now.Year(), now.Month(), now.Day(), h, m, 0, 0, time.Local)
}

// getCurrentStage 计算当前阶段(默认 21:00 开始,每 314 秒一轮)
func getCurrentStage(startTime string) int {
	start := bearStageStart(startTime)
	now := time.Now()
	totalSeconds := now.Sub(start).Seconds()
	if totalSeconds < 0 {
		return 1 // 还没开始
	}
	currentStage := int(math.Ceil(totalSeconds / stageSeconds))
	if currentStage < 1 {
		currentStage = 1
	}
	return currentStage
}

// nextStageSeconds 距下一阶段的秒数
func nextStageSeconds() float64 {
	start := bearStageStart(bearStartTime)
	now := time.Now()
	totalSeconds := now.Sub(start).Seconds()
	nextStage := math.Ceil(totalSeconds / stageSeconds)
	nextStageTime := start.Add(time.Duration(nextStage*stageSeconds) * time.Second)
	return nextStageTime.Sub(now).Seconds()
}

// 熊_无剩余队列
func bearSetSendTeams(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	// SEND_TEAMS = TOTAL_TEAMS(已注释,保持为空实现)
	return true
}

// 熊_初始化参数
func bearInitPara(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	startTimeStr := jsonParamStr(arg.CustomActionParam, "开始时间")
	if startTimeStr == "" {
		startTimeStr = "21:00"
	}
	leadNames := jsonParamStr(arg.CustomActionParam, "大车头")
	secondaryNames := jsonParamStr(arg.CustomActionParam, "小车头")
	bearStartTime = startTimeStr

	teamOrderStr := jsonParamStr(arg.CustomActionParam, "循环顺序")
	if teamOrderStr == "" {
		teamOrderStr = "0"
	}
	if len(bearTeamOrder) == 0 {
		bearTeamOrder = nil
		for _, x := range strings.Split(teamOrderStr, ",") {
			x = strings.TrimSpace(x)
			if x != "" {
				bearTeamOrder = append(bearTeamOrder, atoiLocal(x))
			}
		}
	}

	bearTruck1 = splitNames(leadNames)
	bearTruck2 = splitNames(secondaryNames)

	expected1 := make([]string, 0, len(bearTruck1))
	for _, name := range bearTruck1 {
		expected1 = append(expected1, `.*`+regexpQuote(name)+`.*`)
	}
	pipeline := map[string]any{
		"熊_识别队伍_大车头": map[string]any{
			"all_of": []any{
				map[string]any{
					"sub_name":    "team_name",
					"recognition": "OCR",
					"roi":         []int{273, 170, 252, 956},
					"expected":    expected1,
				},
				map[string]any{
					"sub_name":    "join",
					"recognition": "TemplateMatch",
					"template":    "熊/直接加入队伍.png",
					"roi":         "team_name",
					"roi_offset":  []int{310, 87, 0, 58},
					"threshold":   0.9,
					"method":      10001,
				},
			},
		},
	}
	_ = ctx.OverridePipeline(pipeline)
	_ = ctx.GetTasker().GetResource().OverridePipeline(pipeline)

	expected2 := make([]string, 0, len(bearTruck2))
	for _, name := range bearTruck2 {
		expected2 = append(expected2, `.*`+regexpQuote(name)+`.*`)
	}
	pipeline2 := map[string]any{
		"熊_识别队伍_普通车头": map[string]any{
			"all_of": []any{
				map[string]any{
					"sub_name":    "team_name",
					"recognition": "OCR",
					"roi":         []int{273, 170, 252, 956},
					"expected":    expected2,
				},
				map[string]any{
					"sub_name":    "join",
					"recognition": "TemplateMatch",
					"template":    "熊/直接加入队伍.png",
					"roi":         "team_name",
					"roi_offset":  []int{310, 87, 0, 58},
					"threshold":   0.9,
					"method":      10001,
				},
			},
		},
	}
	_ = ctx.OverridePipeline(pipeline2)
	_ = ctx.GetTasker().GetResource().OverridePipeline(pipeline2)

	return true
}

// 熊_计算队伍
func bearComputeTeam(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	currentStage := getCurrentStage(bearStartTime)

	if currentStage > bearLastStage {
		utils.Infof("当前为第 %d 轮", currentStage)
		bearLastStage = currentStage
		bearSendTeams = 0
		bearLeadTruckOfStage = 0
		bearOver40sNotified = map[string]bool{}
	}

	if currentStage > 5 {
		utils.Info("打熊已结束")
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{})
		return true
	}

	bearReserveTeam = 0
	bearTotalTeams = len(bearTeamOrder) - bearReserveTeam

	if bearSendTeams == bearTotalTeams {
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_大车头": map[string]any{"enabled": false}})
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_普通车头": map[string]any{"enabled": false}})
	} else {
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_大车头": map[string]any{"enabled": true}})
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_普通车头": map[string]any{"enabled": true}})
	}

	return true
}

// 熊_记录队伍(对应 Python 第一个 BearCombat)
func bearRecordTeam(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	start := time.Now()

	detail := arg.RecognitionDetail
	if detail == nil {
		utils.Warning("熊_记录队伍: 无识别详情")
		return true
	}
	// all_of 组合识别:CombinedResult 顺序与 all_of 列表一致
	var teamResult, joinResult *maa.RecognitionDetail
	if len(detail.CombinedResult) >= 2 {
		teamResult = detail.CombinedResult[0]
		joinResult = detail.CombinedResult[1]
	} else if detail.Results != nil && detail.Results.Best != nil {
		// 兜底(理论上不会走到)
		utils.Warning("熊_记录队伍: 组合识别结果缺失")
		return true
	}

	joinBox := joinResult.Box
	box := maa.Rect{joinBox[0] + 5, joinBox[1] + 5, joinBox[2] - 10, joinBox[3] - 10}

	currentStage := getCurrentStage(bearStartTime)

	teamText := utils.BestText(teamResult)
	truck := ""
	for _, s := range append(append([]string{}, bearTruck1...), bearTruck2...) {
		if strings.Contains(teamText, s) {
			truck = s
			break
		}
	}
	bearCurrentTruck = truck
	k := truck + "_" + itoa(currentStage)
	if truck != "" {
		if _, exists := bearFoundLeadTruck[k]; !exists {
			bearFoundLeadTruck[k] = nextStageSeconds()
			bearLeadTruckOfStage++
			utils.Debugf("第%d轮: 发现大车头 %s, 现有大车头 %d",
				currentStage, truck, bearLeadTruckOfStage)
		}
	}

	teamsExhausted := bearSendTeams >= bearTotalTeams
	if !teamsExhausted {
		n := map[string]any{
			"next": []string{
				"熊_在队伍选择页面",
				"熊_在集结详情页面",
				"熊_士兵超出上限",
				"熊_队列不足",
				"熊_超出容量",
			},
		}
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_大车头": n})
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_普通车头": n})
		utils.ClickRect(ctx, box)
	} else {
		n := map[string]any{"next": []string{"熊_开始战斗"}}
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_大车头": n})
		_ = ctx.OverridePipeline(map[string]any{"熊_识别队伍_普通车头": n})
	}

	utils.Debugf("熊_记录队伍 click_rect 耗时: %.2f 秒", time.Since(start).Seconds())
	return true
}

// 熊_加入集结(对应 Python 第二个 BearCombat)
func bearJoinGather(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	if len(bearTeamOrder) == 0 {
		return true
	}
	if bearSelectTeamAndDeploy(ctx, bearTeamOrder[0]) {
		// [1,2,3,4] → [2,3,4,1]
		first := bearTeamOrder[0]
		bearTeamOrder = append(bearTeamOrder[1:], first)
	}
	return true
}

// bearSelectTeamAndDeploy 选择队伍并点击出征,返回是否成功出征并返回集结列表
func bearSelectTeamAndDeploy(ctx *maa.Context, teamID int) bool {
	if teamID > 0 && teamID < len(teamROI) {
		roi := teamROI[teamID]
		_, _ = ctx.RunAction("熊_选择队伍", maa.Rect{}, "",
			map[string]any{"熊_选择队伍": map[string]any{"target": roi}})
	}
	_, _ = ctx.RunAction("熊_点击出征", maa.Rect{}, "", nil)

	time.Sleep(300 * time.Millisecond)
	img, _ := utils.ScreenCap(ctx)
	detail, _ := ctx.RunRecognition("熊_在集结列表", img)
	if detail != nil && detail.Hit {
		bearSendTeams++
		utils.Infof("%d 号队伍已加入 %s", teamID, bearCurrentTruck)
		return true
	}
	return false
}

func splitNames(s string) []string {
	out := make([]string, 0)
	for _, name := range strings.Split(s, ",") {
		name = strings.TrimSpace(name)
		if name != "" {
			out = append(out, name)
		}
	}
	return out
}

func regexpQuote(s string) string {
	var b strings.Builder
	for _, r := range s {
		if strings.ContainsRune(`\.+*?()|[]{}^$`, r) {
			b.WriteByte('\\')
		}
		b.WriteRune(r)
	}
	return b.String()
}

func itoa(n int) string {
	return strconv.Itoa(n)
}
