import os
from astrbot.api.star import Star
from astrbot.api.event import AstrMessageEvent, filter as event_filter
from .database import DatabaseManager
from .detector import AdDetector
from .handler import ViolationHandler
from .commands import CommandManager


class AdDetection(Star):
    def __init__(self, context):
        super().__init__(context)
        self.plugin_name = "astrbot_plugin_ad_detection"
        self.db = None
        self.detector = None
        self.handler = None
        self.cmd_manager = None
        
    async def initialize(self):
        config = self.context.get_config()
        data_dir = self.context.get_data_dir()
        db_path = os.path.join(data_dir, "ad_detection.db")
        
        self.db = DatabaseManager(db_path)
        
        llm_provider = None
        try:
            provider_name = config.get("ai_provider")
            if provider_name:
                llm_provider = self.context.get_provider(provider_name)
        except Exception:
            pass
        
        self.detector = AdDetector(config, llm_provider)
        self.handler = ViolationHandler(config, self.db, self.context)
        self.cmd_manager = CommandManager(config, self.db, self.context)
        
        for cmd in self.cmd_manager.get_commands():
            self.register_command(cmd)

    @event_filter.event_message_type(event_filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        try:
            user_id = str(event.get_sender_id())
            group_id = str(event.group_id) if event.group_id else ""
            
            if not group_id or not user_id:
                return
            
            detection_result = await self.detector.detect_message(event)
            if detection_result.is_ad:
                await self.handler.handle_violation(
                    event,
                    detection_result,
                    user_id,
                    group_id
                )
        except Exception:
            pass
