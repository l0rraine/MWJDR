package action

import (
	"image"
	"image/color"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// ============ 投壶小游戏自动化 ============
// 机制（视频实测）：
//   活动入口 → 进入游戏 → 准备 → 开始 → 投 8 支箭 → 结算
//   瞄准条（壶口上方弧形条）：大部分绿色、一小段黄色；白色三角指针来回扫描
//   指针与黄色段重叠时点击投掷 = 最高分；绿色段点击 = 普通命中；脱靶则暂停重开
// 坐标：左上角 0,0，1080x1920（实测）
// =========================================

// 实测坐标
var (
	touhuEntryBtn  = maa.Rect{262, 1154, 189, 51} // 进入游戏（720p 实测：x262-451 y1154-1205）
	touhuReadyBtn  = maa.Rect{357, 672, 4, 4}  // 准备（720p：(539,1011)→(359,674)）
	touhuStartBtn  = maa.Rect{357, 677, 4, 4}  // 开始（720p：(539,1018)→(359,679)）
	touhuThrowBtn  = maa.Rect{313, 1138, 93, 93} // 投掷大按钮（720p：中心(359,1185)）
	touhuPauseBtn  = maa.Rect{40, 37, 40, 37}   // 左上角暂停图标（720p：(90,82)→(60,55)）
	touhuPauseExit = maa.Rect{210, 617, 63, 40} // 暂停菜单-退出（720p：(362,953)→(241,635)）
)

// touhuState 跨调用状态（一局完成计数）
type touhuState struct {
	rounds int
}

var touhuSt = touhuState{}

// RegisterTouhuActions 注册投壶 action
func RegisterTouhuActions() {
	_ = maa.AgentServerRegisterCustomAction("投壶", maa.CustomActionFunc(touhuRun))
	_ = maa.AgentServerRegisterCustomAction("投壶_判断继续", maa.CustomActionFunc(touhuContinue))
}

// touhuThrowDelay 投掷预测延迟（秒）：截图时刻指针位置 + 识别/点击传播耗时，实机偏右则减小、偏左则增大
const touhuThrowDelay = 0.30

// touhuRun 单局执行：进入→准备→开始→投掷→结算
func touhuRun(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	missQuota := jsonParamInt(arg.CustomActionParam, "重开配额", 5)
	utils.Infof("投壶：开始新一局（重开配额=%d）", missQuota)

	ok := touhuOneRound(ctx, missQuota)
	if !ok {
		utils.Warning("投壶：一局未能正常完成")
	}
	return true
}

// touhuContinue 判断是否继续下一局
func touhuContinue(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	maxRounds := jsonParamInt(arg.CustomActionParam, "局数", 0)
	touhuSt.rounds++
	if maxRounds > 0 && touhuSt.rounds >= maxRounds {
		utils.Infof("投壶：已完成 %d 局，任务结束", touhuSt.rounds)
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{{Name: "投壶_结束"}})
	} else {
		utils.Infof("投壶：第 %d 局完成，继续下一局", touhuSt.rounds)
		_ = ctx.OverrideNext(arg.CurrentTaskName, []maa.NextItem{{Name: "投壶_执行"}})
	}
	return true
}

// ============ 状态识别（像素法） ============

type touhuStateID int

const (
	tsEntry touhuStateID = iota
	tsReady
	tsStart
	tsThrow
	tsPause
	tsFinish
	tsUnknown
)

func (s touhuStateID) String() string {
	switch s {
	case tsEntry:
		return "入口"
	case tsReady:
		return "准备"
	case tsStart:
		return "开始"
	case tsThrow:
		return "投掷"
	case tsPause:
		return "暂停菜单"
	case tsFinish:
		return "结算"
	default:
		return "未知"
	}
}

// fastRGB 取像素 RGB（0-255）
func fastRGB(img image.Image, x, y int) (uint8, uint8, uint8) {
	if rg, ok := img.(*image.RGBA); ok {
		i := rg.PixOffset(x, y)
		return rg.Pix[i], rg.Pix[i+1], rg.Pix[i+2]
	}
	c := img.At(x, y)
	if cr, ok := c.(color.RGBA); ok {
		return cr.R, cr.G, cr.B
	}
	if cr, ok := c.(color.NRGBA); ok {
		return cr.R, cr.G, cr.B
	}
	r, g, b, _ := c.RGBA()
	return uint8(r >> 8), uint8(g >> 8), uint8(b >> 8)
}

func hsvOf(r, g, b uint8) (float64, float64, float64) {
	rf := float64(r) / 255.0
	gf := float64(g) / 255.0
	bf := float64(b) / 255.0
	max := rf
	if gf > max {
		max = gf
	}
	if bf > max {
		max = bf
	}
	min := rf
	if gf < min {
		min = gf
	}
	if bf < min {
		min = bf
	}
	d := max - min
	v := max
	s := 0.0
	if max != 0 {
		s = d / max
	}
	h := 0.0
	if d != 0 {
		if max == rf {
			h = 60 * ((gf - bf) / d)
			if h < 0 {
				h += 360
			}
		} else if max == gf {
			h = 60*((bf-rf)/d) + 120
		} else {
			h = 60*((rf-gf)/d) + 240
		}
	}
	return h, s, v
}

func isGreen(r, g, b uint8) bool {
	h, s, v := hsvOf(r, g, b)
	return h >= 45 && h <= 175 && s >= 0.20 && v >= 0.25
}

func isYellow(r, g, b uint8) bool {
	h, s, v := hsvOf(r, g, b)
	return h >= 15 && h <= 55 && s >= 0.40 && v >= 0.60
}

func isWhite(r, g, b uint8) bool {
	_, s, v := hsvOf(r, g, b)
	return v >= 0.70 && s <= 0.25
}

func isBlue(r, g, b uint8) bool {
	return int(b) > 150 && int(b)-int(r) > 60 && int(b)-int(g) > 30
}

func isWarm(r, g, b uint8) bool {
	h, s, v := hsvOf(r, g, b)
	return h <= 60 && s >= 0.45 && v >= 0.45 && v <= 0.98
}

func absI(a int) int {
	if a < 0 {
		return -a
	}
	return a
}

// cluster 简单贪心聚类，返回按数量降序 [x0,y0,x1,y1,cnt]
func cluster(hits [][2]int, gap int) [][5]int {
	var groups [][][2]int
	for _, p := range hits {
		placed := false
		for gi := range groups {
			for _, q := range groups[gi] {
				if absI(p[0]-q[0]) <= gap && absI(p[1]-q[1]) <= gap {
					groups[gi] = append(groups[gi], p)
					placed = true
					break
				}
			}
			if placed {
				break
			}
		}
		if !placed {
			groups = append(groups, [][2]int{p})
		}
	}
	var res [][5]int
	for _, g := range groups {
		minx, miny, maxx, maxy := 1<<30, 1<<30, -1, -1
		for _, p := range g {
			if p[0] < minx {
				minx = p[0]
			}
			if p[1] < miny {
				miny = p[1]
			}
			if p[0] > maxx {
				maxx = p[0]
			}
			if p[1] > maxy {
				maxy = p[1]
			}
		}
		res = append(res, [5]int{minx, miny, maxx, maxy, len(g)})
	}
	for i := 1; i < len(res); i++ {
		for j := i; j > 0 && res[j][4] > res[j-1][4]; j-- {
			res[j], res[j-1] = res[j-1], res[j]
		}
	}
	return res
}

// findPointerGlobal 在瞄准条区域(y 560-720)找白色三角指针
func findPointerGlobal(img image.Image) (int, int) {
	w := img.Bounds().Max.X
	h := img.Bounds().Max.Y
	var hits [][2]int
	for y := 373; y < 480 && y < h; y++ {
		for x := 133; x < w; x++ {
			r, g, b := fastRGB(img, x, y)
			if isWhite(r, g, b) {
				hits = append(hits, [2]int{x, y})
			}
		}
	}
	if len(hits) < 10 {
		return -1, -1
	}
	for _, c := range cluster(hits, 10) {
		cw, ch := c[2]-c[0], c[3]-c[1]
		if cw >= 8 && cw <= 60 && ch >= 8 && ch <= 60 && c[4] >= 12 {
			return (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
		}
	}
	return -1, -1
}

// findGreenBar 瞄准条区域(y 580-675)的绿色横条（瞄准条绿色段）
func findGreenBar(img image.Image) (int, int, int, int, bool) {
	w := img.Bounds().Max.X
	h := img.Bounds().Max.Y
	var hits [][2]int
	for y := 387; y < 450 && y < h; y++ {
		for x := 133; x < w; x++ {
			r, g, b := fastRGB(img, x, y)
			if isGreen(r, g, b) {
				hits = append(hits, [2]int{x, y})
			}
		}
	}
	if len(hits) < 90 {
		return 0, 0, 0, 0, false
	}
	for _, c := range cluster(hits, 30) {
		x0, y0, x1, y1, cnt := c[0], c[1], c[2], c[3], c[4]
		cw, ch := x1-x0, y1-y0
		if cw >= 120 && ch <= 54 && cnt >= 90 {
			return x0, y0, x1, y1, true
		}
	}
	return 0, 0, 0, 0, false
}

// findAimBar 瞄准条 ROI（绿色横条定位 + 三角紧贴条带验证）
func findAimBar(img image.Image) (int, int, int, int, bool) {
	gx0, gy0, gx1, gy1, gok := findGreenBar(img)
	if !gok {
		return 0, 0, 0, 0, false
	}
	x0, y0 := gx0-67, 373
	x1, y1 := gx1+67, 467
	if x0 < 0 {
		x0 = 0
	}
	if x1 >= img.Bounds().Max.X {
		x1 = img.Bounds().Max.X - 1
	}
	// 三角必须紧贴条带（绿条 x 扩展 80、y 上下 25 内）
	px, py := findPointerGlobal(img)
	if px >= 0 && (px < gx0-53 || px > gx1+53 || py < gy0-17 || py > gy1+17) {
		return 0, 0, 0, 0, false
	}
	return x0, y0, x1, y1, true
}

// yellowZone 瞄准条 ROI 内黄色 x 范围
func yellowZone(img image.Image, x0, y0, x1, y1 int) (int, int, bool) {
	minx, maxx := 1<<30, -1
	for y := y0; y < y1; y++ {
		for x := x0; x < x1; x++ {
			r, g, b := fastRGB(img, x, y)
			if isYellow(r, g, b) {
				if x < minx {
					minx = x
				}
				if x > maxx {
					maxx = x
				}
			}
		}
	}
	if maxx < 0 {
		return 0, 0, false
	}
	return minx, maxx, true
}

// yellowZoneGlobal 条带区(y560-720,x200-900)全局黄区兜底（绿条未点亮但黄段可见时定位）
func yellowZoneGlobal(img image.Image) (int, int, bool) {
	minx, maxx := 1<<30, -1
	w := img.Bounds().Max.X
	h := img.Bounds().Max.Y
	for y := 560; y < 720 && y < h; y++ {
		for x := 200; x < 900 && x < w; x++ {
			r, g, b := fastRGB(img, x, y)
			if isYellow(r, g, b) {
				if x < minx {
					minx = x
				}
				if x > maxx {
					maxx = x
				}
			}
		}
	}
	if maxx < 0 {
		return 0, 0, false
	}
	return minx, maxx, true
}

// blueZone 中央暂停菜单蓝色按钮：返回左/右按钮中心 x
func blueZone(img image.Image) (int, int, bool) {
	w, h := img.Bounds().Max.X, img.Bounds().Max.Y
	var hits [][2]int
	for y := 567; y < 733 && y < h; y++ {
		for x := 167; x < 567 && x < w; x++ {
			r, g, b := fastRGB(img, x, y)
			if isBlue(r, g, b) {
				hits = append(hits, [2]int{x, y})
			}
		}
	}
	if len(hits) < 670 {
		return 0, 0, false
	}
	var left, right [5]int
	found := 0
	for _, c := range cluster(hits, 40) {
		if c[4] >= 356 {
			if found == 0 {
				left = c
				found++
			} else if found == 1 {
				right = c
				found++
				break
			}
		}
	}
	if found < 2 {
		return 0, 0, false
	}
	lx, rx := (left[0]+left[2])/2, (right[0]+right[2])/2
	if lx > rx {
		lx, rx = rx, lx
	}
	return lx, rx, true
}

// isButtonBlue 投掷按钮内圈蓝（浅蓝，比暂停菜单蓝钮宽松）
func isButtonBlue(r, g, b uint8) bool {
	return int(b) > 120 && int(b)-int(r) > 40 && int(b)-int(g) > 25
}

// throwBtnPresent 投掷大按钮：底部中央圆形按钮的内圈蓝色
// 内圈蓝被中央手/箭图标分成左右两块，用总包围盒判定
func throwBtnPresent(img image.Image) bool {
	w, h := img.Bounds().Max.X, img.Bounds().Max.Y
	var hits [][2]int
	for y := 1127; y < 1220 && y < h; y++ {
		for x := 287; x < 440 && x < w; x++ {
			r, g, b := fastRGB(img, x, y)
			if isButtonBlue(r, g, b) {
				hits = append(hits, [2]int{x, y})
			}
		}
	}
	if len(hits) < 222 {
		return false
	}
	minx, miny, maxx, maxy := 1<<30, 1<<30, -1, -1
	for _, p := range hits {
		if p[0] < minx {
			minx = p[0]
		}
		if p[1] < miny {
			miny = p[1]
		}
		if p[0] > maxx {
			maxx = p[0]
		}
		if p[1] > maxy {
			maxy = p[1]
		}
	}
	return maxx-minx >= 80 && maxy-miny >= 27
}

// entryBtnPresent 入口页底部黄色大按钮（宽>140 高30-80 的簇）
func entryBtnPresent(img image.Image) bool {
	if throwBtnPresent(img) {
		return false
	}
	w, h := img.Bounds().Max.X, img.Bounds().Max.Y
	var hits [][2]int
	for y := 1100; y < 1233 && y < h; y += 1 {
		for x := 267; x < 467 && x < w; x += 1 {
			r, g, b := fastRGB(img, x, y)
			if isWarm(r, g, b) {
				hits = append(hits, [2]int{x, y})
			}
		}
	}
	if len(hits) < 222 {
		return false
	}
	for _, c := range cluster(hits, 25) {
		cw, ch := c[2]-c[0], c[3]-c[1]
		if cw >= 94 && ch >= 20 && ch <= 100 && c[4] >= 222 {
			return true
		}
	}
	return false
}

// centerTextPresent 中央文字区（准备/开始页）
func centerTextPresent(img image.Image) bool {
	w, h := img.Bounds().Max.X, img.Bounds().Max.Y
	c := 0
	for y := 567; y < 800 && y < h; y += 2 {
		for x := 167; x < 553 && x < w; x += 2 {
			r, g, b := fastRGB(img, x, y)
			hh, ss, vv := hsvOf(r, g, b)
			if (vv >= 0.75 && ss <= 0.35) || (hh <= 55 && ss >= 0.45 && vv >= 0.70) {
				c++
			}
		}
	}
	return c > 222
}

// detectState 综合状态判定
func detectState(img image.Image) touhuStateID {
	if _, _, ok := blueZone(img); ok {
		return tsPause
	}
	if throwBtnPresent(img) {
		return tsThrow
	}
	if entryBtnPresent(img) {
		return tsEntry
	}
	if centerTextPresent(img) {
		return tsReady
	}
	return tsStart // 未知：按时序推进
}

// ============ 一局状态机 ============

func touhuOneRound(ctx *maa.Context, missQuota int) bool {
	state := tsEntry
	lastAim := false
	justThrew := false
	missRestarts := 0
	aimGoneStart := time.Now()
	roundStart := time.Now()
	// 投掷预测/盲投状态
	prevPx := -1
	var prevPxT time.Time
	pxVel := 0.0
	var pxVelT time.Time
	arrowStart := time.Now()

	for {
		if time.Since(roundStart) > 300*time.Second {
			utils.Warning("投壶：一局超时（300s），点暂停退出恢复")
			utils.ClickRect(ctx, touhuPauseBtn)
			time.Sleep(900 * time.Millisecond)
			utils.ClickRect(ctx, touhuPauseExit)
			time.Sleep(1500 * time.Millisecond)
			return false
		}

		img, err := utils.ScreenCap(ctx)
		if err != nil {
			time.Sleep(500 * time.Millisecond)
			continue
		}
		if state == tsEntry && time.Since(roundStart) < 3*time.Second {
			b := img.Bounds()
			utils.Infof("投壶：截图分辨率=%dx%d", b.Max.X, b.Max.Y)
		}
		// tsThrow 阶段只专注瞄准条/指针（跳过全屏状态扫描提速）
		var cur touhuStateID = tsUnknown
		if state != tsThrow {
			cur = detectState(img)
		}

		switch state {
		case tsEntry:
			if cur == tsEntry {
				utils.Infof("投壶：入口页，点进入游戏")
				utils.ClickRect(ctx, touhuEntryBtn)
				state = tsReady
				time.Sleep(800 * time.Millisecond)
			} else if cur == tsThrow || cur == tsReady {
				utils.Infof("投壶：入口态检测到非入口(cur=%s)，切投掷", cur)
				state = tsThrow
			} else if cur == tsPause {
				utils.Warningf("投壶：入口态遇到暂停菜单，点退出")
				utils.ClickRect(ctx, touhuPauseExit)
				state = tsEntry
				time.Sleep(1500 * time.Millisecond)
			} else {
				time.Sleep(600 * time.Millisecond)
			}

		case tsReady:
			if cur == tsReady || cur == tsStart {
				utils.Infof("投壶：准备/开始页，点准备")
				utils.ClickRect(ctx, touhuReadyBtn)
				state = tsStart
				time.Sleep(600 * time.Millisecond)
			} else if cur == tsThrow {
				state = tsThrow
			} else if cur == tsEntry {
				state = tsEntry
			} else {
				time.Sleep(500 * time.Millisecond)
			}

		case tsStart:
			if cur == tsStart || cur == tsReady {
				utils.Infof("投壶：开始页，点开始")
				utils.ClickRect(ctx, touhuStartBtn)
				state = tsThrow
				time.Sleep(1 * time.Second)
			} else if cur == tsThrow {
				state = tsThrow
			} else if cur == tsEntry {
				state = tsEntry
			} else {
				time.Sleep(500 * time.Millisecond)
			}

		case tsThrow:
			now := time.Now()
			px, _ := findPointerGlobal(img)
			// 指针速度跟踪（帧间差分）
			if px >= 0 {
				if prevPx >= 0 && !prevPxT.IsZero() {
					if dt := now.Sub(prevPxT).Seconds(); dt > 0.03 && dt < 0.8 {
						pxVel = float64(px-prevPx) / dt
						pxVelT = now
					}
				}
				prevPx, prevPxT = px, now
			}
			// 瞄准条定位：绿条 → 全局黄区兜底
			py0, py1, hasY := -1, -1, false
			aimOK := false
			if x0, y0, x1, y1, ok := findAimBar(img); ok {
				aimOK = true
				py0, py1, hasY = yellowZone(img, x0, y0, x1, y1)
				if justThrew {
					justThrew = false
					lastAim = true
					arrowStart = now
					aimGoneStart = now
				} else {
					lastAim = true
					aimGoneStart = now
				}
			} else if gy0, gy1, ok := yellowZoneGlobal(img); ok {
				aimOK = true
				py0, py1, hasY = gy0, gy1, true
				if justThrew {
					justThrew = false
					lastAim = true
					arrowStart = now
					aimGoneStart = now
				} else {
					lastAim = true
					aimGoneStart = now
				}
			}
			utils.Debugf("投壶：px=%d vel=%.0f aim=%v 黄区[%d,%d] 距投掷=%.1fs", px, pxVel, aimOK, py0, py1, now.Sub(arrowStart).Seconds())
			// 投掷后：指针重现（动画结束）即视为下一支箭开始
			if justThrew {
				if now.Sub(aimGoneStart) > 800*time.Millisecond && (px >= 0 || aimOK) {
					justThrew = false
					lastAim = true
					arrowStart = now
					aimGoneStart = now
				} else if now.Sub(aimGoneStart) > 8*time.Second {
					utils.Infof("投壶：投掷后瞄准条长时间未恢复，判为结算")
					state = tsFinish
					lastAim = false
					justThrew = false
				} else {
					time.Sleep(400 * time.Millisecond)
					continue
				}
			}
			// 投掷触发
			doThrow := false
			reason := ""
			if aimOK && hasY && px >= 0 {
				if px >= py0 && px <= py1 {
					doThrow, reason = true, "黄区内"
				} else if pxVel != 0 && now.Sub(pxVelT) < 500*time.Millisecond {
					future := float64(px) + pxVel*touhuThrowDelay
					if pxVel > 0 && px < py0 && future >= float64(py0) && future <= float64(py1)+200 {
						doThrow, reason = true, "预测进黄区"
					} else if pxVel < 0 && px > py1 && future <= float64(py1) && future >= float64(py0)-200 {
						doThrow, reason = true, "预测进黄区"
					}
				}
			}
			// 每支箭 3s 保底盲投（未点亮/指针缺失时不干等）
			if !doThrow && now.Sub(arrowStart) > 3*time.Second {
				doThrow, reason = true, "超时盲投"
			}
			if doThrow {
				utils.Infof("投壶：投掷(%s) px=%d 黄区[%d,%d] vel=%.0f", reason, px, py0, py1, pxVel)
				utils.ClickRect(ctx, touhuThrowBtn)
				justThrew = true
				lastAim = false
				aimGoneStart = now
				arrowStart = now
				// 等待命中判定
				time.Sleep(2 * time.Second)
				if !touhuHitCheck(ctx) {
					missRestarts++
					if missRestarts > missQuota {
						utils.Warningf("投壶：脱靶次数超过配额(%d)，不再重开", missQuota)
					} else {
						utils.Warningf("投壶：疑似脱靶（第%d次），暂停重开", missRestarts)
						touhuRestart(ctx)
						state = tsEntry
						continue
					}
				}
				time.Sleep(300 * time.Millisecond)
				continue
			}
			// 未投出：瞄准条消失>5s 判结算（仅点亮时）
			if lastAim && aimOK && !justThrew {
				aimGoneStart = now
			} else if lastAim && !justThrew && now.Sub(aimGoneStart) > 5*time.Second {
				utils.Infof("投壶：瞄准条消失>5s，判为结算")
				state = tsFinish
				lastAim = false
			}
			time.Sleep(150 * time.Millisecond)

		case tsPause:
			utils.ClickRect(ctx, touhuPauseExit)
			state = tsEntry
			time.Sleep(1500 * time.Millisecond)

		case tsFinish:
			utils.Infof("投壶：结算，点空白返回")
			utils.ClickRect(ctx, maa.Rect{267, 733, 187, 133})
			state = tsEntry
			time.Sleep(1500 * time.Millisecond)
			return true
		}
	}
}

// touhuHitCheck 投掷后判定是否命中：加分区(150,280)-(900,480)亮色像素
func touhuHitCheck(ctx *maa.Context) bool {
	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return true
	}
	w, h := img.Bounds().Max.X, img.Bounds().Max.Y
	c := 0
	for y := 187; y < 320 && y < h; y += 2 {
		for x := 100; x < 600 && x < w; x += 2 {
			r, g, b := fastRGB(img, x, y)
			_, ss, vv := hsvOf(r, g, b)
			if vv >= 0.65 && ss <= 0.40 {
				c++
			}
		}
	}
	hit := c > 67
	utils.Debugf("投壶：命中判定亮像素=%d → %v", c, hit)
	return hit
}

// touhuRestart 暂停 → 退出 → 回入口
func touhuRestart(ctx *maa.Context) {
	utils.ClickRect(ctx, touhuPauseBtn)
	time.Sleep(900 * time.Millisecond)
	for i := 0; i < 5; i++ {
		img, err := utils.ScreenCap(ctx)
		if err != nil {
			time.Sleep(1 * time.Second)
			continue
		}
		lx, _, ok := blueZone(img)
		if ok {
			utils.Infof("投壶：暂停菜单出现，点退出(%d,635)", lx)
			utils.ClickRect(ctx, maa.Rect{lx - 5, 617, 13, 40})
			time.Sleep(1500 * time.Millisecond)
			return
		}
		time.Sleep(700 * time.Millisecond)
	}
	utils.ClickRect(ctx, touhuPauseExit)
	time.Sleep(1500 * time.Millisecond)
}

// blueZoneScreen 便捷截图判暂停菜单
func blueZoneScreen(ctx *maa.Context) (int, int, bool) {
	img, err := utils.ScreenCap(ctx)
	if err != nil {
		return 0, 0, false
	}
	return blueZone(img)
}
