import time
from typing import Literal

from twitchio import Message
from twitchio.ext.commands import Context


def get_cooldown_end(cooldown: dict[Literal["per", "gen"], int]) -> (float, float):
    """Returns personal and general cooldown ends"""
    per_end = time.time() + cooldown["per"]
    gen_end = time.time() + cooldown["gen"]
    return per_end, gen_end


class Cooldown:
    def __init__(self, channels: list[str]):
        self.cooldowns: dict[str, dict[str, dict[str, float | dict[str, float]]]] = {
            channel: {} for channel in channels
        }

    async def check_command(self, command_name: str, message: Message, admin: bool = False) -> bool | None:
        """
        Check user access level by command's flags, check cooldown expiration and set new one
        Returns True if successful else None
        """

        command = self.get_command(command_name)

        if not admin:
            user = message.author.name
            if "admin" in command.flags:
                return
            if (
                "7tv-editor" in command.flags
                and message.author.name not in self.stv_editors.get(message.channel.name, [])
                and not message.author.is_broadcaster
            ):
                return
            if "7tv-editor" not in command.flags and not message.author.is_mod:
                return
            if message.custom_tags.get("mention") and "mention" not in command.flags:
                return
            if (
                command.name in self.editor_commands.get(message.channel.name, [])
                and message.author.name not in self.editors.get(message.channel.name, [])
                and not message.author.is_broadcaster
            ):
                return

            if await self.check_bot_role(message, command.flags, command.name):
                if command.name in self.cooldowns[message.channel.name]:
                    if (
                        self.cooldowns[message.channel.name][command.name]["gen"]
                        < time.time()
                        > self.cooldowns[message.channel.name][command.name]["per"].get(user, 0)
                    ):
                        self.set_cooldown(message, command.name, command.cooldown)
                        return True

                    return

                per_end, gen_end = get_cooldown_end(command.cooldown)
                self.cooldowns[message.channel.name][command.name] = {"per": {user: per_end}, "gen": gen_end}
                return True

            return

        if "admin" in command.flags:
            return True

        if await self.check_bot_role(message, command.flags, command.name):
            if command.name in self.cooldowns[message.channel.name]:
                _, self.cooldowns[message.channel.name][command.name]["gen"] = get_cooldown_end(command.cooldown)
            else:
                _, gen_end = get_cooldown_end(command.cooldown)
                self.cooldowns[message.channel.name][command.name] = {"per": {}, "gen": gen_end}
            return True

        return

    async def check_bot_role(self, message: Message, flags: list, command: str):
        """Check if the bot has the necessary role to execute the command"""
        if ("bot-vip" not in flags or message.channel.bot_is_vip or message.channel.bot_is_mod) and (
            "bot-mod" not in flags or message.channel.bot_is_mod
        ):
            return True
        if "bot-vip" in flags:
            text = f"{message.author.mention} Боту необходима випка или модерка для работы этой команды. Если роль выдана, вызовите команду ещё раз"
        else:
            text = f"{message.author.mention} Боту необходима модерка для работы этой команды. Если роль выдана, вызовите команду ещё раз"

        self.cooldowns[message.channel.name][command] = {"per": {}, "gen": time.time() + 1}
        await message.channel.send(text)

    def set_cooldown(self, message: Context | Message, command_name: str, cd: dict[Literal["per", "gen"], int]):
        (
            self.cooldowns[message.channel.name][command_name]["per"][message.author.name],
            self.cooldowns[message.channel.name][command_name]["gen"],
        ) = (
            time.time() + cd["per"],
            time.time() + cd["gen"],
        )
