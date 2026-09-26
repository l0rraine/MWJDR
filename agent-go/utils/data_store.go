package utils

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
)

// MWJDR 数据持久化工具
// 数据文件位于 config/mwjdr_data.json(优先使用 MFA_DATA_ROOT 下的 config 目录),按角色ID分桶存储

// 默认时间戳:2003年的一个时间戳,确保任何日期检查都不匹配
const DefaultTimestampMs int64 = 1058306766000

// GetDataFilePath 获取数据文件路径,优先使用 MFA_DATA_ROOT 下的 config 目录
func GetDataFilePath() string {
	dataRoot := os.Getenv("MFA_DATA_ROOT")
	if dataRoot != "" {
		if st, err := os.Stat(dataRoot); err == nil && st.IsDir() {
			return filepath.Join(dataRoot, "config", "mwjdr_data.json")
		}
	}
	return filepath.Join("config", "mwjdr_data.json")
}

// LoadData 加载数据文件,文件不存在时返回空字典
func LoadData() map[string]any {
	dataFile := GetDataFilePath()
	if _, err := os.Stat(dataFile); err != nil {
		_ = os.MkdirAll(filepath.Dir(dataFile), 0755)
		return map[string]any{}
	}
	raw, err := os.ReadFile(dataFile)
	if err != nil {
		Warningf("读取数据文件失败: %v", err)
		return map[string]any{}
	}
	var data map[string]any
	if err := json.Unmarshal(raw, &data); err != nil {
		Warningf("解析数据文件失败: %v", err)
		return map[string]any{}
	}
	return data
}

// SaveData 保存数据到文件
func SaveData(data map[string]any) bool {
	dataFile := GetDataFilePath()
	if err := os.MkdirAll(filepath.Dir(dataFile), 0755); err != nil {
		Warningf("写入数据文件失败: %v", err)
		return false
	}
	raw, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		Warningf("序列化数据失败: %v", err)
		return false
	}
	if err := os.WriteFile(dataFile, raw, 0644); err != nil {
		Warningf("写入数据文件失败: %v", err)
		return false
	}
	return true
}

// GetAccountBucket 获取角色分桶数据
func GetAccountBucket(data map[string]any, key, accountID string) map[string]any {
	store, ok := data[key].(map[string]any)
	if !ok {
		store = map[string]any{}
		data[key] = store
	}

	if accountID != "" {
		normalized := strings.TrimSpace(accountID)
		if bucket, ok := store[normalized].(map[string]any); ok {
			return bucket
		}
		bucket := map[string]any{}
		store[normalized] = bucket
		return bucket
	}

	const defaultKey = "__default__"
	if bucket, ok := store[defaultKey].(map[string]any); ok {
		return bucket
	}
	bucket := map[string]any{}
	store[defaultKey] = bucket
	return bucket
}

// GetTimestamp 获取某条记录的时间戳
func GetTimestamp(data map[string]any, category, accountID, item string) int64 {
	bucket := GetAccountBucket(data, category, accountID)
	if v, ok := bucket[item].(float64); ok {
		return int64(v)
	}
	return DefaultTimestampMs
}

// SetTimestamp 设置某条记录的时间戳
func SetTimestamp(data map[string]any, category, accountID, item string, tsMs int64) {
	bucket := GetAccountBucket(data, category, accountID)
	bucket[item] = tsMs
}
