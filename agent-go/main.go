package main

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime/debug"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

const usage = "Usage: agent-go <socket_id>"

func main() {
	// panic 恢复:打印堆栈到日志,避免静默崩溃
	defer func() {
		if r := recover(); r != nil {
			utils.Critical(fmt.Sprintf("PANIC: %v\n%s", r, debug.Stack()))
			os.Exit(1)
		}
	}()

	utils.Info("MWJDR Go Agent starting")
	if len(os.Args) < 2 {
		utils.Critical(usage)
		os.Exit(1)
	}
	// MFAAvalonia 将 socket_id 作为最后一个参数传入(与 Python 的 sys.argv[-1] 一致)
	identifier := os.Args[len(os.Args)-1]

	// 父进程(客户端)一旦退出立即结束自己,避免残留
	go watchParent(os.Getppid())

	runAgent(identifier)
}

func runAgent(identifier string) {
	libDir, err := resolveLibDir()
	if err != nil {
		utils.Critical("resolve MAA lib dir: " + err.Error())
		os.Exit(1)
	}
	utils.Infof("MAA libDir: %s", libDir)

	if err := maa.Init(maa.WithLibDir(libDir)); err != nil {
		utils.Critical("MAA init failed: " + err.Error())
		os.Exit(1)
	}
	defer maa.Release()

	if err := maa.ConfigInitOption(userPath(), "{}"); err != nil {
		utils.Warningf("ConfigInitOption failed: %v", err)
	}

	registerAll()

	if err := maa.AgentServerStartUp(identifier); err != nil {
		utils.Critical("AgentServerStartUp failed: " + err.Error())
		os.Exit(1)
	}
	utils.Info("Agent server started")

	maa.AgentServerJoin()

	maa.AgentServerShutDown()
	utils.Info("Agent server shutdown")
}

// resolveLibDir 定位 MaaFramework 动态库目录:
// 优先使用 deps/bin-go(Go 绑定对应版本,与 Python 版的 deps/bin 隔离),
// 依次尝试 exe 同目录 / exe 上级目录 / exe 的 deps 子目录
func resolveLibDir() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	exeDir := filepath.Dir(exe)
	candidates := []string{
		filepath.Join(exeDir, "deps", "bin-go"),
		filepath.Join(exeDir, "..", "deps", "bin-go"),
		filepath.Join(exeDir, "deps", "bin"),
		filepath.Join(exeDir, "..", "deps", "bin"),
		exeDir,
	}
	for _, c := range candidates {
		if st, err := os.Stat(filepath.Join(c, "MaaFramework.dll")); err == nil && !st.IsDir() {
			abs, err := filepath.Abs(c)
			if err != nil {
				return "", err
			}
			return abs, nil
		}
	}
	return "", fmt.Errorf("MaaFramework.dll not found near %s", exeDir)
}

func userPath() string {
	if cwd, err := os.Getwd(); err == nil {
		return cwd
	}
	return "."
}
