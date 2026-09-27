package action

import (
	"encoding/json"
)

// CombatRepetitionCount 出征/罐头次数计数器(替代 Python combat.py 的类变量)
type combatRepetitionCount struct {
	Count       int
	Limit       int
	initialized bool
	fromOCR     bool   // Limit 是否由 setMonsterCount(OCR 识别)设置,beginCombat 保持不覆盖
	owner       string // 当前 Limit 归属的任务("monster");其他任务残留时 beginCombat 会接管重置
}

var combatCount = &combatRepetitionCount{}

func (c *combatRepetitionCount) Init(limit int) {
	if !c.initialized {
		c.Limit = limit
		c.initialized = true
	}
}

// InitFromOCR 由 setMonsterCount(OCR 识别剩余次数)设置 Limit,标记为 OCR 来源
func (c *combatRepetitionCount) InitFromOCR(limit int) {
	c.Limit = limit
	c.initialized = true
	c.fromOCR = true
	c.owner = "monster"
}

func (c *combatRepetitionCount) AddCount(step int) {
	c.Count += step
}

func (c *combatRepetitionCount) SetCount(data int) { c.Count = data }

func (c *combatRepetitionCount) SetLimit(data int) { c.Limit = data }

func (c *combatRepetitionCount) Reset() {
	c.Count = 0
	c.Limit = 0
	c.initialized = false
	c.fromOCR = false
	c.owner = ""
}

func (c *combatRepetitionCount) IsReachLimit() bool {
	return c.Limit > 0 && c.Count >= c.Limit
}

// 队伍 ROI(与 Python combat.py / bear.py / garrison.py / join.py 一致)
// 索引 0 为默认队伍,无需点击
var teamROI = [9][4]int{
	{0, 0, 0, 0},
	{56, 117, 22, 15},
	{127, 115, 26, 23},
	{204, 113, 16, 25},
	{270, 113, 35, 26},
	{349, 117, 22, 22},
	{416, 112, 23, 32},
	{494, 113, 30, 28},
	{565, 113, 30, 29},
}

// 撤回队伍 ROI(与 Python common.py RecallTeam 一致)
var recallTeamROI = [7][4]int{
	{0, 0, 0, 0},
	{200, 552, 45, 45},
	{200, 488, 45, 45},
	{200, 427, 45, 45},
	{200, 371, 45, 45},
	{200, 313, 45, 45},
	{200, 246, 45, 45},
}

func jsonParam(param string) map[string]any {
	m := map[string]any{}
	if param == "" {
		return m
	}
	_ = json.Unmarshal([]byte(param), &m)
	return m
}

func jsonParamStr(param, key string) string {
	m := jsonParam(param)
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func jsonParamInt(param, key string, def int) int {
	m := jsonParam(param)
	switch v := m[key].(type) {
	case float64:
		return int(v)
	case string:
		n := 0
		neg := false
		i := 0
		if i < len(v) && (v[i] == '-' || v[i] == '+') {
			neg = v[i] == '-'
			i++
		}
		for ; i < len(v); i++ {
			if v[i] < '0' || v[i] > '9' {
				break
			}
			n = n*10 + int(v[i]-'0')
		}
		if neg {
			n = -n
		}
		return n
	}
	return def
}
