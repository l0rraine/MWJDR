package utils

import (
	"regexp"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"
)

// OCRHit 是 filtered_results / all_results 中单条 OCR 结果的扁平结构
type OCRHit struct {
	Text  string
	Box   maa.Rect
	Score float64
}

// BestText 返回识别结果的 best_result.text(仅 OCR 算法)
func BestText(d *maa.RecognitionDetail) string {
	if d == nil || d.Results == nil || d.Results.Best == nil {
		return ""
	}
	if ocr, ok := d.Results.Best.AsOCR(); ok {
		return ocr.Text
	}
	return ""
}

// FilteredOCR 返回识别结果的 filtered_results 列表(仅 OCR 算法)
func FilteredOCR(d *maa.RecognitionDetail) []OCRHit {
	if d == nil || d.Results == nil {
		return nil
	}
	out := make([]OCRHit, 0, len(d.Results.Filtered))
	for _, r := range d.Results.Filtered {
		if ocr, ok := r.AsOCR(); ok {
			out = append(out, OCRHit{Text: ocr.Text, Box: ocr.Box, Score: ocr.Score})
		}
	}
	return out
}

// OcrUntilConsistent OCR 读取直到获得多次完全一致的结果(直接指定 ROI)
// 返回匹配文本;失败返回 ""
func OcrUntilConsistent(ctx *maa.Context, roi maa.Rect, expectedPattern string,
	consistentCount, maxAttempts int) string {
	if consistentCount <= 0 {
		consistentCount = 3
	}
	if maxAttempts <= 0 {
		maxAttempts = 30
	}
	re, err := regexp.Compile(expectedPattern)
	if err != nil {
		Error("invalid expected_pattern: " + expectedPattern)
		return ""
	}

	lastResult := ""
	sameCount := 0

	for attempt := 1; attempt <= maxAttempts; attempt++ {
		img, err := ScreenCap(ctx)
		if err != nil {
			Debugf("OCR第%d次异常: %v", attempt, err)
			sameCount = 0
			time.Sleep(300 * time.Millisecond)
			continue
		}
		detail, err := ctx.RunRecognitionDirect(maa.RecognitionTypeOCR,
			&maa.OCRParam{ROI: maa.NewTargetRect(roi), Expected: []string{expectedPattern}}, img)
		if err != nil || detail == nil || !detail.Hit {
			Debugf("OCR第%d次: 未识别到内容", attempt)
			sameCount = 0
			time.Sleep(300 * time.Millisecond)
			continue
		}

		text := trimSpace(BestText(detail))
		if text == lastResult {
			sameCount++
			Debugf("OCR第%d次: '%s'一致(%d/%d)", attempt, text, sameCount, consistentCount)
			if sameCount >= consistentCount {
				if m := re.FindString(text); m != "" {
					return m
				}
			}
		} else {
			lastResult = text
			sameCount = 1
			Debugf("OCR第%d次: '%s'(1/%d)", attempt, text, consistentCount)
		}
		time.Sleep(300 * time.Millisecond)
	}

	Warningf("OCR一致性校验失败: 超过最大尝试次数%d, 最后结果'%s'", maxAttempts, lastResult)
	return ""
}

// OcrUntilConsistentByTask OCR 读取直到获得多次完全一致的结果(通过 pipeline 节点名)
// 返回 (匹配文本, 最后一次成功的识别详情)
// options: [consistentCount=3, maxAttempts=30]
func OcrUntilConsistentByTask(ctx *maa.Context, taskName string,
	override map[string]any, expectedPattern string,
	options ...int) (string, *maa.RecognitionDetail) {
	consistentCount := 3
	maxAttempts := 30
	if len(options) > 0 && options[0] > 0 {
		consistentCount = options[0]
	}
	if len(options) > 1 && options[1] > 0 {
		maxAttempts = options[1]
	}
	var re *regexp.Regexp
	if expectedPattern != "" {
		re, _ = regexp.Compile(expectedPattern)
	}

	lastResult := ""
	sameCount := 0

	for attempt := 1; attempt <= maxAttempts; attempt++ {
		img, err := ScreenCap(ctx)
		if err != nil {
			Debugf("OCR第%d次[%s]异常: %v", attempt, taskName, err)
			sameCount = 0
			time.Sleep(300 * time.Millisecond)
			continue
		}
		var detail *maa.RecognitionDetail
		if override == nil {
			detail, err = ctx.RunRecognition(taskName, img)
		} else {
			detail, err = ctx.RunRecognition(taskName, img, override)
		}
		if err != nil || detail == nil || !detail.Hit {
			sameCount = 0
			time.Sleep(300 * time.Millisecond)
			continue
		}

		text := trimSpace(BestText(detail))
		if text == lastResult {
			sameCount++
			if sameCount >= consistentCount {
				Debugf("OCR成功[%s]: '%s'(%d次一致)", taskName, text, consistentCount)
				if re != nil {
					m := re.FindString(text)
					return m, detail
				}
				return text, detail
			}
		} else {
			lastResult = text
			sameCount = 1
		}
		time.Sleep(300 * time.Millisecond)
	}

	Warningf("OCR失败[%s]: 超过最大尝试次数%d, 最后结果'%s'", taskName, maxAttempts, lastResult)
	return "", nil
}

func trimSpace(s string) string {
	start := 0
	end := len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t' || s[start] == '\n' || s[start] == '\r') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t' || s[end-1] == '\n' || s[end-1] == '\r') {
		end--
	}
	return s[start:end]
}
