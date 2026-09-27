# -*- coding: utf-8 -*-
"""更新 deps/bin-go 中的 MaaFramework DLL。

原理: Go 绑定(github.com/MaaXYZ/maa-framework-go/v4)跟踪 MaaFramework 的
最新 release,README 徽章标注对应版本。deps/bin-go 的 DLL 取自同版本的
maafw(Python 绑定)wheel,保证整套 DLL 版本一致。

用法:
    python tools/update_bin_go.py                 # 用 Go 绑定 README 标注的版本更新
    python tools/update_bin_go.py 5.11.0          # 指定版本更新
    python tools/update_bin_go.py --check         # 仅检查当前版本是否对齐,不更新

注意事项:
    - DLL 必须整套替换(只换 MaaFramework.dll 会因依赖 DLL 版本不匹配而失败)
    - deps/bin-go 与 Python 版的 deps/bin 相互独立,互不影响
    - 更新后重新 go build,并用 agent-go.exe 冒烟测试(MAA init + AgentServer 启动)
    - 升级 Go 绑定: cd agent-go && go get github.com/MaaXYZ/maa-framework-go/v4@latest
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # agent-go/
PROJECT = ROOT.parent                          # 项目根
BIN_GO = PROJECT / "deps" / "bin-go"
GOMODCACHE = Path(os.environ.get("GOMODCACHE", str(Path.home() / "go" / "pkg" / "mod")))

MAA_DLL = "MaaFramework.dll"


def go_binding_version() -> str:
    """从 Go 绑定 README 徽章提取要求的 MaaFramework 版本。"""
    mods = sorted(glob.glob(str(GOMODCACHE / "github.com" / "!maa!x!y!z" / "maa-framework-go" / "v4@*")))
    if not mods:
        return ""
    readme = Path(mods[-1]) / "README.md"
    if not readme.exists():
        return ""
    text = readme.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"MaaFramework-v([\d.]+)", text)
    return m.group(1) if m else ""


def current_version() -> str:
    """从当前 DLL 判断版本(通过同版本 maafw wheel 无法直接读,返回 'unknown')。"""
    return "unknown"


def download_maafw(version: str, workdir: Path) -> Path:
    """pip download maafw==version,返回 wheel 路径。"""
    print(f"[1/4] pip download maafw=={version} ...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "download", f"maafw=={version}",
         "--no-deps", "-d", str(workdir), "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit(f"pip download 失败,请确认版本号存在: maafw=={version}")
    wheels = list(workdir.glob("maafw-*.whl"))
    if not wheels:
        sys.exit("未找到下载的 wheel")
    return wheels[0]


def extract_dlls(wheel: Path, workdir: Path) -> Path:
    """解压 wheel,返回 DLL 目录(maa/bin)。"""
    print(f"[2/4] 解压 {wheel.name} ...")
    zf = zipfile.ZipFile(wheel)
    zf.extractall(workdir)
    zf.close()
    bin_dir = workdir / "maa" / "bin"
    if not (bin_dir / MAA_DLL).exists():
        sys.exit("wheel 中未找到 MaaFramework.dll")
    return bin_dir


def verify_dlls(bin_dir: Path) -> bool:
    """校验关键 DLL 完整。"""
    required = [MAA_DLL, "MaaToolkit.dll", "MaaAgentServer.dll", "MaaAgentClient.dll",
                "MaaUtils.dll", "onnxruntime_maa.dll", "opencv_world4_maa.dll"]
    missing = [n for n in required if not (bin_dir / n).exists()]
    if missing:
        print(f"!! 缺少关键 DLL: {missing}")
        return False
    return True


def install(bin_dir: Path):
    """替换 deps/bin-go 内容。"""
    print(f"[3/4] 替换 {BIN_GO} ...")
    if BIN_GO.exists():
        shutil.rmtree(BIN_GO)
    shutil.copytree(bin_dir, BIN_GO)
    print(f"[4/4] 完成: {BIN_GO}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", nargs="?", help="MaaFramework 版本,缺省用 Go 绑定要求的版本")
    ap.add_argument("--check", action="store_true", help="仅检查对齐情况")
    args = ap.parse_args()

    go_ver = go_binding_version()
    print(f"Go 绑定要求 MaaFramework: {go_ver or '(未知)'}")
    print(f"当前 deps/bin-go: {current_version()} (DLL 无版本资源,以安装记录为准)")

    if not args.version:
        if not go_ver:
            sys.exit("无法确定版本:请显式指定,如 python tools/update_bin_go.py 5.10.4")
        args.version = go_ver

    if args.check:
        print("检查完成(需人工核对 DLL 来源版本与 Go 绑定要求一致)")
        return

    if not args.version:
        sys.exit("缺少版本号")

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        wheel = download_maafw(args.version, workdir)
        bin_dir = extract_dlls(wheel, workdir)
        if not verify_dlls(bin_dir):
            sys.exit("DLL 校验失败,已中止(未改动 deps/bin-go)")
        install(bin_dir)

    print("\n更新完成。接下来:")
    print("  1) cd agent-go && go build -o agent-go.exe .   # 重新编译")
    print("  2) 运行 agent-go.exe 冒烟测试,确认 MAA init 与 AgentServer 启动正常")
    print("  3) 若报 'procedure could not be found' = DLL 与 Go 绑定版本不匹配")


if __name__ == "__main__":
    main()
