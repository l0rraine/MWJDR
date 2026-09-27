from pathlib import Path

import shutil
import sys
import json

import os
import sys


script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from configure import configure_ocr_model

working_dir = Path(__file__).parent.parent.parent
install_path = working_dir / Path("install")
version = len(sys.argv) > 1 and sys.argv[1] or "v0.0.1"


def install_deps():
    shutil.copytree(
        working_dir / "deps" / "bin-go",
        install_path / "deps" / "bin-go",
        ignore=shutil.ignore_patterns(
            "*MaaDbgControlUnit*",
            "*MaaThriftControlUnit*",
            "*MaaWin32ControlUnit*",
            "*MaaRpc*",
            "*MaaHttp*",
        ),
        dirs_exist_ok=True,
    )
    shutil.copytree(
        working_dir / "deps" / "share" / "MaaAgentBinary",
        install_path / "MaaAgentBinary",
        dirs_exist_ok=True,
    )


def install_resource():

    configure_ocr_model()

    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        working_dir / "assets" / "interface.json",
        install_path,
    )

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = json.load(f)

    interface["version"] = version
    interface["custom_title"] = f"MWJDR {version} | 无尽冬日小助手"

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        json.dump(interface, f, ensure_ascii=False, indent=4)


def install_chores():
    for file in ["README.md", "LICENSE"]:
        shutil.copy2(
            working_dir / file,
            install_path,
        )
    shutil.copytree(
        working_dir / "docs",
        install_path / "docs",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.yaml"),
    )


def install_agent():
    agent_dir = install_path / "agent-go"
    agent_dir.mkdir(parents=True, exist_ok=True)
    exe_name = "agent-go.exe" if sys.platform.startswith("win") else "agent-go"
    shutil.copy2(working_dir / "agent-go" / exe_name, agent_dir)

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = json.load(f)

    interface["agent"]["child_exec"] = "{PROJECT_DIR}/agent-go/" + exe_name
    interface["agent"]["child_args"] = []

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        json.dump(interface, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    install_deps()
    install_resource()
    install_chores()
    install_agent()

    print(f"Install to {install_path} successfully.")
