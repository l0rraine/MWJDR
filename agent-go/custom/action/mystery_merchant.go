package action

import (
	"image"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

const mysteryShopDir = "神秘商店"

var (
	mysteryParamPrefix  = "神秘商店_参数_"
	mysteryDisabled50   = map[string]bool{}
	mysteryEnabledNames []string
	mysteryDiamondUsed  = 0

	mysteryScreen1Slots = [5][4]int{
		{240, 419, 241, 286}, {480, 419, 220, 280}, {14, 708, 227, 281},
		{242, 708, 234, 285}, {477, 709, 229, 280},
	}
	mysteryScreen2Slots = [3][4]int{
		{14, 909, 231, 280}, {245, 909, 228, 279}, {472, 914, 235, 272},
	}
	// 从50%折扣box计算的offset
	mysteryItemFrom50  = [4]int{41, 32, 67, 82}
	mysteryColorFrom50 = [4]int{36, 171, -37, -31}
	mysteryBuyFrom50   = [4]int{57, 212, 53, -16}
)

// RegisterMysteryMerchantActions 注册神秘商店 action
func RegisterMysteryMerchantActions() {
	_ = maa.AgentServerRegisterCustomAction("神秘商店_购买",
		maa.CustomActionFunc(mysteryMerchantPurchase))
}

// 神秘商店_购买
func mysteryMerchantPurchase(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	diamondLimit := jsonParamInt(arg.CustomActionParam, "钻石刷新次数", 0)
	_, _ = ctx.RunTask("神秘商店_下滑")
	// 截取专武模板(当季专武图片从界面截取)
	time.Sleep(500 * time.Millisecond)
	img, err := utils.ScreenCap(ctx)
	if err == nil {
		// numpy 的 img[490:542, 85:194] → 图像区域 (85,490)-(194,542)
		weaponImg := utils.CropImage(img, 85, 490, 194-85, 542-490)
		_ = ctx.OverrideImage(mysteryShopDir+"/当季专武.png", weaponImg)
		utils.Debug("已截取专武模板图片")
	}

	// 从JSON读取选项列表
	mysteryEnabledNames = nil
	for _, paramName := range NodeNextNames(ctx, "神秘商店_选项") {
		if paramName == "" {
			continue
		}
		if NodeEnabled(ctx, paramName) {
			mysteryEnabledNames = append(mysteryEnabledNames, trimPrefixLocal(paramName, mysteryParamPrefix))
		}
	}

	if len(mysteryEnabledNames) == 0 {
		utils.Info("神秘商店无启用选项,仅购买免费物品")
	} else {
		utils.Debugf("神秘商店启用选项: %v", mysteryEnabledNames)
	}

	// 购买循环
	for {
		_, _ = ctx.RunTask("神秘商店_下滑")
		mysterySearchSlots(ctx, mysteryScreen1Slots[:])

		_, _ = ctx.RunTask("神秘商店_上滑")
		mysterySearchSlots(ctx, mysteryScreen2Slots[:])

		// 尝试刷新
		if mysteryTryFreeRefresh(ctx) {
			continue
		}
		if mysteryTryDiamondRefresh(ctx, diamondLimit) {
			continue
		}
		break
	}

	// 结束
	utils.Info("神秘商店购买完成,记录日期")
	utils.SaveTaskDate("神秘商店")
	mysteryDisabled50 = map[string]bool{}
	mysteryDiamondUsed = 0
	utils.DisableSwitch(ctx, "神秘商店_开关")

	return true
}

func mysterySearchSlots(ctx *maa.Context, slots [][4]int) {
	for _, slotROI := range slots {
		mysteryTryBuySlot(ctx, slotROI)
	}
}

func mysteryTryBuySlot(ctx *maa.Context, slotROI [4]int) {
	// 检查免费
	img := mustScreenCap(ctx)
	freeDetail, _ := ctx.RunRecognition("神秘商店_免费", img,
		map[string]any{"神秘商店_免费": map[string]any{"roi": slotROI}})
	if freeDetail != nil && freeDetail.Hit {
		utils.ClickRect(ctx, freeDetail.Box)
		utils.Info("发现免费物品,购买")
		time.Sleep(1 * time.Second)
		mysteryHandleConfirm(ctx, "免费物品")
		return
	}

	// 检查50%折扣
	discountDetail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
		&maa.TemplateMatchParam{Template: []string{mysteryShopDir + "/50%.png"}, ROI: maa.NewTargetRect(slotROI)},
		mustScreenCap(ctx))
	if discountDetail == nil || !discountDetail.Hit {
		return
	}

	// 取色检查徽章
	colorROI := utils.AddOffset(discountDetail.Box, mysteryColorFrom50)
	colorDetail, _ := ctx.RunRecognition("神秘商店_徽章", mustScreenCap(ctx),
		map[string]any{"神秘商店_徽章": map[string]any{"roi": colorROI}})
	if colorDetail == nil || !colorDetail.Hit {
		utils.Debug("50%标签取色不匹配,跳过")
		return
	}

	// 识别物品
	itemROI := utils.AddOffset(discountDetail.Box, mysteryItemFrom50)
	identifyImg := mustScreenCap(ctx)
	name := ""
	for _, n := range mysteryEnabledNames {
		if mysteryDisabled50[n] {
			continue
		}
		d, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
			&maa.TemplateMatchParam{Template: []string{mysteryShopDir + "/" + n + ".png"}, ROI: maa.NewTargetRect(itemROI)},
			identifyImg)
		if d != nil && d.Hit {
			name = n
			break
		}
	}
	if name == "" {
		return
	}

	// 点击购买
	buyROI := utils.AddOffset(discountDetail.Box, mysteryBuyFrom50)
	utils.ClickRect(ctx, buyROI)
	time.Sleep(1 * time.Second)
	mysteryHandleConfirm(ctx, name)
}

// mysteryHandleConfirm 处理购买确认对话框
func mysteryHandleConfirm(ctx *maa.Context, name string) {
	_, _ = ctx.RunTask("神秘商店_确定购买")
	badgeDetail, _ := ctx.RunRecognition("神秘商店_获取更多", mustScreenCap(ctx))
	if badgeDetail != nil && badgeDetail.Hit {
		_, _ = ctx.RunTask("神秘商店_关闭提示")
		mysteryDisabled50[name] = true
		utils.Warningf("徽章不足,禁用%s的50%%购买", name)
	} else {
		utils.Infof("50%%购买%s成功", name)
	}
}

func mysteryTryFreeRefresh(ctx *maa.Context) bool {
	detail, _ := ctx.RunRecognition("神秘商店_免费刷新", mustScreenCap(ctx))
	if detail != nil && detail.Hit {
		utils.ClickRect(ctx, detail.Box)
		utils.Info("神秘商店免费刷新")
		time.Sleep(1500 * time.Millisecond)
		return true
	}
	return false
}

func mysteryTryDiamondRefresh(ctx *maa.Context, diamondLimit int) bool {
	if diamondLimit <= 0 || mysteryDiamondUsed >= diamondLimit {
		return false
	}

	detail, _ := ctx.RunRecognition("神秘商店_钻石刷新", mustScreenCap(ctx))
	if detail != nil && detail.Hit {
		utils.ClickRect(ctx, detail.Box)
		time.Sleep(1 * time.Second)

		// 钻石购买确认
		confirmDetail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeOCR,
			&maa.OCRParam{Expected: []string{"提示"}, ROI: maa.NewTargetRect(maa.Rect{308, 416, 96, 60})},
			mustScreenCap(ctx))
		if confirmDetail != nil && confirmDetail.Hit {
			utils.Debugf("钻石刷新确认对话框识别结果:%s", utils.BestText(confirmDetail))
			utils.ClickRect(ctx, maa.Rect{465, 768, 100, 44})
			time.Sleep(1 * time.Second)
		} else {
			utils.Debug("钻石刷新确认对话框识别结果:未识别到提示")
		}

		mysteryDiamondUsed++
		utils.Infof("神秘商店钻石刷新第%d次,共%d次", mysteryDiamondUsed, diamondLimit)
		return true
	}
	return false
}

func mustScreenCap(ctx *maa.Context) image.Image {
	img, _ := utils.ScreenCap(ctx)
	return img
}

func trimPrefixLocal(s, prefix string) string {
	if len(s) >= len(prefix) && s[:len(prefix)] == prefix {
		return s[len(prefix):]
	}
	return s
}
