"""
角色ID识别

通过 OCR 识别游戏界面上的角色ID（9位数字），用于数据分桶存储。
复刻自 m9a 项目的 RecordID 模式，使用一致性校验保证准确性。
"""

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from utils import logger
from utils.ocr_util import ocr_until_consistent


@AgentServer.custom_action("开始是否识别角色ID")
class StartRecordIDOrNot(CustomAction):
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        from utils.mfa_config import has_battle_tasks

        battle_status = has_battle_tasks()
        if battle_status is True:
            logger.debug("后续有战斗任务，跳过识别角色ID")
            context.override_pipeline({"识别角色ID_开始": {"enabled": False}})
            context.tasker.resource.override_pipeline(
                {"识别角色ID_开始": {"enabled": False}}
            )
            context.tasker.resource.override_pipeline(
                {"查看队列_记录角色ID": {"enabled": True}}
            )

        return CustomAction.RunResult(success=True)

@AgentServer.custom_action("识别角色ID")
class RecordID(CustomAction):
    # 类变量：存储当前角色的 ID，供其他 Custom Action 读取
    _account_id: str = ""

    # 角色 ID 的 OCR 区域（9位数字）
    _id_roi: list = [347, 946, 138, 34]

    # 角色 ID 格式：9位纯数字
    _id_pattern: str = r"^\d{9}$"

    @classmethod
    def current_account_id(cls) -> str:
        """获取当前角色 ID"""
        return cls._account_id.strip()

    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> CustomAction.RunResult:
        account_id = ocr_until_consistent(
            context,
            roi=self._id_roi,
            expected_pattern=self._id_pattern,
        )

        if account_id:
            RecordID._account_id = account_id
            logger.info(f"识别到角色ID：{account_id}")
        else:
            logger.warning("未能识别到角色ID，将使用默认存储")
            RecordID._account_id = ""

        return CustomAction.RunResult(success=True)
