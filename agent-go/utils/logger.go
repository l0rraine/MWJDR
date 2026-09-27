package utils

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Logger 提供与 Python loguru 兼容的日志输出:
// - stderr 输出 "level:message" 格式(MFAAvalonia 按前缀识别级别)
// - 同时写文件 debug/custom/YYYY-MM-DD.log
type Logger struct {
	mu     sync.Mutex
	file   *os.File
	logDir string
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

func (l *Logger) log(short, long, msg string) {
	// stderr: MFAAvalonia 依赖 "level:message" 前缀
	fmt.Fprintf(os.Stderr, "%s:%s\n", short, msg)

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
