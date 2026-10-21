package utils

import "testing"

// stderrLine 是与 MFAAvalonia 的跨进程契约:
// 行首 "level:" 供 CheckShouldLog 识别级别,内容为 HTML,
// 由日志面板的 Markdown+HtmlPlugin 渲染颜色。改动格式需同步确认 MFA 侧行为。
func TestStderrLine(t *testing.T) {
	cases := []struct {
		short, msg, want string
	}{
		{"info", "派出挖矿队伍:肉", `info:<font color="Black">派出挖矿队伍:肉</font>`},
		{"debug", "OCR第1次: '8'", `debug:<font color="DeepSkyBlue">OCR第1次: &#39;8&#39;</font>`},
		{"warn", "降级搜索超限", `warn:<font color="Orange">降级搜索超限</font>`},
		{"err", "连接失败 <超时>", `err:<font color="OrangeRed">连接失败 &lt;超时&gt;</font>`},
		{"unknown", "x", `unknown:<font color="Black">x</font>`},
		{"info", "多行\n消息两", `info:<font color="Black">多行 消息两</font>`},
	}
	for _, c := range cases {
		if got := stderrLine(c.short, c.msg); got != c.want {
			t.Errorf("stderrLine(%q,%q) =\n  %s\nwant:\n  %s", c.short, c.msg, got, c.want)
		}
	}
}
