package utils

import "strings"

// AccountID 全局角色ID缓存(替代 Python custom/reco/record_id.py 的类变量)
var AccountID string

// CurrentAccountID 获取当前角色ID
func CurrentAccountID() string {
	return strings.TrimSpace(AccountID)
}
