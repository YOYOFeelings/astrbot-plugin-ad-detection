import os
import re
import json
import base64
from pathlib import Path
from typing import Optional, List
from sqlalchemy import create_engine, Table, Column, String, Integer, DateTime, MetaData
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from astrbot.api import AstrBotConfig
from astrbot.api.star import Star, StarTools, Context
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import PermissionType
from astrbot.api import logger


class ViolationRecord:
    def __init__(self, user_id: str, group_id: str, violation_count: int = 0, last_violation_time: str = ""):
        self.user_id = user_id
        self.group_id = group_id
        self.violation_count = violation_count
        self.last_violation_time = last_violation_time


class DatabaseManager:
    def __init__(self, db_path: str):
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.metadata = MetaData()
        self.violations_table = Table(
            'violations', self.metadata,
            Column('user_id', String, primary_key=True),
            Column('group_id', String, primary_key=True),
            Column('violation_count', Integer, default=0),
            Column('last_violation_time', String)
        )
        self.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_violation(self, user_id: str, group_id: str):
        session = self.Session()
        try:
            result = session.query(self.violations_table).filter_by(
                user_id=user_id, group_id=group_id
            ).first()
            if result:
                new_count = result.violation_count + 1
                session.execute(
                    self.violations_table.update()
                    .where(self.violations_table.c.user_id == user_id, self.violations_table.c.group_id == group_id)
                    .values(violation_count=new_count, last_violation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
            else:
                session.execute(
                    self.violations_table.insert().values(
                        user_id=user_id, group_id=group_id,
                        violation_count=1, last_violation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                )
                new_count = 1
            session.commit()
            return ViolationRecord(user_id, group_id, new_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        finally:
            session.close()

    def get_violation(self, user_id: str, group_id: str):
        session = self.Session()
        try:
            result = session.query(self.violations_table).filter_by(
                user_id=user_id, group_id=group_id
            ).first()
            if result:
                return ViolationRecord(result.user_id, result.group_id, result.violation_count, result.last_violation_time)
            return None
        finally:
            session.close()

    def reset_violation(self, user_id: str, group_id: str):
        session = self.Session()
        try:
            result = session.execute(
                self.violations_table.delete()
                .where(self.violations_table.c.user_id == user_id, self.violations_table.c.group_id == group_id)
            )
            session.commit()
            return result.rowcount > 0
        finally:
            session.close()


class AdDetection(Star):
    """广告检测插件主类"""
    config: AstrBotConfig
    db: DatabaseManager
    plugin_name = "astrbot_plugin_ad_detection"

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        logger.info(f"[广告检测] 配置已加载: {config}")

    async def initialize(self):
        try:
            plugin_data_dir = StarTools.get_data_dir(self.plugin_name)
        except Exception:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            plugin_data_dir = (
                Path(get_astrbot_data_path())
                / "plugin_data"
                / self.plugin_name
            )

        db_path = plugin_data_dir / "ad_detection.db"
        self.db = DatabaseManager(str(db_path))
        logger.info("广告检测插件初始化完成")

    def _get_config(self, key: str, default=None):
        """安全获取配置值"""
        try:
            value = self.config.get(key)
            logger.info(f"[广告检测] 读取配置 {key}: {value}")
            return value if value is not None else default
        except Exception as e:
            logger.warning(f"[广告检测] 读取配置 {key} 失败: {e}")
            return default

    def _is_admin_by_qq(self, user_id: str) -> bool:
        """通过配置的QQ号判断是否为管理员"""
        admin_qqs = self._get_config("admin_qqs", [])
        if not admin_qqs:
            logger.warning("[广告检测] 未配置管理员QQ号")
            return False
        return str(user_id) in [str(qq) for qq in admin_qqs]

    def _check_group_permission(self, group_id: str) -> bool:
        """检查群是否有权限使用此插件"""
        mode = self._get_config("group_list_mode", "none")
        group_list = self._get_config("group_list", [])

        if mode == "none":
            return True

        match_found = False
        for allowed_group in group_list:
            if group_id == allowed_group or str(group_id) in str(allowed_group):
                match_found = True
                break

        if mode == "whitelist":
            return match_found
        elif mode == "blacklist":
            return not match_found
        return True

    async def _call_ai_detect(self, message: str, images: List[str] = None) -> tuple[bool, str]:
        """调用AI检测广告内容"""
        try:
            provider_name = self._get_config("ai_provider", "")
            if not provider_name:
                return False, ""

            provider = self.context.get_provider(provider_name)
            if not provider:
                return False, ""

            prompt = """请判断以下消息是否包含广告内容。广告内容包括但不限于：
1. 邀请加群、推广群聊
2. 推销产品、服务、商业信息
3. 诱导点击链接、二维码
4. 虚假信息、诈骗内容

消息内容：{message}

请只回答"是广告"或"不是广告"，不要添加任何解释。""".format(message=message)

            messages = [{"role": "user", "content": prompt}]

            if images:
                for img_data in images:
                    if img_data.startswith("base64://"):
                        img_base64 = img_data.replace("base64://", "")
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                            ]
                        })

            result = await provider.chat(messages=messages)

            if "是广告" in result:
                return True, "AI检测判定为广告"
            return False, ""

        except Exception as e:
            logger.warning(f"AI检测失败: {e}")
            return False, ""

    async def _detect_ad(self, event: AstrMessageEvent) -> tuple[bool, str, str]:
        """检测消息是否为广告"""
        regex_rules = self._get_config("regex_rules", [])
        message_str = event.message_str or ""
        group_id = event.get_group_id() or ""
        user_id = str(event.get_sender_id()) if event.get_sender_id() else ""

        logger.info(f"[广告检测] 收到消息: {message_str}, 发送者: {user_id}, 群: {group_id}")
        logger.info(f"[广告检测] 正则规则: {regex_rules}")

        # 管理员白名单跳过检测
        admin_qqs = self._get_config("admin_qqs", [])
        if str(user_id) in [str(qq) for qq in admin_qqs]:
            logger.info(f"[广告检测] 用户是管理员，跳过检测")
            return False, "", ""

        # 群组白名单跳过检测
        whitelist = self._get_config("group_whitelist", [])
        if whitelist and (group_id in whitelist or str(group_id) in [str(g) for g in whitelist]):
            logger.info(f"[广告检测] 群在白名单中，跳过检测")
            return False, "", ""

        # 正则检测
        if self._get_config("enable_regex_detection", True):
            logger.info(f"[广告检测] 开始正则检测，规则数: {len(regex_rules)}")
            for rule in regex_rules:
                try:
                    if re.search(rule, message_str, re.IGNORECASE):
                        logger.info(f"[广告检测] 匹配成功！规则: {rule}")
                        return True, f"匹配到违规关键词: {rule}", "regex"
                except re.error:
                    continue

        # 引用消息检测
        if self._get_config("enable_quote_detection", False):
            try:
                for component in event.message_obj.message:
                    if component.type == 'reply':
                        quoted_text = getattr(component, 'content', None)
                        if quoted_text:
                            for rule in regex_rules:
                                try:
                                    if re.search(rule, str(quoted_text), re.IGNORECASE):
                                        return True, f"引用消息匹配到违规关键词: {rule}", "regex"
                                except re.error:
                                    continue
            except Exception:
                pass

        # AI检测
        if self._get_config("enable_ai_detection", False):
            is_ad, reason = await self._call_ai_detect(message_str)
            if is_ad:
                return True, reason, "ai"

        logger.info(f"[广告检测] 未检测到广告")
        return False, "", ""

    async def _handle_violation(self, event: AstrMessageEvent, reason: str, detection_type: str):
        """处理违规消息"""
        user_id = str(event.get_sender_id()) if event.get_sender_id() else ""
        group_id = event.get_group_id() or ""

        if not group_id or not user_id:
            return

        logger.info(f"[广告检测] 处理违规: 用户={user_id}, 原因={reason}")

        violation = self.db.add_violation(user_id, group_id)

        # 撤回消息
        if self._get_config("enable_withdraw", True):
            try:
                await event.recall()
                logger.info(f"[广告检测] 消息已撤回")
            except Exception as e:
                logger.warning(f"[广告检测] 撤回失败: {e}")

        # 发送警告
        if self._get_config("enable_warn", True):
            warn_msg = self._get_config("warn_message", "检测到您发送了广告内容，请遵守群规！")
            full_msg = f"{warn_msg}\n违规原因：{reason}\n当前违规次数：{violation.violation_count}"
            try:
                await event.send(full_msg)
                logger.info(f"[广告检测] 警告已发送")
            except Exception as e:
                logger.warning(f"[广告检测] 发送警告失败: {e}")

        # 踢出群
        if self._get_config("enable_kick", False):
            threshold = self._get_config("warn_threshold", 3)
            if violation.violation_count >= threshold:
                try:
                    await self.context.kick_group_member(group_id, user_id)
                    logger.info(f"[广告检测] 用户已被踢出")
                except Exception as e:
                    logger.warning(f"[广告检测] 踢出失败: {e}")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """处理群消息"""
        try:
            group_id = event.get_group_id() or ""
            if not group_id:
                return

            if not self._check_group_permission(group_id):
                return

            is_ad, reason, detection_type = await self._detect_ad(event)
            if is_ad:
                await self._handle_violation(event, reason, detection_type)
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)

    @filter.command("广告违规", alias={"ad_violation"})
    async def cmd_violation(self, event: AstrMessageEvent, user_id: str = ""):
        """查看用户违规记录 [用户ID]"""
        sender_id = str(event.get_sender_id()) if event.get_sender_id() else ""
        if not self._is_admin_by_qq(sender_id):
            await event.send("您没有权限执行此命令")
            return

        if not user_id:
            await event.send("请指定要查询的用户ID：/广告违规 [用户ID]")
            return
        group_id = event.get_group_id() or ""
        record = self.db.get_violation(user_id, group_id)
        if record:
            msg = f"用户 {user_id} 的违规记录：\n违规次数：{record.violation_count}\n最近违规时间：{record.last_violation_time}"
            await event.send(msg)
        else:
            await event.send(f"未找到用户 {user_id} 的违规记录")

    @filter.command("重置违规", alias={"ad_reset"})
    async def cmd_reset(self, event: AstrMessageEvent, user_id: str = ""):
        """重置用户违规记录 [用户ID]"""
        sender_id = str(event.get_sender_id()) if event.get_sender_id() else ""
        if not self._is_admin_by_qq(sender_id):
            await event.send("您没有权限执行此命令")
            return

        if not user_id:
            await event.send("请指定要重置的用户ID：/重置违规 [用户ID]")
            return
        group_id = event.get_group_id() or ""
        success = self.db.reset_violation(user_id, group_id)
        msg = f"{'已重置' if success else '未找到'}用户 {user_id} 的违规记录"
        await event.send(msg)

    @filter.command("广告帮助", alias={"ad_help"})
    async def cmd_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """广告检测插件命令：
/广告违规 [用户ID] - 查看用户违规记录（管理员）
/重置违规 [用户ID] - 重置用户违规记录（管理员）
/广告帮助 - 显示此帮助"""
        await event.send(help_text)
