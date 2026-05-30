import os
import re
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy import create_engine, Table, Column, String, Integer, DateTime, MetaData
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from astrbot.api.star import Star, StarTools
from astrbot.api.event import AstrMessageEvent, filter as event_filter
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
        self.user_whitelist_table = Table(
            'user_whitelist', self.metadata,
            Column('user_id', String, primary_key=True),
            Column('group_id', String, primary_key=True)
        )
        self.group_whitelist_table = Table(
            'group_whitelist', self.metadata,
            Column('group_id', String, primary_key=True)
        )
        self.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_violation(self, user_id: str, group_id: str) -> ViolationRecord:
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

    def get_violation(self, user_id: str, group_id: str) -> Optional[ViolationRecord]:
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

    def reset_violation(self, user_id: str, group_id: str) -> bool:
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

    def is_user_whitelisted(self, user_id: str, group_id: str) -> bool:
        session = self.Session()
        try:
            result = session.query(self.user_whitelist_table).filter_by(
                user_id=user_id, group_id=group_id
            ).first()
            return result is not None
        finally:
            session.close()

    def is_group_whitelisted(self, group_id: str) -> bool:
        session = self.Session()
        try:
            result = session.query(self.group_whitelist_table).filter_by(group_id=group_id).first()
            return result is not None
        finally:
            session.close()

    def add_user_to_whitelist(self, user_id: str, group_id: str) -> bool:
        session = self.Session()
        try:
            if self.is_user_whitelisted(user_id, group_id):
                return False
            session.execute(self.user_whitelist_table.insert().values(user_id=user_id, group_id=group_id))
            session.commit()
            return True
        finally:
            session.close()

    def remove_user_from_whitelist(self, user_id: str, group_id: str) -> bool:
        session = self.Session()
        try:
            result = session.execute(
                self.user_whitelist_table.delete()
                .where(self.user_whitelist_table.c.user_id == user_id, self.user_whitelist_table.c.group_id == group_id)
            )
            session.commit()
            return result.rowcount > 0
        finally:
            session.close()

    def add_group_to_whitelist(self, group_id: str) -> bool:
        session = self.Session()
        try:
            if self.is_group_whitelisted(group_id):
                return False
            session.execute(self.group_whitelist_table.insert().values(group_id=group_id))
            session.commit()
            return True
        finally:
            session.close()

    def remove_group_from_whitelist(self, group_id: str) -> bool:
        session = self.Session()
        try:
            result = session.execute(
                self.group_whitelist_table.delete()
                .where(self.group_whitelist_table.c.group_id == group_id)
            )
            session.commit()
            return result.rowcount > 0
        finally:
            session.close()


class AdDetection(Star):
    def __init__(self, context, config: Dict[str, Any]):
        super().__init__(context)
        self.plugin_name = "astrbot_plugin_ad_detection"
        self.db = None
        self.config = config

    async def initialize(self):
        data_dir = StarTools.get_data_dir(self.plugin_name)
        db_path = data_dir / "ad_detection.db"
        self.db = DatabaseManager(str(db_path))

    def is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            sender = event.sender
            role = getattr(sender, 'role', None)
            return role in ["admin", "owner"]
        except Exception:
            return False

    async def _detect_ad(self, event: AstrMessageEvent) -> tuple:
        regex_rules = self.config.get("regex_rules", [])
        message_str = event.message_str or ""

        if self.config.get("enable_regex_detection", True):
            for rule in regex_rules:
                try:
                    if re.search(rule, message_str, re.IGNORECASE):
                        return True, f"匹配到违规关键词: {rule}", "regex"
                except re.error:
                    continue

        if self.config.get("enable_quote_detection", False):
            try:
                for component in event.message_obj.message:
                    if component.type == 'reply':
                        quoted_text = getattr(component, 'content', None)
                        if quoted_text:
                            for rule in regex_rules:
                                try:
                                    if re.search(rule, quoted_text, re.IGNORECASE):
                                        return True, f"引用消息匹配到违规关键词: {rule}", "regex"
                                except re.error:
                                    continue
            except Exception:
                pass

        return False, "", ""

    async def _handle_violation(self, event: AstrMessageEvent, reason: str, detection_type: str):
        user_id = str(event.get_sender_id())
        group_id = str(event.group_id) if event.group_id else ""

        if self.db.is_group_whitelisted(group_id) or self.db.is_user_whitelisted(user_id, group_id):
            return

        violation = self.db.add_violation(user_id, group_id)

        if self.config.get("enable_withdraw", True):
            try:
                await event.recall()
            except Exception:
                pass

        if self.config.get("enable_warn", True):
            warn_msg = self.config.get("warn_message", "检测到您发送了广告内容，请遵守群规！")
            full_msg = f"{warn_msg}\n违规原因：{reason}\n当前违规次数：{violation.violation_count}"
            try:
                await event.send(full_msg)
            except Exception:
                pass

        if self.config.get("enable_kick", False):
            threshold = self.config.get("warn_threshold", 3)
            if violation.violation_count >= threshold:
                try:
                    await self.context.kick_group_member(group_id, user_id)
                except Exception:
                    pass

    @event_filter.event_message_type(event_filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        try:
            is_ad, reason, detection_type = await self._detect_ad(event)
            if is_ad:
                await self._handle_violation(event, reason, detection_type)
        except Exception:
            pass

    @event_filter.command("ad_violation")
    async def cmd_violation(self, event: AstrMessageEvent, user_id: str = ""):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return
        if not user_id:
            await event.send("请指定要查询的用户ID：/ad_violation <用户ID>")
            return
        group_id = str(event.group_id) if event.group_id else ""
        record = self.db.get_violation(user_id, group_id)
        if record:
            await event.send(f"用户 {user_id} 的违规记录：\n违规次数：{record.violation_count}\n最近违规时间：{record.last_violation_time}")
        else:
            await event.send(f"未找到用户 {user_id} 的违规记录")

    @event_filter.command("ad_reset")
    async def cmd_reset(self, event: AstrMessageEvent, user_id: str = ""):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return
        if not user_id:
            await event.send("请指定要重置的用户ID：/ad_reset <用户ID>")
            return
        group_id = str(event.group_id) if event.group_id else ""
        success = self.db.reset_violation(user_id, group_id)
        await event.send(f"{'已重置' if success else '未找到'}用户 {user_id} 的违规记录")

    @event_filter.command("ad_whitelist")
    async def cmd_whitelist(self, event: AstrMessageEvent, action: str = "", user_id: str = ""):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return
        if not action or action not in ["add", "remove"]:
            await event.send("用法：\n/ad_whitelist add <用户ID> - 添加白名单\n/ad_whitelist remove <用户ID> - 移除白名单")
            return
        if not user_id:
            await event.send("请指定用户ID")
            return
        group_id = str(event.group_id) if event.group_id else ""
        if action == "add":
            success = self.db.add_user_to_whitelist(user_id, group_id)
            await event.send(f"{'已添加' if success else '用户已在'}白名单")
        else:
            success = self.db.remove_user_from_whitelist(user_id, group_id)
            await event.send(f"{'已移除' if success else '用户不在'}白名单")

    @event_filter.command("ad_gwhitelist")
    async def cmd_group_whitelist(self, event: AstrMessageEvent, action: str = ""):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return
        if not action or action not in ["add", "remove"]:
            await event.send("用法：\n/ad_gwhitelist add - 添加本群白名单\n/ad_gwhitelist remove - 移除本群白名单")
            return
        group_id = str(event.group_id) if event.group_id else ""
        if action == "add":
            success = self.db.add_group_to_whitelist(group_id)
            await event.send(f"{'已添加' if success else '本群已在'}白名单")
        else:
            success = self.db.remove_group_from_whitelist(group_id)
            await event.send(f"{'已移除' if success else '本群不在'}白名单")

    @event_filter.command("ad_help")
    async def cmd_help(self, event: AstrMessageEvent):
        help_text = """广告检测插件命令：
/ad_violation <用户ID> - 查看用户违规记录
/ad_reset <用户ID> - 重置用户违规记录
/ad_whitelist add <用户ID> - 添加用户白名单
/ad_whitelist remove <用户ID> - 移除用户白名单
/ad_gwhitelist add/remove - 管理群组白名单
/ad_help - 显示此帮助"""
        await event.send(help_text)
