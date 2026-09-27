package action

// 梦境关卡数据(关卡 1-4,按关卡拆分为 4 个文件便于维护):
//   dream_stages_part1.go  关卡 1
//   dream_stages_part2.go  关卡 2
//   dream_stages_part3.go  关卡 3
//   dream_stages_part4.go  关卡 4
// 原数据由 tools/convert_dream.py 从 Python 源生成;现按关卡拆分,手工维护。

func dreamStageData(episode, level string) []dreamItem {
	m, ok := dreamStageMap[episode]
	if !ok {
		return nil
	}
	return m[level]
}

func dreamTeamData(episode, level string) []dreamItem {
	m, ok := dreamTeamMap[episode]
	if !ok {
		return nil
	}
	return m[level]
}

var dreamStageMap = map[string]map[string][]dreamItem{}
var dreamTeamMap = map[string]map[string][]dreamItem{}

func init() {
	for k, v := range dreamStageMapPart1 {
		dreamStageMap[k] = v
	}
	for k, v := range dreamStageMapPart2 {
		dreamStageMap[k] = v
	}
	for k, v := range dreamStageMapPart3 {
		dreamStageMap[k] = v
	}
	for k, v := range dreamStageMapPart4 {
		dreamStageMap[k] = v
	}
	for k, v := range dreamTeamMapPart1 {
		dreamTeamMap[k] = v
	}
	for k, v := range dreamTeamMapPart2 {
		dreamTeamMap[k] = v
	}
	for k, v := range dreamTeamMapPart3 {
		dreamTeamMap[k] = v
	}
	for k, v := range dreamTeamMapPart4 {
		dreamTeamMap[k] = v
	}
}
