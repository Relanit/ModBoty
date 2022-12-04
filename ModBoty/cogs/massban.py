import asyncio
import time
from typing import Generator, TypedDict

from twitchio.ext.commands import Cog, command, Context
from twitchio import Message

from config import config

reason = 'Сообщение, содержащее запрещённую фразу: "%s" (от ModBoty). Начато %s'

LoggedMessage = TypedDict("LoggedMessage", {"author": str, "content": str, "first": bool, "time": float})


def most_common_substring(strings: list[str]) -> tuple[str, int]:
    """
    Gets the longest most common substring
    Returns string and number of matches
    """

    def matches(s1: str, s2: str) -> Generator[str]:
        final = {s1[i : b + 1] for i in range(len(s1)) for b in range(len(s1))}
        return (i for i in final if i in s1 and i in s2 and 15 >= len(i) > 2)

    substring_counts = {}
    for i in range(len(strings)):
        for j in range(i + 1, len(strings)):
            for match in matches(strings[i], strings[j]):
                substring_counts[match] = substring_counts.get(match, 0) + 1

    substrings = substring_counts.items() or [("", 0)]
    m = max(substrings, key=lambda x: x[1])[1]
    top = [substring for substring in substrings if substring[1] == m]
    return max(top, key=lambda x: len(x[0]))


class MassBan(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ban_phrases: dict[str, str] = {}
        self.queue: dict[str, list[str]] = {}
        self.message_history: dict[str, list[LoggedMessage]] = {
            channel: [] for channel in config["Bot"]["channels"].split()
        }

    @Cog.event()
    async def event_message(self, message: Message):
        if message.echo:
            return

        if message.channel.name in self.ban_phrases and (
            message.author.is_mod or message.author.name == self.bot.admin
        ):
            if message.content.startswith(self.bot.prefix):
                content = message.content.lstrip(self.bot.prefix)
                if not content:
                    return

                command = content.split(maxsplit=1)[0].lower()
                if command == "stop":
                    self.ban_phrases.pop(message.channel.name, None)
                    self.queue.pop(message.channel.name, None)
                    ctx = await self.bot.get_context(message)
                    while ctx.limited:
                        await asyncio.sleep(0.1)
                    await ctx.reply("Остановлено")
            return

        self.message_history[message.channel.name].append(
            {
                "author": message.author.name,
                "content": message.content,
                "first": message.first,
                "time": time.time(),
            }
        )
        if len(self.message_history[message.channel.name]) >= 50:
            del self.message_history[message.channel.name][0]

        if (
            self.ban_phrases.get(message.channel.name)
            and self.ban_phrases[message.channel.name] in message.content.lower()
        ):
            self.queue[message.channel.name].append(message.author.name)

    @command(
        name="mb",
        aliases=["mt", "m"],
        cooldown={"per": 0, "gen": 60},
        description="Бан/мут пользователей, написавших сообщение с указанной фразой. Полное описание - https://vk.cc/chCfLq ",
        flags=["bot-mod"],
    )
    async def mass_ban(self, ctx: Context):
        content = ban_phrase = ctx.content.lower()

        if not content and ctx.command_alias in ("mt", "m"):
            await ctx.send("Введите время и мутфразу")
            return

        if ctx.command_alias in ("mt", "m"):
            content_split = content.split(" ", 1)
            try:
                timeout = int(content_split[0])
                if len(content_split) == 1:
                    await ctx.send("Введите мутфразу")
                    return
                if not 1 <= timeout <= 1209600:
                    await ctx.reply("Допустимая длительность мута от 1 до 1209600 секунд")
                    return
                ban_phrase = content_split[1]
            except ValueError:
                timeout = 300
            text = f"/timeout %s {timeout} {reason % (ban_phrase, ctx.author.name)}"
        else:
            text = f"/ban %s {reason % (ban_phrase, ctx.author.name)}"

        self.queue[ctx.channel.name] = []
        banned_users = []
        reply = "Запущено"

        if not ban_phrase:
            first_messages = [message for message in self.message_history[ctx.channel.name].copy() if message["first"]]

            if len(first_messages) > 1:  # an attempt to separate users from bots by removing single messages
                first_messages_copy = first_messages.copy()
                for i, message in enumerate(first_messages_copy):
                    if message != first_messages_copy[-1]:
                        if i == 0:
                            if first_messages_copy[i + 1]["time"] - message["time"] > 1:
                                first_messages.remove(message)
                        elif (
                            message["time"] - first_messages_copy[i - 1]["time"] > 1
                            and first_messages_copy[i + 1]["time"] - message["time"] > 1
                        ):
                            first_messages.remove(message)
                    elif message["time"] - first_messages_copy[i - 1]["time"] > 1:
                        first_messages.remove(message)

            if not first_messages:
                self.ban_phrases.pop(ctx.channel.name, None)
                self.queue.pop(ctx.channel.name, None)
                await ctx.reply("Сообщений от новых пользователей не найдено")
                return

            characters = 0
            i = 0
            for index, message in enumerate(first_messages[-20:], start=1):
                characters += len(message["content"])
                if characters > 2200:
                    break
                i = index

            strings = [message["content"].lower() for message in first_messages[-i:]]
            ban_phrase, count = most_common_substring(strings)

            _, max_count = most_common_substring(["asd"] * len(first_messages[-i:]))
            found = count > max_count / 100 * 60 if count else False

            if not found:
                while ctx.limited:
                    await asyncio.sleep(0.1)

                await ctx.reply("Запущено, банфраза не найдена, будут забанены последние новые пользователи")
                text = f'/ban %s {reason % ("Первое сообщение в чате", ctx.author.name)}'

                for message in first_messages:
                    while ctx.limited:
                        await asyncio.sleep(0.1)
                    if ctx.channel.name not in self.queue:
                        return
                    await ctx.send(text % message["author"])
                    banned_users.append(message["author"])
                    await asyncio.sleep(0.3)

                self.ban_phrases.pop(ctx.channel.name, None)
                self.queue.pop(ctx.channel.name, None)
                return

            text = f"/ban %s {reason % (ban_phrase, ctx.author.name)}"
            reply = "Запущено, банфраза найдена"

        while ctx.limited:
            await asyncio.sleep(0.1)
        await ctx.reply(reply)

        start = time.time()
        self.ban_phrases[ctx.channel.name] = ban_phrase

        for message in self.message_history[ctx.channel.name].copy():
            if ban_phrase in message["content"].lower() and message["author"] not in banned_users:
                while ctx.limited:
                    await asyncio.sleep(0.1)
                if ctx.channel.name not in self.ban_phrases:
                    return
                await ctx.send(text % message["author"])
                banned_users.append(message["author"])
                await asyncio.sleep(0.3)

        while ctx.channel.name in self.ban_phrases:
            for user in self.queue[ctx.channel.name]:
                if user not in banned_users:
                    while ctx.limited:
                        await asyncio.sleep(0.1)
                    if ctx.channel.name not in self.ban_phrases:
                        return
                    await ctx.send(text % user)
                    banned_users.append(user)
                    await asyncio.sleep(0.3)

            if time.time() - start > 300:
                self.ban_phrases.pop(ctx.channel.name, None)
                self.queue.pop(ctx.channel.name, None)
                return

            banned_users.clear()
            self.queue.get(ctx.channel.name, []).clear()
            await asyncio.sleep(0.1)


def prepare(bot):
    bot.add_cog(MassBan(bot))
