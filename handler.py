from typing import Optional
from astrbot.api.message import Message
from astrbot.api.config import AstrBotConfig
from .database import DatabaseManager
from .detector import DetectionResult


class ViolationHandler:
    def __init__(self, config: AstrBotConfig, db: DatabaseManager):
        self.config = config
        self.db = db

    async def handle_violation(
        self,
        message: Message,
        detection_result: DetectionResult,
        user_id: str,
        group_id: str
    ):
        if self.db.is_group_whitelisted(group_id):
            return
        
        if self.db.is_user_whitelisted(user_id, group_id):
            return

        violation_record = self.db.add_violation(user_id, group_id)

        if self.config.get("enable_withdraw", True):
            await self._withdraw_message(message)

        if self.config.get("enable_warn", True):
            await self._send_warning(
                message,
                violation_record.violation_count,
                detection_result
            )

        if self.config.get("enable_kick", False):
            warn_threshold = self.config.get("warn_threshold", 3)
            if violation_record.violation_count >= warn_threshold:
                await self._kick_user(message, user_id, group_id)

    async def _withdraw_message(self, message: Message):
        try:
            if hasattr(message, "withdraw"):
                await message.withdraw()
        except Exception as e:
            pass

    async def _send_warning(
        self,
        message: Message,
        violation_count: int,
        detection_result: DetectionResult
    ):
        try:
            base_warn_msg = self.config.get("warn_message", "检测到您发送了广告内容，请遵守群规！")
            full_message = (
                f"{base_warn_msg}\n"
                f"违规原因：{detection_result.reason}\n"
                f"当前违规次数：{violation_count}"
            )
            await message.reply(full_message)
        except Exception as e:
            pass

    async def _kick_user(self, message: Message, user_id: str, group_id: str):
        try:
            if hasattr(message, "kick_member"):
                await message.kick_member(user_id)
        except Exception as e:
            pass
