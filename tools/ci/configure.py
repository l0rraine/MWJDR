from pathlib import Path

import shutil

assets_dir = Path(__file__).parent.parent.parent / "assets"


def configure_ocr_model():
    # Maa 从 {resource}/base 下加载 OCR 模型（interface.json 的 resource path 为 {PROJECT_DIR}/resource/base），
    # 必须复制到 base/model/ocr，而非顶层 model/ocr
    # PP-OCRv5 mobile：相比 v4 det Hmean 63.8→79.0、rec 78.74→81.29，
    # det 体积/耗时基本不变，rec 体积 10.5→16MB、CPU 耗时 +21%（详见 knowledge.md）
    shutil.copytree(
        assets_dir / "MaaCommonAssets" / "OCR" / "ppocr_v5" / "zh_cn",
        assets_dir / "resource" / "base" / "model" / "ocr",
        dirs_exist_ok=True,
    )


if __name__ == "__main__":
    configure_ocr_model()
