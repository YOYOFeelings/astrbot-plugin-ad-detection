from typing import List, Dict, Any
from astrbot.api.event import AstrMessageEvent
from .database import DatabaseManager, ViolationRecord


class CommandManager:
    def __init__(self, config: Dict[str, Any], db: DatabaseManager, context):
        self.config = config
        self.db = db
        self.context = context

    def is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            sender = event.sender
            role = getattr(sender, 'role', None)
            return role in ["admin", "owner"]
        except Exception:
            return False

    async def cmd_violation(self, event: AstrMessageEvent, args: List[str]):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return

        group_id = str(event.group_id) if event.group_id else ""
        user_id = str(event.sender.user_id) if event.sender else ""

        if len(args) > 0:
            target_user_id = args[0]
        else:
            await event.send("请指定要查询的用户ID")
            return

        record = self.db.get_violation(target_user_id, group_id)
        if record:
            await event.send(
                f"用户 {target_user_id} 的违规记录：\n"
                f"违规次数：{record.violation_count}\n"
                f"最近违规时间：{record.last_violation_time}"
            )
        else:
            await event.send(f"未找到用户 {target_user_id} 的违规记录")

    async def cmd_reset_violation(self, event: AstrMessageEvent, args: List[str]):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return

        group_id = str(event.group_id) if event.group_id else ""

        if len(args) > 0:
            target_user_id = args[0]
        else:
            await event.send("请指定要重置的用户ID")
            return

        success = self.db.reset_violation(target_user_id, group_id)
        if success:
            await event.send(f"已重置用户 {target_user_id} 的违规记录")
        else:
            await event.send(f"未找到用户 {target_user_id} 的违规记录")

    async def cmd_whitelist_user(self, event: AstrMessageEvent, args: List[str]):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return

        group_id = str(event.group_id) if event.group_id else ""

        if len(args) < 2:
            await event.send("请使用：/ad_whitelist_user <add/remove> <用户ID>")
            return

        action = args[0]
        target_user_id = args[1]

        if action == "add":
            success = self.db.add_user_to_whitelist(target_user_id, group_id)
            if success:
                await event.send(f"已将用户 {target_user_id} 加入白名单")
            else:
                await event.send(f"用户 {target_user_id} 已在白名单中")
        elif action == "remove":
            success = self.db.remove_user_from_whitelist(target_user_id, group_id)
            if success:
                await event.send(f"已将用户 {target_user_id} 从白名单移除")
            else:
                await event.send(f"用户 {target_user_id} 不在白名单中")
        else:
            await event.send("无效的操作，请使用 add 或 remove")

    async def cmd_whitelist_group(self, event: AstrMessageEvent, args: List[str]):
        if not self.is_admin(event):
            await event.send("您没有权限执行此命令")
            return

        group_id = str(event.group_id) if event.group_id else ""

        if len(args) < 1:
            await event.send("请使用：/ad_whitelist_group <add/remove>")
            return

        action = args[0]

        if action == "add":
            success = self.db.add_group_to_whitelist(group_id)
            if success:
                await event.send("已将本群加入白名单")
            else:
                await event.send("本群已在白名单中")
        elif action == "remove":
            success = self.db.remove_group_from_whitelist(group_id)
            if success:
                await event.send("已将本群从白名单移除")
            else:
                await event.send("本群不在白名单中")
        else:
            await event.send("无效的操作，请使用 add 或 remove")

    async def cmd_help(self, event: AstrMessageEvent):
        help_text = (
            "广告检测插件命令：\n"
            "/ad_violation <用户ID> - 查看用户违规记录\n"
            "/ad_reset_violation <用户ID> - 重置用户违规记录\n"
            "/ad_whitelist_user <add/remove> <用户ID> - 管理用户白名单\n"
            "/ad_whitelist_group <add/remove> - 管理群组白名单\n"
            "/ad_help - 显示此帮助信息"
        )
        await event.send(help_text)

    def get_commands(self):
        from astrbot.api.event import filter
        
        @filter.command("ad_violation")
        async def ad_violation(event: AstrMessageEvent, user_id: str = ""):
            await self.cmd_violation(event, [user_id] if user_id else [])
        
        @filter.command("ad_reset_violation")
        async def ad_reset_violation(event: AstrMessageEvent, user_id: str = ""):
            await self.cmd_reset_violation(event, [user_id] if user_id else [])
        
        @filter.command("ad_whitelist_user")
        async def ad_whitelist_user(event: AstrMessageEvent, action: str = "", user_id: str = ""):
            if action and user_id:
                await self.cmd_whitelist_user(event, [action, user_id])
            else:
                await event.send("请使用：/ad_whitelist_user <add/remove> <用户ID>")
        
        @filter.command("ad_whitelist_group")
        async def ad_whitelist_group(event: AstrMessageEvent, action: str = ""):
            if action:
                await self.cmd_whitelist_group(event, [action])
            else:
                await event.send("请使用：/ad_whitelist_group <add/remove>")
        
        @filter.command("ad_help")
        async def ad_help(event: AstrMessageEvent):
            await self.cmd_help(event)
        
        return [ad_violation, ad_reset_violation, ad_whitelist_user, ad_whitelist_group, ad_help]
