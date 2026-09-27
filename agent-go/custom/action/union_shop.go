package action

import (
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

const (
	unionShopDir = "联盟商店"
	unionTZItem  = "统帅经验"
)

var (
	unionParamPrefix    = "联盟商店_参数_"
	unionDisabledLabels = map[string]bool{}
	unionEnabledNames   []string

	// 识别范围: [第一轮, 滚动后]
	unionScanROIs = [2][4]int{{11, 184, 698, 1001}, {9, 903, 697, 296}}
	// 从75%折扣box计算物品/联盟币区域
	unionItemFromDiscount = [4]int{33, 30, 82, 92}
	unionCoinFromDiscount = [4]int{22, 162, -47, -32}
	unionCoinFromTZ       = [4]int{-37, 104, -85, -53}
)

// RegisterUnionShopActions 注册联盟商店 action
func RegisterUnionShopActions() {
	_ = maa.AgentServerRegisterCustomAction("联盟商店_购买",
		maa.CustomActionFunc(unionShopPurchase))
}

// 联盟商店_购买
func unionShopPurchase(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	// 从JSON读取选项列表
	unionEnabledNames = nil
	for _, paramName := range NodeNextNames(ctx, "联盟商店_选项") {
		if paramName == "" {
			continue
		}
		if NodeEnabled(ctx, paramName) {
			unionEnabledNames = append(unionEnabledNames, trimPrefixLocal(paramName, unionParamPrefix))
		}
	}

	if len(unionEnabledNames) == 0 {
		utils.Info("联盟商店无启用选项,跳过")
	} else {
		utils.Debugf("联盟商店启用选项: %v", unionEnabledNames)
	}

	for _, roi := range unionScanROIs {
		unionBuyTZ(ctx, roi)
		unionBuyDiscount(ctx, roi)
		_, _ = ctx.RunTask("联盟商店_滚动")
	}

	utils.Info("联盟商店购买完成,记录日期")
	utils.SaveTaskDate("联盟商店")
	unionDisabledLabels = map[string]bool{}
	utils.DisableSwitch(ctx, "联盟商店_开关")

	return true
}

// unionBuyTZ 统帅经验:直接匹配模板购买
func unionBuyTZ(ctx *maa.Context, roi [4]int) {
	if !containsStr(unionEnabledNames, unionTZItem) || unionDisabledLabels[unionTZItem] {
		return
	}

	detail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
		&maa.TemplateMatchParam{Template: []string{unionShopDir + "/" + unionTZItem + ".png"}, ROI: maa.NewTargetRect(roi)},
		mustScreenCap(ctx))
	if detail == nil || !detail.Hit {
		return
	}

	for _, r := range detail.Results.Filtered {
		var matchBox maa.Rect
		var matchOK bool
		if tm, ok := r.AsTemplateMatch(); ok {
			matchBox = tm.Box
			matchOK = true
		}
		if !matchOK {
			continue
		}
		coinROI := utils.AddOffset(matchBox, unionCoinFromTZ)
		coinDetail, _ := ctx.RunRecognition("联盟商店_联盟币", mustScreenCap(ctx),
			map[string]any{"联盟商店_联盟币": map[string]any{"roi": coinROI}})
		if coinDetail == nil || !coinDetail.Hit {
			continue
		}
		utils.ClickRect(ctx, coinROI)
		utils.Infof("点击联盟币购买 %s", unionTZItem)
		time.Sleep(1 * time.Second)
		unionHandleConfirm(ctx, unionTZItem)
		if unionDisabledLabels[unionTZItem] {
			break
		}
	}
}

// unionBuyDiscount 折扣物品:先找75%,再识别物品,检查联盟币后购买
func unionBuyDiscount(ctx *maa.Context, roi [4]int) {
	discountEnabled := make([]string, 0)
	for _, n := range unionEnabledNames {
		if n != unionTZItem {
			discountEnabled = append(discountEnabled, n)
		}
	}
	if len(discountEnabled) == 0 {
		return
	}

	detail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
		&maa.TemplateMatchParam{Template: []string{unionShopDir + "/75%.png"}, ROI: maa.NewTargetRect(roi)},
		mustScreenCap(ctx))
	if detail == nil || !detail.Hit {
		return
	}

	matches := make([]maa.Rect, 0)
	for _, r := range detail.Results.Filtered {
		if tm, ok := r.AsTemplateMatch(); ok {
			matches = append(matches, tm.Box)
		}
	}
	utils.Debugf("联盟商店识别到 %d 个75%%折扣标签", len(matches))

	for _, matchBox := range matches {
		itemROI := utils.AddOffset(matchBox, unionItemFromDiscount)
		coinROI := utils.AddOffset(matchBox, unionCoinFromDiscount)

		// 识别物品:在反算的物品区域内逐个匹配折扣模板
		identifyImg := mustScreenCap(ctx)
		name := ""
		for _, n := range discountEnabled {
			if unionDisabledLabels[n] {
				continue
			}
			d, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
				&maa.TemplateMatchParam{Template: []string{unionShopDir + "/" + n + ".png"}, ROI: maa.NewTargetRect(itemROI)},
				identifyImg)
			if d != nil && d.Hit {
				name = n
				break
			}
		}
		if name == "" {
			continue
		}

		// 检查联盟币
		coinDetail, _ := ctx.RunRecognition("联盟商店_联盟币", mustScreenCap(ctx),
			map[string]any{"联盟商店_联盟币": map[string]any{"roi": coinROI}})
		if coinDetail == nil || !coinDetail.Hit {
			utils.Debug("联盟币取色不匹配,跳过")
			continue
		}

		utils.ClickRect(ctx, coinROI)
		utils.Infof("点击联盟币购买 %s", name)
		time.Sleep(1 * time.Second)
		unionHandleConfirm(ctx, name)
		if unionDisabledLabels[name] {
			break
		}
	}
}

// unionHandleConfirm 处理购买确认对话框
func unionHandleConfirm(ctx *maa.Context, name string) {
	confirmDetail, _ := ctx.RunRecognition("联盟商店_确定购买", mustScreenCap(ctx))
	if confirmDetail != nil && confirmDetail.Hit {
		_, _ = ctx.RunTask("联盟商店_确定购买")
		badgeDetail, _ := ctx.RunRecognition("联盟商店_获取更多", mustScreenCap(ctx))
		if badgeDetail != nil && badgeDetail.Hit {
			for i := 0; i < 3; i++ {
				_, _ = ctx.RunTask("联盟商店_关闭提示")
			}
			unionDisabledLabels[name] = true
			utils.Warningf("联盟币不足,禁用 %s 的购买", name)
		} else {
			utils.Infof("购买 %s 成功", name)
		}
	} else {
		utils.Debug("未出现确定购买对话框")
	}
}
