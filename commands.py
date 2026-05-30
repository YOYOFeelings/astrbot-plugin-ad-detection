from typing import Optional, List
from astrbot.api.message import Message
from astrbot.api.command import Command
from astrbot.api.config import AstrBotConfig
from .database import DatabaseManager, ViolationRecord


class CommandManager:
    def __init__(self, config: AstrBotConfig, db: DatabaseManager):
        self.config = config
        self.db = db

    def is_admin(self, message: Message) -> bool:
        try:
            if hasattr(message, "is_admin"):
                return message.is_admin
            if hasattr(message, "sender_role"):
                return message.sender_role in ["admin", "owner"]
        except Exception:
            pass
        return False

    async def cmd_violation(self, message: Message, args: List[str]):
        if not self.is_admin(message):
            await message.reply("您没有权限执行此命令")
            return

        group_id = str(message.group_id) if message.group_id else ""
        user_id = str(message.sender.user_id) if message.sender else ""

        if len(args) > 0:
            target_user_id = args[0]
        else:
            await message.reply("请指定要查询的用户ID")
            return

        record = self.db.get_violation(target_user_id, group_id)
        if record:
            await message.reply(
                f"用户 {target_user_id} 的违规记录：\n"
                f"违规次数：{record.violation_count}\n"
                f"最近违规时间：{record.last_violation_time}"
            )
        else:
            await message.reply(f"未找到用户 {target_user_id} 的违规记录")

    async def cmd_reset_violation(self, message: Message, args: List[str]):
        if not self.is_admin(message):
            await message.reply("您没有权限执行此命令")
            return

        group_id = str(message.group_id) if message.group_id else ""

        if len(args) > 0:
            target_user_id = args[0]
        else:
            await message.reply("请指定要重置的用户ID")
            return

        success = self.db.reset_violation(target_user_id, group_id)
        if success:
            await message.reply(f"已重置用户 {target_user_id} 的违规记录")
        else:
            await message.reply(f"未找到用户 {target_user_id} 的违规记录")

    async def cmd_whitelist_user(self, message: Message, args: List[str]):
        if not self.is_admin(message):
            await message.reply("您没有权限执行此命令")
            return

        group_id = str(message.group_id) if message.group_id else ""

        if len(args) < 2:
            await message.reply("请使用：/ad_whitelist_user <add/remove> <用户ID>")
            return

        action = args[0]
        target_user_id = args[1]

        if action == "add":
            success = self.db.add_user_to_whitelist(target_user_id, group_id)
            if success:
                await message.reply(f"已将用户 {target_user_id} 加入白名单")
            else:
                await message.reply(f"用户 {target_user_id} 已在白名单中")
        elif action == "remove":
            success = self.db.remove_user_from_whitelist(target_user_id, group_id)
            if success:
                await message.reply(f"已将用户 {target_user_id} 从白名单移除")
            else:
                await message.reply(f"用户 {target_user_id} 不在白名单中")
        else:
            await message.reply("无效的操作，请使用 add 或 remove")

    async def cmd_whitelist_group(self, message: Message, args: List[str]):
        if not self.is_admin(message):
            await message.reply("您没有权限执行此命令")
            return

        group_id = str(message.group_id) if message.group_id else ""

        if len(args) < 1:
            await message.reply("请使用：/ad_whitelist_group <add/remove>")
            return

        action = args[0]

        if action == "add":
            success = self.db.add_group_to_whitelist(group_id)
            if success:
                await message.reply("已将本群加入白名单")
            else:
                await message.reply("本群已在白名单中")
        elif action == "remove":
            success = self.db.remove_group_from_whitelist(group_id)
            if success:
                await message.reply("已将本群从白名单移除")
            else:
                await message.reply("本群不在白名单中")
        else:
            await message.reply("无效的操作，请使用 add 或 remove")

    async def cmd_help(self, message: Message):
        help_text = (
            "广告检测插件命令：\n"
            "/ad_violation <用户ID> - 查看用户违规记录\n"
            "/ad_reset_violation <用户ID> - 重置用户违规记录\n"
            "/ad_whitelist_user <add/remove> <用户ID> - 管理用户白名单\n"
            "/ad_whitelist_group <add/remove> - 管理群组白名单\n"
            "/ad_help - 显示此帮助信息"
        )
        await message.reply(help_text)

    def get_commands(self):
        return [
            Command("ad_violation", self.cmd_violation, "查看用户违规记录"),
            Command("ad_reset_violation", self.cmd_reset_violation, "重置用户违规记录"),
            Command("ad_whitelist_user", self.cmd_whitelist_user, "管理用户白名单"),
            Command("ad_whitelist_group", self.cmd_whitelist_group, "管理群组白名单"),
            Command("ad_help", self.cmd_help, "显示帮助信息"),
        ]
