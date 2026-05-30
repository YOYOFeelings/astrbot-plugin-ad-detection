from typing import Optional, Dict, Any
from astrbot.api.event import AstrMessageEvent
from .database import DatabaseManager
from .detector import DetectionResult


class ViolationHandler:
    def __init__(self, config: Dict[str, Any], db: DatabaseManager, context):
        self.config = config
        self.db = db
        self.context = context

    async def handle_violation(
        self,
        event: AstrMessageEvent,
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
            await self._withdraw_message(event)

        if self.config.get("enable_warn", True):
            await self._send_warning(
                event,
                violation_record.violation_count,
                detection_result
            )

        if self.config.get("enable_kick", False):
            warn_threshold = self.config.get("warn_threshold", 3)
            if violation_record.violation_count >= warn_threshold:
                await self._kick_user(event, user_id, group_id)

    async def _withdraw_message(self, event: AstrMessageEvent):
        try:
            await event.recall()
        except Exception:
            pass

    async def _send_warning(
        self,
        event: AstrMessageEvent,
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
            await event.send(full_message)
        except Exception:
            pass

    async def _kick_user(self, event: AstrMessageEvent, user_id: str, group_id: str):
        try:
            await self.context.kick_group_member(group_id, user_id)
        except Exception:
            pass
