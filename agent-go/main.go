package main

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"

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

// resolveLibDir 定位 MaaFramework 动态库目录。
// 搜索顺序(参考 MaaEnd 的 cwd/maafw 约定 + 常见发布布局):
//   1. 环境变量 MAA_LIB_DIR(显式指定,最高优先)
//   2. exe 同目录(DLL 与 exe 一起发布)
//   3. exe 下的 deps/bin-go、deps/bin、deps(开发/发布布局)
//   4. exe 上级目录的 deps/bin-go、deps/bin、deps(仓库源码布局)
//   5. 工作目录下的 maafw、deps/bin-go、deps/bin、deps(MaaEnd 风格)
// 找不到时返回完整搜索路径便于诊断。
func resolveLibDir() (string, error) {
	// 1. 环境变量显式指定
	if env := os.Getenv("MAA_LIB_DIR"); env != "" {
		if st, err := os.Stat(filepath.Join(env, "MaaFramework.dll")); err == nil && !st.IsDir() {
			abs, _ := filepath.Abs(env)
			return abs, nil
		}
		utils.Warningf("MAA_LIB_DIR 中未找到 MaaFramework.dll: %s", env)
	}

	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	exeDir := filepath.Dir(exe)
	cwd, _ := os.Getwd()

	var candidates []string
	seen := map[string]bool{}
	add := func(p string) {
		abs, err := filepath.Abs(p)
		if err != nil {
			return
		}
		if !seen[abs] {
			seen[abs] = true
			candidates = append(candidates, abs)
		}
	}

	// 2. exe 同目录
	add(exeDir)
	// 3. exe 下的 deps 子目录
	add(filepath.Join(exeDir, "deps", "bin-go"))
	add(filepath.Join(exeDir, "deps", "bin"))
	add(filepath.Join(exeDir, "deps"))
	// 4. exe 上级目录的 deps
	add(filepath.Join(exeDir, "..", "deps", "bin-go"))
	add(filepath.Join(exeDir, "..", "deps", "bin"))
	add(filepath.Join(exeDir, "..", "deps"))
	// 5. 工作目录
	add(filepath.Join(cwd, "maafw"))
	add(filepath.Join(cwd, "deps", "bin-go"))
	add(filepath.Join(cwd, "deps", "bin"))
	add(filepath.Join(cwd, "deps"))

	for _, c := range candidates {
		if st, err := os.Stat(filepath.Join(c, "MaaFramework.dll")); err == nil && !st.IsDir() {
			return c, nil
		}
	}
	return "", fmt.Errorf("MaaFramework.dll not found; searched:\n  %s",
		strings.Join(candidates, "\n  "))
}

func userPath() string {
	if cwd, err := os.Getwd(); err == nil {
		return cwd
	}
	return "."
}
