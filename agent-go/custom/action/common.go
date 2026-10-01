package action

import (
	"encoding/json"
	"regexp"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// RegisterCommonActions 注册通用 action 与 recognition
func RegisterCommonActions() {
	_ = maa.AgentServerRegisterCustomRecognition("新手_不可能任务",
		maa.CustomRecognitionFunc(newbieImpossibleTask))
	_ = maa.AgentServerRegisterCustomAction("新手_设置扫描间隔",
		maa.CustomActionFunc(newbieSetInterval))
	_ = maa.AgentServerRegisterCustomAction("根据需要切换角色",
		maa.CustomActionFunc(switchCharacter))
	_ = maa.AgentServerRegisterCustomAction("确保有队列可用",
		maa.CustomActionFunc(makeSureQueueAvailable))
	_ = maa.AgentServerRegisterCustomAction("NodeParaCombine",
		maa.CustomActionFunc(nodeParaCombine))
	_ = maa.AgentServerRegisterCustomAction("DisableNode",
		maa.CustomActionFunc(disableNode))
	_ = maa.AgentServerRegisterCustomAction("NodeOverride",
		maa.CustomActionFunc(nodeOverride))
	_ = maa.AgentServerRegisterCustomAction("每日检查",
		maa.CustomActionFunc(dailyCheckAction))
	_ = maa.AgentServerRegisterCustomAction("记录日期",
		maa.CustomActionFunc(recordDate))
	_ = maa.AgentServerRegisterCustomAction("下午检查",
		maa.CustomActionFunc(afternoonCheck))
	_ = maa.AgentServerRegisterCustomAction("切换队伍",
		maa.CustomActionFunc(changeTeam))
	_ = maa.AgentServerRegisterCustomAction("撤回最后一个队伍",
		maa.CustomActionFunc(recallTeam))
}

// NodeEnabled 读取节点 enabled 状态(默认 false)
func NodeEnabled(ctx *maa.Context, name string) bool {
	node, err := ctx.GetNode(name)
	if err != nil || node == nil || node.Enabled == nil {
		return false
	}
	return *node.Enabled
}

// NodeNextNames 读取节点的 next 列表(兼容 name/string 项),返回节点名列表
func NodeNextNames(ctx *maa.Context, name string) []string {
	raw, err := ctx.GetNodeJSON(name)
	if err != nil {
		return nil
	}
	var node map[string]any
	if err := json.Unmarshal([]byte(raw), &node); err != nil {
		return nil
	}
	next, _ := node["next"].([]any)
	names := make([]string, 0, len(next))
	for _, item := range next {
		switch v := item.(type) {
		case string:
			names = append(names, v)
		case map[string]any:
			if n, ok := v["name"].(string); ok {
				names = append(names, n)
			}
		}
	}
	return names
}

// 新手_不可能任务:始终识别失败的占位节点,主循环每轮调用 QueueStatus.Update
func newbieImpossibleTask(ctx *maa.Context, arg *maa.CustomRecognitionArg) (*maa.CustomRecognitionResult, bool) {
	mine := NodeEnabled(ctx, "挖矿_入口")
	join := NodeEnabled(ctx, "加入集结_入口")
	garrison := NodeEnabled(ctx, "王城驻防_入口")
	if mine || join || garrison {
		utils.Queue.Update(ctx)
	}
	return nil, true // 未命中
}

// 新手_设置扫描间隔:秒 → 毫秒,override 新手_等待.pre_delay
func newbieSetInterval(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	interval := jsonParamInt(arg.CustomActionParam, "interval", 60)
	_ = ctx.OverridePipeline(map[string]any{
		"新手_等待": map[string]any{"pre_delay": interval * 1000},
	})
	return true
}

// 根据需要切换角色
func switchCharacter(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	param := jsonParam(arg.CustomActionParam)
	region := jsonParamStr(arg.CustomActionParam, "王国编号")
	if region == "" {
		region = "3194"
	}
	index := ""
	if v, ok := param["王国内序号"].(string); ok {
		index = v
	}
	utils.Debugf("王国编号:%s,王国内序号:%s", region, index)
	expected := `王国\D+` + regexp.QuoteMeta(region)

	var chaDetail, regionDetail *maa.RecognitionDetail
	count := 3
	for count > 0 && (chaDetail == nil || !chaDetail.Hit) {
		func() {
			defer func() { _ = recover() }()
			img, err := utils.ScreenCap(ctx)
			if err != nil {
				return
			}
			regionDetail, _ = ctx.RunRecognition("国度信息", img,
				map[string]any{"国度信息": map[string]any{"expected": expected}})
			if regionDetail == nil || !regionDetail.Hit {
				utils.Debugf("未找到国度信息,期望值:%s", expected)
			} else {
				utils.Debugf("国度信息:%s", utils.BestText(regionDetail))
				chaDetail, _ = ctx.RunRecognition("选中角色", img,
					map[string]any{
						"选中角色": map[string]any{
							"roi": []int{
								regionDetail.Box[0] + 402,
								regionDetail.Box[1] + 70,
								119,
								231,
							},
						},
					})
				if chaDetail != nil && chaDetail.Hit {
					utils.Debugf("是否是第一个角色:%v",
						chaDetail.Box[1]-regionDetail.Box[1] < 170)
				}
			}
		}()
		count--
		time.Sleep(2 * time.Second)
	}

	if chaDetail == nil || !chaDetail.Hit || regionDetail == nil || !regionDetail.Hit {
		utils.Warning("未能识别角色信息,跳过切换")
		return true
	}

	offsetY := chaDetail.Box[1] - regionDetail.Box[1]
	switch index {
	case "1":
		if offsetY > 170 {
			_, _ = ctx.RunTask("点击角色", map[string]any{
				"点击角色": map[string]any{
					"target": []int{chaDetail.Box[0], chaDetail.Box[1] - 170, chaDetail.Box[2], chaDetail.Box[3]},
				},
			})
			utils.Info("切换到第一个角色")
		} else {
			utils.Info("当前已是第1个角色,无需切换")
		}
	case "2":
		if offsetY < 170 {
			_, _ = ctx.RunTask("点击角色", map[string]any{
				"点击角色": map[string]any{
					"target": []int{chaDetail.Box[0], chaDetail.Box[1] + 170, chaDetail.Box[2], chaDetail.Box[3]},
				},
			})
			utils.Info("切换到第二个角色")
		} else {
			utils.Info("当前已是第2个角色,无需切换")
		}
	default:
		utils.Infof("当前已是第%s个角色,无需切换", index)
	}

	// 在角色管理界面 OCR 角色ID
	accountID := utils.OcrUntilConsistent(ctx, idROI, idPattern, 3, 30)
	if accountID != "" {
		utils.AccountID = accountID
		utils.Infof("角色ID已识别:%s", accountID)
	} else {
		utils.Warning("角色ID识别失败,将使用默认存储")
		utils.AccountID = ""
	}

	return true
}

// 确保有队列可用
func makeSureQueueAvailable(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	// 0. 如果后续没有战斗任务,跳过
	battleStatus, ok := utils.HasBattleTasks()
	if ok && !battleStatus {
		utils.Info("后续无战斗任务,跳过确保空闲队列")
		return true
	}

	// 1. 关闭自动加入
	utils.Debug("关闭自动加入集结")
	_, _ = ctx.RunTask("自动加入集结_关闭_入口")
	_, _ = ctx.RunTask("转到城外")
	_, _ = ctx.RunTask("开始查看队列")
	text, _ := utils.OcrUntilConsistentByTask(ctx, "识别当前队列数量", nil, `\d+/\d+`, 0, 0)
	if text == "" {
		utils.Warning("识别队列数量失败")
		// 节点"确保有空闲队列"无 next 字段,OverrideNext(空) 为冗余调用,直接 return 即可。
		return true
	}
	utils.Debugf("队列情况:%s", text)

	firstNum := 0
	if m := regexp.MustCompile(`\d+`).FindString(text); m != "" {
		firstNum = atoiLocal(m)
	}
	if firstNum > 0 {
		return true
	}

	_, _ = ctx.RunTask("后退")
	parts := regexp.MustCompile(`\d+`).FindAllString(text, -1)
	b := 0
	if len(parts) >= 2 {
		b = atoiLocal(parts[1])
	} else if len(parts) == 1 {
		b = atoiLocal(parts[0])
	}

	utils.Infof("当前队列已满,队列总数为%d", b)

	// 2. 如果有不是挖矿的队伍,等待
	img, _ := utils.ScreenCap(ctx)
	detail, _ := ctx.RunRecognition("识别队列动作", img)
	if detail != nil && detail.Hit {
		utils.Info("开始等待出征队伍回归")
	} else {
		// 3. 如果全部在挖矿,召回最后一队
		recallRegion := [6][4]int{
			{200, 544, 43, 56}, {200, 484, 43, 56}, {200, 424, 43, 56},
			{200, 364, 43, 56}, {200, 304, 43, 56}, {200, 244, 43, 56},
		}
		img, _ = utils.ScreenCap(ctx)
		start := len(recallRegion) - b
		if start < 0 {
			start = 0
		}
		for _, region := range recallRegion[start:] {
			detail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
				&maa.TemplateMatchParam{Template: []string{"召回.png"}, ROI: maa.NewTargetRect(region)}, img)
			if detail != nil && detail.Hit {
				_, _ = ctx.RunTask("点击召回", map[string]any{"点击召回": map[string]any{"target": region}})
				utils.Info("已召回队伍,开始等待")
				break
			}
		}
	}

	_, _ = ctx.RunTask("开始查看队列")
	for {
		time.Sleep(1 * time.Second)
		img, _ := utils.ScreenCap(ctx)
		detail, _ := ctx.RunRecognition("识别当前队列数量", img)
		if detail != nil && detail.Hit {
			text := utils.BestText(detail)
			if m := regexp.MustCompile(`\d+`).FindString(text); m != "" && atoiLocal(m) > 0 {
				break
			}
		}
	}

	return true
}

// NodeParaCombine:禁用节点
func nodeParaCombine(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	param := jsonParam(arg.CustomActionParam)
	nodeName, _ := param["node_name"].(string)
	utils.Debug(nodeName)
	_ = ctx.OverridePipeline(map[string]any{nodeName: map[string]any{"enabled": false}})
	return true
}

// DisableNode:禁用节点
func disableNode(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	nodeName := jsonParamStr(arg.CustomActionParam, "node_name")
	_ = ctx.OverridePipeline(map[string]any{nodeName: map[string]any{"enabled": false}})
	return true
}

// NodeOverride:pipeline 覆盖
func nodeOverride(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	ppover := jsonParam(arg.CustomActionParam)
	if len(ppover) == 0 {
		utils.Warning("No ppover")
		return true
	}
	utils.Debugf("NodeOverride: %v", ppover)
	_ = ctx.OverridePipeline(ppover)
	return true
}

// 每日检查
func dailyCheckAction(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	param := jsonParam(arg.CustomActionParam)
	taskName, _ := param["task_name"].(string)
	switchName, _ := param["switch_name"].(string)
	currentNode, _ := param["current_node"].(string)
	skipNext, _ := param["skip_next"].(string)
	utils.DailyCheck(ctx, taskName, switchName, currentNode, skipNext)
	return true
}

// 记录日期
func recordDate(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	param := jsonParam(arg.CustomActionParam)
	taskName, _ := param["task_name"].(string)
	switchName, _ := param["switch_name"].(string)
	utils.SaveTaskDate(taskName)
	if switchName != "" {
		utils.DisableSwitch(ctx, switchName)
	}
	utils.Infof("%s完成,记录日期", taskName)
	return true
}

// 下午检查
func afternoonCheck(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	param := jsonParam(arg.CustomActionParam)
	hour := jsonParamInt(arg.CustomActionParam, "hour", 16)
	enabled := true
	if v, ok := param["enabled"].(bool); ok {
		enabled = v
	}
	skipNode, _ := param["skip_node"].(string)

	if !enabled {
		utils.Info("时段检查已禁用,直接放行")
		return true
	}
	if utils.IsAfterHour(hour, "Asia/Shanghai") {
		utils.Infof("当前已过%d点,执行后续流程", hour)
		return true
	}
	utils.Infof("当前未到%d点,跳过后续流程", hour)
	if skipNode != "" {
		_ = ctx.OverridePipeline(map[string]any{skipNode: map[string]any{"enabled": false}})
	}
	return true
}

// 切换队伍
func changeTeam(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	teamIndex := jsonParamInt(arg.CustomActionParam, "队伍序号", 0)
	utils.Debugf("切换队伍到:%d", teamIndex)
	if teamIndex != 0 && teamIndex > 0 && teamIndex < len(teamROI) {
		_, _ = ctx.RunActionDirect(maa.ActionTypeClick,
			&maa.ClickParam{Target: maa.NewTargetRect(teamROI[teamIndex])},
			maa.Rect{}, nil)
	}
	return true
}

// 撤回最后一个队伍
func recallTeam(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	teamIndex := jsonParamInt(arg.CustomActionParam, "队伍序号", 0)
	if teamIndex != 0 && teamIndex > 0 && teamIndex < len(recallTeamROI) {
		_, _ = ctx.RunActionDirect(maa.ActionTypeClick,
			&maa.ClickParam{Target: maa.NewTargetRect(recallTeamROI[teamIndex])},
			maa.Rect{}, nil)
	}
	return true
}

func atoiLocal(s string) int {
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			break
		}
		n = n*10 + int(c-'0')
	}
	return n
}
