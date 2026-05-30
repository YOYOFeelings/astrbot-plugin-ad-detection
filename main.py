from typing import Any
from astrbot.api.star import Star

class AdDetection(Star):
    def __init__(self):
        super().__init__()
        self.plugin_name = "astrbot-plugin-ad-detection"
        
    async def on_load(self):
        pass
    
    async def on_unload(self):
        pass
