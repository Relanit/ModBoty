import time
from typing import Literal

from twitchio import Message


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

    async def check_command(self, command: str, message: Message, admin: bool = False) -> bool | None:
        """
        Check user access level by command's flags, check cooldown expiration and set new one
        Returns True if successful else None
        """

        data = self.get_command(command)

        if not admin:
            user = message.author.name
            if not message.author.is_mod or "admin" in data.flags:
                return
            if (
                (command in self.editor_commands.get(message.channel.name, []) or "editor" in data.flags)
                and message.author.name not in self.editors.get(message.channel.name, [])
                and not message.author.is_broadcaster
            ):
                return
            if command in self.cooldowns[message.channel.name]:
                if (
                    self.cooldowns[message.channel.name][command]["gen"]
                    < time.time()
                    > self.cooldowns[message.channel.name][command]["per"].get(user, 0)
                ) and await self.check_bot_role(message, data.flags, command):
                    (
                        self.cooldowns[message.channel.name][command]["per"][user],
                        self.cooldowns[message.channel.name][command]["gen"],
                    ) = get_cooldown_end(data.cooldown)
                    return True

                return

            if await self.check_bot_role(message, data.flags, command):
                per_end, gen_end = get_cooldown_end(data.cooldown)
                self.cooldowns[message.channel.name][command] = {"per": {user: per_end}, "gen": gen_end}
            return True

        if "admin" in data.flags:
            return True

        if command in self.cooldowns[message.channel.name] and await self.check_bot_role(message, data.flags, command):
            _, self.cooldowns[message.channel.name][command]["gen"] = get_cooldown_end(data.cooldown)
            return True

        if await self.check_bot_role(message, data.flags, command):
            _, gen_end = get_cooldown_end(data.cooldown)
            self.cooldowns[message.channel.name][command] = {"per": {}, "gen": gen_end}
        return True

    async def check_bot_role(self, message: Message, flags: list, command: str):
        """Check if the bot has the necessary role to execute the command"""
        if ("bot-vip" not in flags or message.channel.bot_is_vip or message.channel.bot_is_mod) and (
            "bot-mod" not in flags or message.channel.bot_is_mod
        ):
            return True
        if "bot-vip" in flags:
            text = f"@{message.author.name} Боту необходима випка или модерка для работы этой команды. Если роль выдана, вызовите команду ещё раз"
        else:
            text = f"@{message.author.name} Боту необходима модерка для работы этой команды. Если роль выдана, вызовите команду ещё раз"
        await message.channel.send(text)
        if command in self.cooldowns[message.channel.name]:
            self.cooldowns[message.channel.name][command]["gen"] = time.time() + 1
        else:
            self.cooldowns[message.channel.name][command] = {"per": {}, "gen": time.time() + 1}
        return
