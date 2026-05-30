import os
from typing import Any
from astrbot.api.star import Star
from astrbot.api.config import AstrBotConfig
from astrbot.api.message import Message
from astrbot.api.provider import Provider
from .database import DatabaseManager
from .detector import AdDetector
from .handler import ViolationHandler
from .commands import CommandManager

class AdDetection(Star):
    def __init__(self):
        super().__init__()
        self.plugin_name = "astrbot-plugin-ad-detection"
        self.db: DatabaseManager = None
        self.config: AstrBotConfig = None
        self.detector: AdDetector = None
        self.handler: ViolationHandler = None
        self.cmd_manager: CommandManager = None
        
    async def on_load(self):
        self.config = self.get_config()
        data_dir = self.get_data_dir()
        db_path = os.path.join(data_dir, "ad_detection.db")
        self.db = DatabaseManager(db_path)
        
        llm_provider = None
        try:
            text_provider_name = self.config.get("text_ai_provider")
            if text_provider_name:
                llm_provider = self.get_provider(text_provider_name)
        except Exception:
            pass
        
        self.detector = AdDetector(self.config, llm_provider)
        self.handler = ViolationHandler(self.config, self.db)
        self.cmd_manager = CommandManager(self.config, self.db)
        
        for cmd in self.cmd_manager.get_commands():
            self.register_command(cmd)
        
    async def on_unload(self):
        pass
        
    async def on_message(self, message: Message):
        try:
            if not message.group_id or not message.sender:
                return
            
            user_id = str(message.sender.user_id)
            group_id = str(message.group_id)
            
            detection_result = await self.detector.detect_message(message)
            if detection_result.is_ad:
                await self.handler.handle_violation(
                    message,
                    detection_result,
                    user_id,
                    group_id
                )
        except Exception as e:
            pass
