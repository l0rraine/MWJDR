package utils

import (
	"regexp"

	"github.com/MaaXYZ/maa-framework-go/v4"
)

// 队列状态管理
// 主循环每轮由 新手_不可能任务 调用 Update 更新缓存;
// mine/join/garrison 的 recognition 直接读缓存判断队列是否已满。

const (
	mainOcrTask = "挖矿_识别队伍数量" // 主界面队列指示器 OCR 节点名
	cityOcrTask = "识别当前队列数量"  // 城外队列面板 OCR 节点名
	maxFail     = 3           // 连续识别失败次数上限
)

// QueueStatus 队列数量缓存(单例,模块级全局)
type queueStatus struct {
	Sent      int // 已用队列
	Total     int // 总队列
	failCount int // 连续识别失败次数
	IfFail    int // 最近一次是否失败(1/0)
}

var Queue = &queueStatus{}

var queueMainRe = regexp.MustCompile(`(\d)\D(\d)`)
var queueCityRe = regexp.MustCompile(`(\d+)\D+(\d+)`)

// Update 识别主界面队列指示器,更新缓存。失败累计超过 maxFail 执行恢复逻辑
func (q *queueStatus) Update(ctx *maa.Context) {
	text, _ := OcrUntilConsistentByTask(ctx, mainOcrTask, nil, `\d\D\d`, 0, 0)
	q.IfFail = 0
	if text != "" {
		if m := queueMainRe.FindStringSubmatch(text); m != nil {
			q.Sent = atoi(m[1])
			q.Total = atoi(m[2])
			q.failCount = 0
			q.IfFail = 0
			return
		}
	}
	q.failCount++
	q.IfFail = 1
	Debugf("队列数量识别失败(%d/%d)", q.failCount, maxFail)
	if q.failCount >= maxFail {
		Warningf("队列数量连续%d次识别失败,执行恢复逻辑", q.failCount)
		q.recover(ctx)
	}
}

// recover 恢复逻辑:转到城外 → 开始查看队列 → 识别当前队列数量 → 后退
// 城外格式「空闲/总数」,统一转换为「已用/总数」存储
func (q *queueStatus) recover(ctx *maa.Context) {
	defer func() {
		if r := recover(); r != nil {
			Warningf("恢复逻辑异常: %v", r)
		}
		// 恢复失败也重置计数,避免反复触发
		q.failCount = 0
	}()

	_, _ = ctx.RunTask("转到城外")
	_, _ = ctx.RunTask("开始查看队列")
	text, _ := OcrUntilConsistentByTask(ctx, cityOcrTask, nil, `\d+/\d+`, 0, 0)
	if text != "" {
		if m := queueCityRe.FindStringSubmatch(text); m != nil {
			free := atoi(m[1])
			total := atoi(m[2])
			q.Sent = total - free
			q.Total = total
			q.failCount = 0
			q.IfFail = 0
			Infof("恢复识别成功: 空闲%d/%d,已用%d/%d", free, total, q.Sent, q.Total)
			_, _ = ctx.RunTask("后退")
			return
		}
	}
	Warning("恢复逻辑未能识别队列数量")
}

// IsFull 队列是否已满
func (q *queueStatus) IsFull() bool {
	return q.Sent >= q.Total
}

// GetNums 返回 (已用队列, 总队列)
func (q *queueStatus) GetNums() (int, int) {
	return q.Sent, q.Total
}

// Reset 重置缓存(测试/初始化用)
func (q *queueStatus) Reset() {
	q.Sent = 0
	q.Total = 0
	q.failCount = 0
	q.IfFail = 0
}

func atoi(s string) int {
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			break
		}
		n = n*10 + int(c-'0')
	}
	return n
}
