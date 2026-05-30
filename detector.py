import re
from typing import List, Optional, Tuple
from astrbot.api.provider import Provider
from astrbot.api.config import AstrBotConfig
from astrbot.api.message import Message


class DetectionResult:
    def __init__(self, is_ad: bool, reason: str = "", detection_type: str = ""):
        self.is_ad = is_ad
        self.reason = reason
        self.detection_type = detection_type


class AdDetector:
    def __init__(self, config: AstrBotConfig, llm_provider: Optional[Provider] = None):
        self.config = config
        self.llm_provider = llm_provider
        self.regex_rules = config.get("regex_rules", [])

    async def detect_message(self, message: Message) -> DetectionResult:
        text_result = await self._detect_text_content(message)
        if text_result.is_ad:
            return text_result

        if self.config.get("enable_quote_detection", False):
            quote_result = await self._detect_quote(message)
            if quote_result.is_ad:
                return quote_result

        if self.config.get("enable_image_ai_detection", False):
            image_result = await self._detect_images(message)
            if image_result.is_ad:
                return image_result

        return DetectionResult(False)

    async def _detect_text_content(self, message: Message) -> DetectionResult:
        if not message.content:
            return DetectionResult(False)

        if self.config.get("enable_regex_detection", True):
            regex_result = self._regex_detect(message.content)
            if regex_result.is_ad:
                return regex_result

        if self.config.get("enable_text_ai_detection", False):
            ai_result = await self._text_ai_detect(message.content)
            if ai_result.is_ad:
                return ai_result

        return DetectionResult(False)

    def _regex_detect(self, text: str) -> DetectionResult:
        for rule in self.regex_rules:
            try:
                if re.search(rule, text, re.IGNORECASE):
                    return DetectionResult(
                        True, 
                        reason=f"匹配到违规关键词规则: {rule}", 
                        detection_type="regex"
                    )
            except re.error as e:
                continue
        return DetectionResult(False)

    async def _text_ai_detect(self, text: str) -> DetectionResult:
        if not self.llm_provider:
            return DetectionResult(False)

        try:
            prompt = (
                "请判断以下内容是否为广告或违规推广信息。"
                "如果是广告，请回复'是广告'并在新行说明原因；"
                "如果不是，请仅回复'不是广告'。\n\n"
                f"内容：{text}"
            )

            response = await self.llm_provider.text_chat(prompt)
            response_text = response.get("text", "").strip()

            if "是广告" in response_text:
                reason = response_text.split("是广告")[-1].strip()
                return DetectionResult(
                    True, 
                    reason=reason if reason else "AI检测为广告内容", 
                    detection_type="text_ai"
                )
        except Exception as e:
            pass

        return DetectionResult(False)

    async def _detect_images(self, message: Message) -> DetectionResult:
        return DetectionResult(False)

    async def _detect_quote(self, message: Message) -> DetectionResult:
        if not message.quote:
            return DetectionResult(False)
        
        return await self._detect_text_content(message.quote)
