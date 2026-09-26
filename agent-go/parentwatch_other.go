//go:build !windows

package main

// 非 Windows 平台不做父进程监控(本项目运行于 Windows)
func watchParent(pid int) {}
