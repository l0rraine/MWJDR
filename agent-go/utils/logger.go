package utils

import (
	"fmt"
	"html"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Logger 提供与 Python loguru 兼容的日志输出:
// - stderr 输出 "level:<font color=...>msg</font>" 格式:
//   MFAAvalonia 按 "level:" 前缀识别级别(CheckShouldLog),
//   内容以 Markdown 渲染,其 HtmlPlugin 的 FontParser 解析 <font color>
//   并直接设置前景色(本地值优先于主题正文色),实现按级别着色。
// - 同时写文件 debug/custom/YYYY-MM-DD.log(纯文本,不含 HTML)
type Logger struct {
	mu     sync.Mutex
	file   *os.File
	logDir string
}

// levelColors stderr 着色映射,与旧版 MFA AddLog 的前缀配色一致
var levelColors = map[string]string{
	"info":     "Black",
	"debug":    "DeepSkyBlue",
	"warn":     "Orange",
	"err":      "OrangeRed",
	"critical": "Red",
}

var stdLogger = NewLogger("debug/custom")

func NewLogger(logDir string) *Logger {
	l := &Logger{logDir: logDir}
	_ = l.openFile()
	return l
}

func (l *Logger) openFile() error {
	if err := os.MkdirAll(l.logDir, 0755); err != nil {
		return err
	}
	name := filepath.Join(l.logDir, time.Now().Format("2006-01-02")+".log")
	f, err := os.OpenFile(name, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	l.file = f
	return nil
}

// stderrLine 构造 MFAAvalonia 日志面板用的 stderr 行。
// 消息做 HTML 转义,换行折叠为空格(面板按行分割,跨行会切断标签)。
func stderrLine(short, msg string) string {
	color, ok := levelColors[short]
	if !ok {
		color = "Black"
	}
	safe := html.EscapeString(msg)
	safe = strings.ReplaceAll(safe, "\r\n", " ")
	safe = strings.ReplaceAll(safe, "\r", " ")
	safe = strings.ReplaceAll(safe, "\n", " ")
	return fmt.Sprintf("%s:<font color=%q>%s</font>", short, color, safe)
}

func (l *Logger) log(short, long, msg string) {
	// stderr: MFAAvalonia 日志面板
	fmt.Fprintln(os.Stderr, stderrLine(short, msg))

	l.mu.Lock()
	defer l.mu.Unlock()
	if l.file == nil {
		if err := l.openFile(); err != nil {
			return
		}
	}
	now := time.Now()
	fmt.Fprintf(l.file, "%s | %-8s | main | %s\n",
		now.Format("2006-01-02 15:04:05.000"), long, msg)
}

func Info(msg string)     { stdLogger.log("info", "INFO", msg) }
func Debug(msg string)    { stdLogger.log("debug", "DEBUG", msg) }
func Warning(msg string)  { stdLogger.log("warn", "WARNING", msg) }
func Error(msg string)    { stdLogger.log("err", "ERROR", msg) }
func Critical(msg string) { stdLogger.log("critical", "CRITICAL", msg) }

func Infof(format string, args ...any)    { Info(fmt.Sprintf(format, args...)) }
func Debugf(format string, args ...any)   { Debug(fmt.Sprintf(format, args...)) }
func Warningf(format string, args ...any) { Warning(fmt.Sprintf(format, args...)) }
func Errorf(format string, args ...any)   { Error(fmt.Sprintf(format, args...)) }
