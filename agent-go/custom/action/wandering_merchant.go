package action

import (
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"

	"github.com/l0rraine/MWJDR/agent-go/utils"
)

// 游荡商人钻石刷新次数
var merchantDiamondUsed = 0

// RegisterWanderingMerchantActions 注册游荡商人 action
func RegisterWanderingMerchantActions() {
	_ = maa.AgentServerRegisterCustomAction("游荡商人_钻石刷新",
		maa.CustomActionFunc(merchantDiamondRefresh))
}

// 游荡商人_钻石刷新
func merchantDiamondRefresh(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	diamondLimit := jsonParamInt(arg.CustomActionParam, "钻石刷新次数", 0)

	// 第一步:尝试免费刷新
	img, _ := utils.ScreenCap(ctx)
	freeDetail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
		&maa.TemplateMatchParam{Template: []string{"流浪商人/免费刷新.png"}, ROI: maa.NewTargetRect(maa.Rect{511, 213, 171, 96})},
		img)
	if freeDetail != nil && freeDetail.Hit {
		utils.Info("发现免费刷新,点击刷新")
		utils.ClickRect(ctx, freeDetail.Box)
		time.Sleep(1500 * time.Millisecond)
		return true
	}

	// 第二步:没有免费刷新了
	if diamondLimit == 0 {
		utils.Info("免费刷新已用完,不使用钻石刷新,记录日期")
		merchantEnd(ctx)
		_ = ctx.OverrideNext("游荡商人_刷新控制", []maa.NextItem{{Name: "商店购买_入口"}})
		return true
	}

	// 第三步:执行钻石刷新
	if merchantDiamondUsed < diamondLimit {
		img, _ := utils.ScreenCap(ctx)
		diamondDetail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeTemplateMatch,
			&maa.TemplateMatchParam{Template: []string{"流浪商人/钻石刷新.png"}, ROI: maa.NewTargetRect(maa.Rect{523, 229, 137, 68})},
			img)
		if diamondDetail != nil && diamondDetail.Hit {
			utils.ClickRect(ctx, diamondDetail.Box)
			time.Sleep(1 * time.Second)

			// 处理确认对话框
			img, _ := utils.ScreenCap(ctx)
			confirmDetail, _ := ctx.RunRecognitionDirect(maa.RecognitionTypeOCR,
				&maa.OCRParam{Expected: []string{"提示"}, ROI: maa.NewTargetRect(maa.Rect{308, 416, 96, 60})},
				img)
			if confirmDetail != nil && confirmDetail.Hit {
				utils.Debugf("钻石刷新确认对话框识别结果:%s", utils.BestText(confirmDetail))
				utils.ClickRect(ctx, maa.Rect{465, 768, 100, 44})
				time.Sleep(1 * time.Second)
			} else {
				utils.Debug("钻石刷新确认对话框识别结果:未识别到提示")
			}

			merchantDiamondUsed++
			utils.Infof("钻石刷新第%d次", merchantDiamondUsed)
			return true
		}
	}

	// 第四步:钻石刷新次数已达上限
	utils.Infof("钻石刷新次数已达上限(%d次),记录日期", diamondLimit)
	merchantEnd(ctx)
	_ = ctx.OverrideNext("游荡商人_刷新控制", []maa.NextItem{{Name: "商店购买_入口"}})
	return true
}

func merchantEnd(ctx *maa.Context) {
	utils.SaveTaskDate("游荡商人")
	merchantDiamondUsed = 0
	utils.DisableSwitch(ctx, "游荡商人_开关")
}
