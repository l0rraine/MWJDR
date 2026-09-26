package utils

import (
	"image"
	"image/png"
	"os"
	"path/filepath"
	"regexp"
	"time"

	"github.com/MaaXYZ/maa-framework-go/v4"
)

var textCleanRe = regexp.MustCompile(`[*?]`)

// tempDir 定位项目根下的 temp 目录(与 Python 的 agent/../.. 相对路径一致)
func tempDir() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	projectRoot := filepath.Dir(filepath.Dir(exe))
	dir := filepath.Join(projectRoot, "temp")
	if err := os.MkdirAll(dir, 0755); err != nil {
		return "", err
	}
	return dir, nil
}

// ScreenShot 截图保存到 temp/ 目录
func ScreenShot(ctx *maa.Context, text string) {
	img, err := ScreenCap(ctx)
	if err != nil {
		Warningf("截图失败: %v", err)
		return
	}
	dir, err := tempDir()
	if err != nil {
		Warningf("创建 temp 目录失败: %v", err)
		return
	}

	text = textCleanRe.ReplaceAllString(text, "")
	name := ""
	if text != "" {
		name = text + "_"
	}
	now := time.Now()
	name = name + now.Format("20060102150405.") + msOf(now) + ".png"
	path := filepath.Join(dir, name)

	f, err := os.Create(path)
	if err != nil {
		Warningf("保存截图失败: %v", err)
		return
	}
	defer f.Close()
	if err := png.Encode(f, img); err != nil {
		Warningf("编码截图失败: %v", err)
		return
	}
	Debugf("截图保存至 temp/%s", name)
}

func msOf(t time.Time) string {
	return t.Format(".000")[1:4]
}

// CropImage 裁剪图像区域 [x, y, w, h](对应 Python numpy 的 img[y:y+h, x:x+w])
func CropImage(img image.Image, x, y, w, h int) image.Image {
	rect := image.Rect(x, y, x+w, y+h)
	return cropBounds(img, rect)
}

func cropBounds(img image.Image, r image.Rectangle) image.Image {
	b := img.Bounds().Intersect(r)
	if b.Empty() {
		return image.NewRGBA(image.Rect(0, 0, 0, 0))
	}
	// 通用裁剪:逐像素拷贝到新图(与 numpy 裁剪语义一致,不依赖具体类型)
	out := image.NewRGBA(image.Rect(0, 0, b.Dx(), b.Dy()))
	for y := b.Min.Y; y < b.Max.Y; y++ {
		for x := b.Min.X; x < b.Max.X; x++ {
			out.Set(x-b.Min.X, y-b.Min.Y, img.At(x, y))
		}
	}
	return out
}
