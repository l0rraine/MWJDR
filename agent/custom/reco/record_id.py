"""
角色ID识别

通过 OCR 识别游戏界面上的角色信息，用于数据分桶存储。
复刻自 m9a 项目的 RecordID 模式，用户可自行完善识别逻辑。
"""

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from maa.pipeline import JRecognitionType, JOCR

from utils import logger


@AgentServer.custom_action("识别角色ID")
class RecordID(CustomAction):
    # 类变量：存储当前角色的 ID，供其他 Custom Action 读取
    _account_id: str = ""

    # TODO: 根据实际游戏界面设置 OCR 区域
    _id_roi: tuple[int, int, int, int] = (0, 0, 100, 100)

    @classmethod
    def current_account_id(cls) -> str:
        """获取当前角色 ID"""
        return cls._account_id.strip()

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        img = context.tasker.controller.post_screencap().wait().get()

        # TODO: 根据 actual game UI 修改 ROI 和识别逻辑
        detail = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(roi=list(self._id_roi), only_rec=True),
            img,
        )

        if detail and detail.hit:
            account_id = detail.best_result.text.strip()
            RecordID._account_id = account_id
            logger.info(f"识别到角色ID：{account_id}")
        else:
            logger.warning("未识别到角色ID，将使用默认存储")
            RecordID._account_id = ""

        return CustomAction.RunResult(success=True)
