package action

import (
	"strings"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// 梦境寻忆
var episode = "1"

// dreamItem 梦境物品与坐标(按 Python dict 插入序排列,保证匹配顺序一致)
type dreamItem struct {
	Name string
	Rect maa.Rect
}

// RegisterDreamActions 注册梦境寻忆 action
func RegisterDreamActions() {
	_ = maa.AgentServerRegisterCustomAction("梦境寻忆_判断生效",
		maa.CustomActionFunc(dreamEffective))
	_ = maa.AgentServerRegisterCustomAction("梦境寻忆",
		maa.CustomActionFunc(memories))
}

// 梦境寻忆_判断生效:根据选择的 episode 禁用其他阶段节点
func dreamEffective(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	episode = jsonParamStr(arg.CustomActionParam, "episode")
	isStage := NodeEnabled(ctx, "梦境寻忆_闯关")

	var nameList []string
	if isStage {
		nameList = NodeNextNames(ctx, "梦境寻忆_开始闯关")
	} else {
		nameList = NodeNextNames(ctx, "梦境寻忆_组队")
	}

	if episode == "0" {
		maxStr := ""
		maxNum := -1
		for _, item := range nameList {
			parts := strings.Split(item, "_")
			if len(parts) >= 2 {
				if n := atoiLocal(parts[1]); n > maxNum {
					maxNum = n
					maxStr = item
				}
			}
		}
		episode = itoa(maxNum)
		utils.Debugf("当前最新阶段: %s", episode)
		for _, item := range nameList {
			if maxStr != item {
				utils.DisableSwitch(ctx, item)
			}
		}
	} else {
		utils.Debugf("当前选择阶段: %s", episode)
		prefix := "梦境寻忆_" + episode + "_"
		for _, item := range nameList {
			if !strings.Contains(item, prefix) {
				utils.DisableSwitch(ctx, item)
			}
		}
	}

	return true
}

// 梦境寻忆
func memories(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	param := jsonParam(arg.CustomActionParam)
	mode, _ := param["mode"].(string)
	level, _ := param["level"].(string)
	utils.Debugf("当前模式:%s,当前关卡:%s", mode, level)
	utils.ScreenShot(ctx, level)

	if mode == "闯关" {
		dreamStageMode(ctx, level)
	} else {
		dreamTeamMode(ctx, level)
	}
	// 本关卡完成:节点"梦境寻忆_*_开始_*关"无 next 字段,OverrideNext(空) 为冗余调用,
	// 直接 return 即弹栈回"梦境寻忆_*_闯关"继续下一关;此处不能禁用节点,否则会中断多关卡流程。
	return true
}

// dreamStageMode 闯关模式
func dreamStageMode(ctx *maa.Context, level string) {
	itemList := dreamStageData(episode, level)
	areas := [3]maa.Rect{{40, 1135, 214, 72}, {252, 1133, 215, 69}, {467, 1133, 217, 71}}
	dreamFindLoop(ctx, itemList, areas[:], maa.Rect{336, 900, 52, 33})
}

// dreamTeamMode 组队模式
func dreamTeamMode(ctx *maa.Context, level string) {
	itemList := dreamTeamData(episode, level)
	areas := [6]maa.Rect{
		{68, 1120, 111, 58}, {281, 1123, 160, 54}, {508, 1121, 172, 61},
		{71, 1196, 124, 59}, {297, 1200, 132, 53}, {529, 1193, 133, 62},
	}
	dreamFindLoop(ctx, itemList, areas[:], maa.Rect{317, 1216, 46, 19})
}

// dreamFindLoop 循环 OCR 找物品并点击,直到"找到所有物品"命中
func dreamFindLoop(ctx *maa.Context, itemList []dreamItem, areas []maa.Rect, doneBtn maa.Rect) {
	// itemMap 便于按名查找坐标;remaining 保持插入序
	itemMap := make(map[string]maa.Rect, len(itemList))
	for _, item := range itemList {
		itemMap[item.Name] = item.Rect
	}
	remaining := make([]string, 0, len(itemList))
	for _, item := range itemList {
		remaining = append(remaining, item.Name)
	}
	doneKeys := make([]string, 0, len(itemList))
	missCount := map[string]int{}

	for {
		for _, area := range areas {
			img, err := utils.ScreenCap(ctx)
			if err != nil {
				continue
			}
			d, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeOCR,
				&maa.OCRParam{ROI: maa.NewTargetRect(area), OnlyRec: true, Threshold: 0.5}, img)
			if d == nil || len(d.Results.Filtered) == 0 {
				continue
			}

			texts := make([]string, 0, len(d.Results.Filtered))
			for _, r := range d.Results.Filtered {
				if ocr, ok := r.AsOCR(); ok {
					texts = append(texts, capitalize(trimSpaceLocal(ocr.Text)))
				}
			}

			match := dreamExactMatch(remaining, texts)
			if match == "" {
				match = dreamFuzzyMatch(remaining, texts)
			}

			if match != "" {
				utils.Debugf("找到:%s", match)
				utils.ClickRect(ctx, itemMap[match])
				doneKeys = append(doneKeys, match)
				remaining = removeStr(remaining, match)
			} else {
				// 缺失打印:取 score 最高的 t
				best := d.Results.Filtered[0]
				bestScore := -1.0
				for _, r := range d.Results.Filtered {
					if ocr, ok := r.AsOCR(); ok && ocr.Score > bestScore {
						bestScore = ocr.Score
						best = r
					}
				}
				var t string
				if ocr, ok := best.AsOCR(); ok {
					t = capitalize(trimSpaceLocal(ocr.Text))
				}
				alreadyFound := false
				for _, key := range doneKeys {
					if strings.Contains(t, key) {
						alreadyFound = true
						break
					}
				}
				if !alreadyFound {
					if _, exists := missCount[t]; !exists {
						utils.Infof("缺失:%s", t)
					}
					missCount[t]++
				}
			}
			time.Sleep(500 * time.Millisecond)
		}

		img, _ := utils.ScreenCap(ctx)
		detail, _ := ctx.RunRecognition("梦境寻忆_找到所有物品", img)
		if detail != nil && detail.Hit {
			break
		}
	}

	utils.Infof("共点击%d个物品", len(doneKeys))
	_, _ = ctx.RunActionDirect(maa.ActionTypeClick,
		&maa.ClickParam{Target: maa.NewTargetRect(doneBtn)}, maa.Rect{}, nil)
}

// dreamExactMatch 完全匹配,去掉被其他匹配key包含的短key
func dreamExactMatch(remaining, texts []string) string {
	exact := make([]string, 0)
	for _, key := range remaining {
		for _, t := range texts {
			if t == key {
				exact = append(exact, key)
				break
			}
		}
	}
	if len(exact) == 0 {
		return ""
	}
	filtered := make([]string, 0)
	for _, k := range exact {
		contained := false
		for _, other := range exact {
			if other != k && strings.Contains(other, k) {
				contained = true
				break
			}
		}
		if !contained {
			filtered = append(filtered, k)
		}
	}
	if len(filtered) > 0 {
		return filtered[0]
	}
	return exact[0]
}

// dreamFuzzyMatch 包含匹配,去掉被其他匹配key包含的短key
func dreamFuzzyMatch(remaining, texts []string) string {
	fuzzy := make([]string, 0)
	for _, key := range remaining {
		for _, t := range texts {
			if strings.Contains(t, key) {
				fuzzy = append(fuzzy, key)
				break
			}
		}
	}
	if len(fuzzy) == 0 {
		return ""
	}
	filtered := make([]string, 0)
	for _, k := range fuzzy {
		contained := false
		for _, other := range fuzzy {
			if other != k && strings.Contains(other, k) {
				contained = true
				break
			}
		}
		if !contained {
			filtered = append(filtered, k)
		}
	}
	if len(filtered) > 0 {
		return filtered[0]
	}
	return fuzzy[0]
}

// capitalize 与 Python str.capitalize() 一致:首字母大写,其余小写
func capitalize(s string) string {
	if s == "" {
		return s
	}
	var b strings.Builder
	b.Grow(len(s))
	first := true
	for _, r := range s {
		if first {
			if r >= 'a' && r <= 'z' {
				r = r - 'a' + 'A'
			}
			first = false
		} else {
			if r >= 'A' && r <= 'Z' {
				r = r - 'A' + 'a'
			}
		}
		b.WriteRune(r)
	}
	return b.String()
}

func trimSpaceLocal(s string) string {
	return strings.TrimSpace(s)
}

func removeStr(list []string, s string) []string {
	out := make([]string, 0, len(list))
	for _, v := range list {
		if v != s {
			out = append(out, v)
		}
	}
	return out
}
