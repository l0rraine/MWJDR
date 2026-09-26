package action

import (
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// 加入集结相关全局状态
var (
	targetPrefix   = "加入集结_目标_"
	priorityTarget = "等级1失控的雪怪"
	joinTargets    []string
	joinTeam       = 1
	joinOffset     = [4]int{318, -88, 0, 50}
)

// RegisterJoinActions 注册加入集结相关 action 与 recognition
func RegisterJoinActions() {
	_ = maa.AgentServerRegisterCustomRecognition("加入集结_识别队伍",
		maa.CustomRecognitionFunc(joinRecoTeam))
	_ = maa.AgentServerRegisterCustomAction("加入集结_执行加入",
		maa.CustomActionFunc(joinDeploy))
}

// readJoinTargets 读取用户勾选的加入集结目标
func readJoinTargets(ctx *maa.Context) []string {
	targets := make([]string, 0)
	defer func() {
		if r := recover(); r != nil {
			targets = nil
		}
	}()
	for _, name := range NodeNextNames(ctx, "加入集结_目标选项") {
		if name == "" || !strings.HasPrefix(name, targetPrefix) {
			continue
		}
		if NodeEnabled(ctx, name) {
			target := strings.TrimPrefix(name, targetPrefix)
			// "等级8深渊龙龟" → "等级8\s*深渊龙龟"
			target = levelSpaceRe.ReplaceAllString(target, `$1\s*$2`)
			targets = append(targets, target)
		}
	}
	return targets
}

var levelSpaceRe = regexp.MustCompile(`(等级\d+)\s*(.+)`)

// targetSortKey 目标排序键:等级1失控的雪怪最优先,等级1-8按等级逆序
func targetSortKey(text string) (int, int) {
	textCompact := spaceRe.ReplaceAllString(text, "")
	if strings.Contains(textCompact, priorityTarget) {
		return 0, 0
	}
	m := levelNumRe.FindStringSubmatch(textCompact)
	level := 0
	if m != nil {
		level = atoiLocal(m[1])
	}
	return 1, -level
}

var (
	spaceRe    = regexp.MustCompile(`\s+`)
	levelNumRe = regexp.MustCompile(`等级(\d+)`)
)

// 加入集结_识别队伍:队列不满 + 有目标 + 识别到按钮时返回按钮 box
func joinRecoTeam(ctx *maa.Context, arg *maa.CustomRecognitionArg) (*maa.CustomRecognitionResult, bool) {
	// 1. 读取队伍编号
	joinTeam = jsonParamInt(arg.CustomRecognitionParam, "team", 0)

	// 2. 读取勾选目标
	joinTargets = readJoinTargets(ctx)
	if len(joinTargets) == 0 {
		return nil, true
	}

	// 3. 队列判断
	if utils.Queue.IsFull() {
		return nil, true
	}

	// 4. 识别「加入集结」按钮
	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return nil, true
	}
	detail, _ := ctx.RunRecognition("加入集结_识别按钮", img,
		map[string]any{
			"加入集结_识别按钮": map[string]any{
				"recognition": "TemplateMatch",
				"template":    "加入集结.png",
				"roi":         []int{643, 523, 44, 47},
				"threshold":   0.8,
				"method":      10001,
			},
		})
	if detail == nil || !detail.Hit {
		return nil, true
	}

	return &maa.CustomRecognitionResult{Box: detail.Box, Detail: ""}, true
}

// 加入集结_执行加入
func joinDeploy(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	if len(joinTargets) == 0 {
		_, _ = ctx.RunAction("加入集结_后退", maa.Rect{}, "", nil)
		return true
	}

	img, err := utils.ScreenCap(ctx)
	if err != nil {
		_, _ = ctx.RunAction("加入集结_后退", maa.Rect{}, "", nil)
		return true
	}

	// 1. OCR 目标名
	detail, _ := ctx.RunRecognition("加入集结_识别目标_ocr", img,
		map[string]any{
			"加入集结_识别目标_ocr": map[string]any{
				"recognition": "OCR",
				"expected":    joinTargets,
				"roi":         []int{238, 183, 293, 936},
			},
		})
	if detail == nil || !detail.Hit {
		_, _ = ctx.RunAction("加入集结_后退", maa.Rect{}, "", nil)
		return true
	}

	// 2. 排序:雪怪最优先,等级1-8逆序
	hits := utils.FilteredOCR(detail)
	sort.SliceStable(hits, func(i, j int) bool {
		gi, g2 := targetSortKey(hits[i].Text)
		hi, h2 := targetSortKey(hits[j].Text)
		if gi != hi {
			return gi < hi
		}
		return g2 < h2
	})

	// 3. 逐个尝试匹配「直接加入队伍」按钮
	total, sent := utils.Queue.GetNums()
	n := total - sent

	for _, result := range hits {
		joinROI := utils.AddOffset(result.Box, joinOffset)

		joinDetail, _ := ctx.RunRecognition("加入集结_识别_join", img,
			map[string]any{
				"加入集结_识别_join": map[string]any{
					"recognition": "TemplateMatch",
					"template":    "熊/直接加入队伍.png",
					"roi":         joinROI,
					"threshold":   0.9,
					"method":      10001,
				},
			})
		if joinDetail != nil && joinDetail.Hit {
			// 点击加入按钮进入队伍选择页
			_, _ = ctx.RunAction("加入集结_点击加入", maa.Rect{}, "",
				map[string]any{"加入集结_点击加入": map[string]any{"target": joinDetail.Box}})
			// 选队并出征
			if joinTeam > 0 && joinTeam < len(teamROI) {
				_, _ = ctx.RunAction("加入集结_选择队伍", maa.Rect{}, "",
					map[string]any{"加入集结_选择队伍": map[string]any{"target": teamROI[joinTeam]}})
			}
			_, _ = ctx.RunAction("加入集结_点击出征", maa.Rect{}, "", nil)
			utils.Infof("加入集结: 已加入 %s", result.Text)
			n--
			if n == 0 {
				break
			}
			time.Sleep(300 * time.Millisecond)
		}
	}
	_, _ = ctx.RunTask("后退")
	return true
}
