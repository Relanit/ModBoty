import time

from twitchio import Message


def get_cooldown_end(cooldown: dict[str, int]) -> (float, float):
    """Returns personal and general cooldown ends"""
    now = time.time()
    per_end = now + cooldown["per"]
    gen_end = now + cooldown["gen"]
    return per_end, gen_end


class Cooldown:
    def __init__(self, channels: list[str]):
        self.cooldowns = {channel: {} for channel in channels}

    async def check_command(self, command: str, message: Message, admin: bool = False) -> bool | None:
        """
        Check user access level by command's flags, check cooldown expiration and set new one
        Returns True if successful else None
        """

        now = time.time()
        data = self.get_command(command)

        channel = message.channel.name

        if not admin:
            user = message.author.name
            if not message.author.is_mod or "admin" in data.flags:
                return
            if (
                command in self.editor_commands[message.channel.name]
                and message.author.name not in self.editors[message.channel.name]
                and not message.author.is_broadcaster
            ):
                ctx = await self.get_context(message)
                await ctx.reply("Эта команда доступна только редакторам бота - https://vk.cc/cijFyF")
                return
            if command in self.cooldowns[channel]:
                if self.cooldowns[channel][command]["gen"] < now > self.cooldowns[channel][command]["per"].get(user, 0):
                    (
                        self.cooldowns[channel][command]["per"][user],
                        self.cooldowns[channel][command]["gen"],
                    ) = get_cooldown_end(data.cooldown)
                    return True

                return

            per_end, gen_end = get_cooldown_end(data.cooldown)
            self.cooldowns[channel][command] = {"per": {user: per_end}, "gen": gen_end}
            return True

        if "admin" in data.flags:
            return True

        if command in self.cooldowns[channel]:
            _, self.cooldowns[channel][command]["gen"] = get_cooldown_end(data.cooldown)
            return True

        _, gen_end = get_cooldown_end(data.cooldown)
        self.cooldowns[channel][command] = {"per": {}, "gen": gen_end}
        return True
