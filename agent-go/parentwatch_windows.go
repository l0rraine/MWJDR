//go:build windows

package main

import (
	"os"

	"golang.org/x/sys/windows"
)

// watchParent 监控父进程,父进程退出后立刻退出本进程。
// 通过一次性 OpenProcess(SYNCHRONIZE) 持有句柄,避免 PID 复用误判。
func watchParent(pid int) {
	h, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
	if err != nil {
		// 无法打开父进程句柄(可能已退出),直接退出
		os.Exit(0)
	}
	defer windows.CloseHandle(h)

	for {
		ev, err := windows.WaitForSingleObject(h, 5000)
		if err != nil {
			return
		}
		// 句柄被信号化 = 进程已退出
		if ev == uint32(windows.WAIT_OBJECT_0) {
			os.Exit(0)
		}
	}
}
