import re
import base64
from typing import List, Optional
from astrbot.api.provider import Provider
from astrbot.api.config import AstrBotConfig
from astrbot.api.event import AstrMessageEvent


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

    async def detect_message(self, event: AstrMessageEvent) -> DetectionResult:
        text_result = await self._detect_text_content(event)
        if text_result.is_ad:
            return text_result

        if self.config.get("enable_quote_detection", False):
            quote_result = await self._detect_quote(event)
            if quote_result.is_ad:
                return quote_result

        if self.config.get("enable_image_detection", True):
            image_result = await self._detect_images(event)
            if image_result.is_ad:
                return image_result

        return DetectionResult(False)

    async def _detect_text_content(self, event: AstrMessageEvent) -> DetectionResult:
        message_str = event.message_str
        if not message_str:
            return DetectionResult(False)

        if self.config.get("enable_regex_detection", True):
            regex_result = self._regex_detect(message_str)
            if regex_result.is_ad:
                return regex_result

        if self.config.get("enable_text_ai_detection", False):
            ai_result = await self._text_ai_detect(message_str)
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
            except re.error:
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
        except Exception:
            pass

        return DetectionResult(False)

    async def _detect_images(self, event: AstrMessageEvent) -> DetectionResult:
        if not self.config.get("enable_image_detection", True):
            return DetectionResult(False)

        if not self.config.get("enable_text_ai_detection", False) or not self.llm_provider:
            return DetectionResult(False)

        try:
            message_obj = event.message_obj
            if not hasattr(message_obj, 'message'):
                return DetectionResult(False)

            for component in message_obj.message:
                if component.type == 'image':
                    try:
                        image_url = getattr(component, 'url', None) or getattr(component, 'file', None)
                        if image_url:
                            image_b64 = await self._download_and_encode_image(image_url)
                            if image_b64:
                                prompt = (
                                    "请判断这张图片中是否包含广告或违规推广信息。"
                                    "如果是广告，请回复'是广告'并在新行说明原因；"
                                    "如果不是，请仅回复'不是广告'。"
                                )

                                response = await self.llm_provider.text_chat(prompt, image_base64=image_b64)
                                response_text = response.get("text", "").strip()

                                if "是广告" in response_text:
                                    reason = response_text.split("是广告")[-1].strip()
                                    return DetectionResult(
                                        True,
                                        reason=f"图片AI检测：{reason if reason else '包含广告内容'}",
                                        detection_type="image_ai"
                                    )
                    except Exception:
                        continue
        except Exception:
            pass

        return DetectionResult(False)

    async def _download_and_encode_image(self, url: str) -> Optional[str]:
        try:
            import httpx
            resp = httpx.get(url, timeout=10)
            resp.raise_for_status()
            import base64
            return base64.b64encode(resp.content).decode('utf-8')
        except Exception:
            return None

    async def _detect_quote(self, event: AstrMessageEvent) -> DetectionResult:
        try:
            message_obj = event.message_obj
            if not hasattr(message_obj, 'message'):
                return DetectionResult(False)

            for component in message_obj.message:
                if component.type == 'reply':
                    quoted_text = getattr(component, 'content', None)
                    if quoted_text:
                        return await self._detect_text_content_by_text(quoted_text)
        except Exception:
            pass
        return DetectionResult(False)

    async def _detect_text_content_by_text(self, text: str) -> DetectionResult:
        if not text:
            return DetectionResult(False)

        if self.config.get("enable_regex_detection", True):
            regex_result = self._regex_detect(text)
            if regex_result.is_ad:
                return regex_result

        if self.config.get("enable_text_ai_detection", False):
            ai_result = await self._text_ai_detect(text)
            if ai_result.is_ad:
                return ai_result

        return DetectionResult(False)
