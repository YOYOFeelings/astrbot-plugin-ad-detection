
import os
import re
from pathlib import Path
from typing import Optional
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

    def add_violation(self, user_id: str, group_id: str) -&gt; ViolationRecord:
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

    def get_violation(self, user_id: str, group_id: str) -&gt; Optional[ViolationRecord]:
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

    def reset_violation(self, user_id: str, group_id: str) -&gt; bool:
        session = self.Session()
        try:
            result = session.execute(
                self.violations_table.delete()
                .where(self.violations_table.c.user_id == user_id, self.violations_table.c.group_id == group_id)
            )
            session.commit()
            return result.rowcount &gt; 0
        finally:
            session.close()

    def is_user_whitelisted(self, user_id: str, group_id: str) -&gt; bool:
        session = self.Session()
        try:
            result = session.query(self.user_whitelist_table).filter_by(
                user_id=user_id, group_id=group_id
            ).first()
            return result is not None
        finally:
            session.close()

    def is_group_whitelisted(self, group_id: str) -&gt; bool:
        session = self.Session()
        try:
            result = session.query(self.group_whitelist_table).filter_by(group_id=group_id).first()
            return result is not None
        finally:
            session.close()

    def add_user_to_whitelist(self, user_id: str, group_id: str) -&gt; bool:
        session = self.Session()
        try:
            if self.is_user_whitelisted(user_id, group_id):
                return False
            session.execute(self.user_whitelist_table.insert().values(user_id=user_id, group_id=group_id))
            session.commit()
            return True
        finally:
            session.close()

    def remove_user_from_whitelist(self, user_id: str, group_id: str) -&gt; bool:
        session = self.Session()
        try:
            result = session.execute(
                self.user_whitelist_table.delete()
                .where(self.user_whitelist_table.c.user_id == user_id, self.user_whitelist_table.c.group_id == group_id)
            )
            session.commit()
            return result.rowcount &gt; 0
        finally:
            session.close()

    def add_group_to_whitelist(self, group_id: str) -&gt; bool:
        session = self.Session()
        try:
            if self.is_group_whitelisted(group_id):
                return False
            session.execute(self.group_whitelist_table.insert().values(group_id=group_id))
            session.commit()
            return True
        finally:
            session.close()

    def remove_group_from_whitelist(self, group_id: str) -&gt; bool:
        session = self.Session()
        try:
            result = session.execute(
                self.group_whitelist_table.delete()
                .where(self.group_whitelist_table.c.group_id == group_id)
            )
            session.commit()
            return result.rowcount &gt; 0
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

    def _check_group_permission(self, group_id: str) -&gt; bool:
        """检查群是否有权限使用此插件"""
        mode = self.config.get("basic.group_list_mode", "none")
        group_list = self.config.get("basic.group_list", [])

        if mode == "none":
            return True

        # 尝试匹配完整ID或纯群号
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

    async def _detect_ad(self, event: AstrMessageEvent) -&gt; tuple[bool, str, str]:
        """检测消息是否为广告"""
        regex_rules = self.config.get("basic.regex_rules", [])
        message_str = event.message_str or ""

        # 正则检测
        if self.config.get("basic.enable_regex_detection", True):
            for rule in regex_rules:
                try:
                    if re.search(rule, message_str, re.IGNORECASE):
                        return True, f"匹配到违规关键词: {rule}", "regex"
                except re.error:
                    continue

        # 引用消息检测
        if self.config.get("basic.enable_quote_detection", False):
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

        return False, "", ""

    async def _handle_violation(self, event: AstrMessageEvent, reason: str, detection_type: str):
        """处理违规消息"""
        user_id = str(event.get_sender_id())
        group_id = str(event.group_id) if event.group_id else ""

        if not group_id:
            return

        # 检查数据库白名单
        if self.db.is_group_whitelisted(group_id) or self.db.is_user_whitelisted(user_id, group_id):
            return

        violation = self.db.add_violation(user_id, group_id)

        # 撤回消息
        if self.config.get("action.enable_withdraw", True):
            try:
                await event.recall()
            except Exception:
                pass

        # 发送警告
        if self.config.get("action.enable_warn", True):
            warn_msg = self.config.get("action.warn_message", "检测到您发送了广告内容，请遵守群规！")
            full_msg = f"{warn_msg}\n违规原因：{reason}\n当前违规次数：{violation.violation_count}"
            try:
                await event.send(full_msg)
            except Exception:
                pass

        # 踢出群
        if self.config.get("action.enable_kick", False):
            threshold = self.config.get("action.warn_threshold", 3)
            if violation.violation_count &gt;= threshold:
                try:
                    await self.context.kick_group_member(group_id, user_id)
                except Exception:
                    pass

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """处理群消息"""
        try:
            group_id = str(event.group_id) if event.group_id else ""
            if not group_id:
                return

            # 检查群权限
            if not self._check_group_permission(group_id):
                return

            is_ad, reason, detection_type = await self._detect_ad(event)
            if is_ad:
                await self._handle_violation(event, reason, detection_type)
        except Exception as e:
            logger.warning(f"处理消息失败: {e}")

    @filter.command("广告违规", alias={"ad_violation"})
    @filter.permission_type(PermissionType.ADMIN)
    async def cmd_violation(self, event: AstrMessageEvent, user_id: str = ""):
        """查看用户违规记录 [用户ID]"""
        if not user_id:
            await event.send("请指定要查询的用户ID：/广告违规 [用户ID]")
            return
        group_id = str(event.group_id) if event.group_id else ""
        record = self.db.get_violation(user_id, group_id)
        if record:
            await event.send(f"用户 {user_id} 的违规记录：\n违规次数：{record.violation_count}\n最近违规时间：{record.last_violation_time}")
        else:
            await event.send(f"未找到用户 {user_id} 的违规记录")

    @filter.command("重置违规", alias={"ad_reset"})
    @filter.permission_type(PermissionType.ADMIN)
    async def cmd_reset(self, event: AstrMessageEvent, user_id: str = ""):
        """重置用户违规记录 [用户ID]"""
        if not user_id:
            await event.send("请指定要重置的用户ID：/重置违规 [用户ID]")
            return
        group_id = str(event.group_id) if event.group_id else ""
        success = self.db.reset_violation(user_id, group_id)
        await event.send(f"{'已重置' if success else '未找到'}用户 {user_id} 的违规记录")

    @filter.command("用户白名单", alias={"ad_whitelist"})
    @filter.permission_type(PermissionType.ADMIN)
    async def cmd_whitelist(self, event: AstrMessageEvent, action: str = "", user_id: str = ""):
        """管理用户白名单 [add/remove] [用户ID]"""
        if not action or action not in ["add", "remove"]:
            await event.send("用法：\n/用户白名单 add [用户ID] - 添加白名单\n/用户白名单 remove [用户ID] - 移除白名单")
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

    @filter.command("群白名单", alias={"ad_gwhitelist"})
    @filter.permission_type(PermissionType.ADMIN)
    async def cmd_group_whitelist(self, event: AstrMessageEvent, action: str = ""):
        """管理群组白名单 [add/remove]"""
        if not action or action not in ["add", "remove"]:
            await event.send("用法：\n/群白名单 add - 添加本群白名单\n/群白名单 remove - 移除本群白名单")
            return
        group_id = str(event.group_id) if event.group_id else ""
        if action == "add":
            success = self.db.add_group_to_whitelist(group_id)
            await event.send(f"{'已添加' if success else '本群已在'}白名单")
        else:
            success = self.db.remove_group_from_whitelist(group_id)
            await event.send(f"{'已移除' if success else '本群不在'}白名单")

    @filter.command("广告帮助", alias={"ad_help"})
    async def cmd_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """广告检测插件命令：
/广告违规 [用户ID] - 查看用户违规记录
/重置违规 [用户ID] - 重置用户违规记录
/用户白名单 [add/remove] [用户ID] - 管理用户白名单
/群白名单 [add/remove] - 管理群组白名单
/广告帮助 - 显示此帮助"""
        await event.send(help_text)

