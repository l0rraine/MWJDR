package utils

import (
	"image"
	"math/rand"

	"github.com/MaaXYZ/maa-framework-go/v4"
)

// RandomClickPoint 在识别区域内生成随机点击坐标 [x, x+w] / [y, y+h]
func RandomClickPoint(box maa.Rect) (int, int) {
	rx := box[0] + rand.Intn(box[2]+1)
	ry := box[1] + rand.Intn(box[3]+1)
	return rx, ry
}

// ClickRect 在识别区域内随机点击
func ClickRect(ctx *maa.Context, box maa.Rect) {
	rx, ry := RandomClickPoint(box)
	ctrl := ctx.GetTasker().GetController()
	ctrl.PostClick(int32(rx), int32(ry)).Wait()
}

// ScreenCap 获取当前屏幕截图(与 Python post_screencap().wait().get() 等价)
func ScreenCap(ctx *maa.Context) (image.Image, error) {
	ctrl := ctx.GetTasker().GetController()
	ctrl.PostScreencap().Wait()
	return ctrl.CacheImage()
}
