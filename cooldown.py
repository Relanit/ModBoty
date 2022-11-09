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
                ):
                    (
                        self.cooldowns[message.channel.name][command]["per"][user],
                        self.cooldowns[message.channel.name][command]["gen"],
                    ) = get_cooldown_end(data.cooldown)
                    return True

                return

            per_end, gen_end = get_cooldown_end(data.cooldown)
            self.cooldowns[message.channel.name][command] = {"per": {user: per_end}, "gen": gen_end}
            return True

        if "admin" in data.flags:
            return True

        if command in self.cooldowns[message.channel.name]:
            _, self.cooldowns[message.channel.name][command]["gen"] = get_cooldown_end(data.cooldown)
            return True

        _, gen_end = get_cooldown_end(data.cooldown)
        self.cooldowns[message.channel.name][command] = {"per": {}, "gen": gen_end}
        return True
