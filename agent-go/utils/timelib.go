package utils

import (
	"regexp"
	"strconv"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"
)

var nonDigitSplitRe = regexp.MustCompile(`\D+`)

// MsTimestampDiffToDHM 将两个毫秒级时间戳的差值转换为 "X天-X时-X分" 格式
func MsTimestampDiffToDHM(ts1, ts2 int64) string {
	diff := ts2 - ts1
	if diff < 0 {
		diff = -diff
	}
	diffSeconds := diff / 1000

	days := diffSeconds / (24 * 3600)
	hours := (diffSeconds % (24 * 3600)) / 3600
	minutes := (diffSeconds % 3600) / 60

	return strconv.FormatInt(days, 10) + "天-" +
		strconv.FormatInt(hours, 10) + "时-" +
		strconv.FormatInt(minutes, 10) + "分"
}

// SplitTimeStr 将 "1:2:3" 或 "1天2时3分" 等文本切分为 (hours, minutes, seconds)
func SplitTimeStr(timeStr string) (hours, minutes, seconds int) {
	parts := nonDigitSplitRe.Split(timeStr, -1)
	nums := make([]int, 0, 3)
	for _, p := range parts {
		if p == "" {
			continue
		}
		if n, err := strconv.Atoi(p); err == nil {
			nums = append(nums, n)
		}
	}
	for len(nums) < 3 {
		nums = append(nums, 0)
	}
	return nums[0], nums[1], nums[2]
}

var timeOcrPattern = regexp.MustCompile(`\d+\D+\d+\D+\d+`)

// GetTimeFromOCR 通过 OCR 识别时间文本并解析为时、分、秒
func GetTimeFromOCR(ctx *maa.Context, taskName string, maxTime int) (hours, minutes, seconds int) {
	text, _ := OcrUntilConsistentByTask(ctx, taskName, nil, timeOcrPattern.String())
	if text == "" {
		Warning("OCR识别时间失败: " + taskName)
		return 0, 0, 0
	}
	return SplitTimeStr(text)
}

func shanghaiLoc() *time.Location {
	loc, err := time.LoadLocation("Asia/Shanghai")
	if err != nil {
		loc = time.FixedZone("CST", 8*3600)
	}
	return loc
}

// IsToday 判断毫秒级时间戳是否在今天(以0点为分界)
func IsToday(timestampMs int64, timezone string) bool {
	loc := shanghaiLoc()
	tsDate := time.UnixMilli(timestampMs).In(loc)
	now := time.Now().In(loc)
	return tsDate.Year() == now.Year() && tsDate.YearDay() == now.YearDay()
}

// IsAfterHour 判断当前时间是否已过指定小时
func IsAfterHour(hour int, timezone string) bool {
	now := time.Now().In(shanghaiLoc())
	return now.Hour() >= hour
}

// IsCurrentPeriod 判断毫秒级时间戳是否在当前周和当前月
func IsCurrentPeriod(timestampMs int64, timezone string) (isCurrentWeek, isCurrentMonth bool) {
	loc := shanghaiLoc()
	ts := time.UnixMilli(timestampMs).In(loc)
	now := time.Now().In(loc)

	// 当前周:周一05:00 至 下周一05:00
	daysSinceMonday := (int(now.Weekday()) + 6) % 7 // 周一=0
	weekStart := time.Date(now.Year(), now.Month(), now.Day()-daysSinceMonday, 5, 0, 0, 0, loc)
	if now.Weekday() == time.Monday && now.Hour() < 5 {
		weekStart = weekStart.AddDate(0, 0, -7)
	}
	weekEnd := weekStart.AddDate(0, 0, 7)

	// 当前月:当月1号05:00(若为1号5点前则用上月1号)至下月1号05:00
	var monthStart time.Time
	if now.Day() == 1 && now.Hour() < 5 {
		monthStart = time.Date(now.Year(), now.Month()-1, 1, 5, 0, 0, 0, loc)
	} else {
		monthStart = time.Date(now.Year(), now.Month(), 1, 5, 0, 0, 0, loc)
	}
	monthEnd := time.Date(monthStart.Year(), monthStart.Month()+1, 1, 5, 0, 0, 0, loc)

	return !ts.Before(weekStart) && ts.Before(weekEnd),
		!ts.Before(monthStart) && ts.Before(monthEnd)
}
