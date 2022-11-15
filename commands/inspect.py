from typing import TypedDict
import asyncio
import time

from twitchio.ext.commands import Cog, command, Context
from twitchio import Message

from config import db


class Limits(TypedDict):
    first_limit: dict[str, int | float]
    second_limit: dict[str, int | float]
    percent_limit: int
    timeouts: list[int]
    stats: dict[str, int]
    active: bool
    offline: bool


class LoggedMessage(TypedDict):
    time: float
    author: str


class Inspect(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.limits: dict[str, Limits] = {}
        self.timeouts: dict[str, list[int]] = {}
        self.warned_users: dict[str, dict[str, int]] = {}
        self.message_log: dict[str, list[LoggedMessage]] = {}

    @Cog.event()
    async def event_message(self, message: Message):
        if message.echo:
            return

        if message.channel.name in self.limits:
            now = time.time()
            self.message_log[message.channel.name].append({"time": now, "author": message.author.name})

            first_limit = self.limits[message.channel.name].get("first_limit", {})
            second_limit = self.limits[message.channel.name].get("second_limit", {})
            main_limit, secondary_limit = (
                (first_limit, second_limit)
                if first_limit.get("time_unit", 0) > second_limit.get("time_unit", 0)
                else (second_limit, first_limit)
            )

            for msg in self.message_log[message.channel.name].copy():
                if now - msg["time"] > main_limit["time_unit"]:
                    del self.message_log[message.channel.name][0]
                else:
                    break

            if message.author.is_mod:
                return

            percent_limit = self.limits[message.channel.name].get("percent_limit", 0)

            chatters = [msg["author"] for msg in self.message_log[message.channel.name]]
            count = chatters.count(message.author.name)
            handle = True

            if count > main_limit["messages"]:
                handle = bool(percent_limit and count <= len(chatters) / 100 * percent_limit)

            if secondary_limit and handle:
                #  choosing the order of iteration depending on the time unit of the smaller limit
                if main_limit["time_unit"] < secondary_limit["time_unit"] * 2:
                    message_log = self.message_log[message.channel.name].copy()
                    for msg in message_log.copy():
                        if now - msg["time"] > secondary_limit["time_unit"]:
                            del message_log[0]
                        else:
                            break
                    chatters = [msg["author"] for msg in message_log]
                else:
                    chatters = []
                    for msg in self.message_log[message.channel.name][::-1]:
                        if now - msg["time"] > secondary_limit["time_unit"]:
                            break
                        else:
                            chatters.append(msg["author"])

                count = chatters.count(message.author.name)

                if count > secondary_limit["messages"]:
                    handle = bool(percent_limit and count <= len(chatters) / 100 * percent_limit)

            if not handle:
                # remove user's messages from message log
                new = [msg for msg in self.message_log[message.channel.name] if msg["author"] != message.author.name]
                self.message_log[message.channel.name] = new

                if message.channel.name in self.bot.streams:
                    await db.inspects.update_one(
                        {"channel": message.channel.name},
                        {"$inc": {f"stats.{message.author.name}": 1}},
                    )

                if message.author.name in self.warned_users[message.channel.name]:
                    i = self.warned_users[message.channel.name][message.author.name]
                    timeout = self.timeouts[message.channel.name][i]

                    if (
                        len(self.timeouts[message.channel.name])
                        > self.warned_users[message.channel.name][message.author.name] + 1
                    ):  # increase timeout if possible
                        self.warned_users[message.channel.name][message.author.name] += 1

                    while message.channel.limited:
                        await asyncio.sleep(0.1)
                    await message.channel.send(f"/timeout {message.author.name} {timeout} Спам (от ModBoty)")
                else:
                    self.warned_users[message.channel.name][message.author.name] = 0
                    ctx = await self.bot.get_context(message)
                    await ctx.reply("Без спамчика :|")

                    while ctx.limited:
                        await asyncio.sleep(0.1)
                    await ctx.send(f"/timeout {message.author.name} 10 Спам (от ModBoty)")

    @command(
        name="inspect",
        cooldown={"per": 0, "gen": 3},
        description="Лимиты на количество отправленных сообщений. Полное описание - https://vk.cc/chCfJI ",
    )
    async def inspect(self, ctx: Context):
        if not ctx.channel.bot_is_mod:
            await ctx.reply("Боту необходима модерка для работы этой команды")
            return

        content = ctx.content.lower()
        data = await db.inspects.find_one({"channel": ctx.channel.name}) or {}

        if (not content or content in ("on", "off") or content.startswith("stats")) and not data:
            await ctx.reply("Сначала настройте наблюдение - https://vk.cc/chCfJI ")
            return

        if not content:
            await self.view_settings(ctx, data)
        elif content in ("off", "on"):
            await self.switch(ctx, data)
        elif content.startswith("stats"):
            await self.stats(ctx, data)
        else:
            await self.edit(ctx, data)

    @staticmethod
    async def view_settings(ctx: Context, data: dict):
        first_limit = data.get("first_limit")
        second_limit = data.get("second_limit")
        percent_limit = (
            f'Лимит от всех сообщений в чате:  {data["percent_limit"]}%.' if "percent_limit" in data else False
        )

        if first_limit:
            first_limit = (
                f'{first_limit["messages"]}/'
                f'{first_limit["time_unit"] if first_limit["time_unit"] % 1 != 0 else int(first_limit["time_unit"])}'
                f'{", " if second_limit else ""}'
            )
        if second_limit:
            second_limit = (
                f' {second_limit["messages"]}//'
                f'{second_limit["time_unit"] if second_limit["time_unit"] % 1 != 0 else int(second_limit["time_unit"])}.'
            )

        message = (
            f'Статус: {"включено" if data["active"] else "выключено"}. '
            f'Лимиты: {first_limit or ""}{second_limit or "."} {percent_limit or ""} '
            f'Таймауты: {", ".join(map(str, data["timeouts"]))}. {"" if data["offline"] else "Только на стриме."}'
        )

        await ctx.reply(message)

    async def switch(self, ctx: Context, data: dict):
        if ctx.content.lower() == "on":
            if ctx.channel.name not in self.limits and (ctx.channel.name in self.bot.streams or data["offline"]):
                await self.set(ctx.channel.name)
            await db.inspects.update_one({"channel": ctx.channel.name}, {"$set": {"active": True}})
            await ctx.reply("✅ Включено")
        else:
            if ctx.channel.name in self.limits:
                self.unset(ctx.channel.name)
            await db.inspects.update_one({"channel": ctx.channel.name}, {"$set": {"active": False}})
            await ctx.reply("❌ Выключено")

    @staticmethod
    async def stats(ctx: Context, data: dict):
        content = ctx.content.lower()
        if not data.get("stats"):
            await ctx.reply("Статистика не найдена")
            return

        if content == "stats":
            items = data["stats"].items()
            sorted_users = sorted(items, key=lambda x: x[1], reverse=True)
            number = len(sorted_users)

            top = []
            for place, user in enumerate(sorted_users[:5], start=1):
                name = user[0][:1] + "\U000E0000" + user[0][1:]
                top.append(f'{place}. {name} - {user[1]}{" отстранений" if place == 1 else ""}')

            await ctx.reply(f'Всего отстранено: {number}. Топ спамеров за стрим: {", ".join(top)}')
        else:
            user = content.split()[1]
            if user not in data["stats"]:
                await ctx.reply("У пользователя 0 отстранений")
                return

            items = data["stats"].items()
            sorted_users = sorted(items, key=lambda x: x[1], reverse=True)

            for pos in range(len(sorted_users)):
                if ctx.author.name in sorted_users[pos]:
                    place = pos + 1
                    timeouts = sorted_users[pos][1]
                    break

            await ctx.reply(f"{place} место ({timeouts} отстранений)")

    async def edit(self, ctx: Context, data: dict):
        content = ctx.content.lower().split()
        values = {"$set": {}, "$unset": {}}

        for value in content:
            if "/" in value:
                split, limit = ("//", "second_limit") if "//" in value else ("/", "first_limit")

                if value.replace("/", ""):
                    try:
                        messages, time_unit = value.replace(",", ".").split(split)
                        messages = int(messages)
                        time_unit = round(float(time_unit), 1)
                    except ValueError:
                        await ctx.reply("Неверная запись времени или количества сообщений - https://vk.cc/chCfJI")
                        return

                    if not 1 <= time_unit <= 60:
                        await ctx.reply("Время не должно быть меньше 1 или больше 60 секунд")
                        return
                    if not 1 <= messages <= 60:
                        await ctx.reply("Количество сообщений не должно быть меньше 1 или больше 60.")
                        return

                    values["$set"][limit] = {
                        "messages": messages,
                        "time_unit": time_unit,
                    }
                elif (
                    data
                    and "first_limit" in data
                    and "second_limit" in data
                    and "first_limit" not in values["$unset"]
                    and "second_limit" not in values["$unset"]
                ):
                    values["$unset"][limit] = 1
                else:
                    await ctx.reply("Чтобы удалить лимит, должен быть установлен другой")
                    return
            elif value.endswith("%"):
                percent_limit = value.strip("%")

                if percent_limit:
                    try:
                        percent_limit = int(percent_limit)
                    except ValueError:
                        await ctx.reply("Неверная запись лимита в процентах - https://vk.cc/chCfJI")
                        return

                    if not 0 <= percent_limit < 100:
                        await ctx.reply("Неверная запись лимита в процентах - https://vk.cc/chCfJI")
                        return

                if not percent_limit:
                    values["$unset"]["percent_limit"] = 1
                else:
                    values["$set"]["percent_limit"] = percent_limit
            elif value == "online":
                values["$set"]["offline"] = False
            elif value == "always":
                values["$set"]["offline"] = True
            else:
                try:
                    timeout = int(value)
                    values["$set"]["timeouts"] = [] if "timeouts" not in values["$set"] else values["$set"]["timeouts"]
                    values["$set"]["timeouts"].append(timeout)
                except ValueError:
                    await ctx.reply("Неверная запись таймаутов или команды - https://vk.cc/chCfJI")
                    return

                if not 1 <= timeout <= 1209600:
                    await ctx.reply("Неверное значение таймаута")
                    return

        first_unit = values["$set"].get("first_limit", data.get("first_limit", {})).get("time_unit", 0)
        second_unit = values["$set"].get("second_limit", data.get("second_limit", {})).get("time_unit", 0)
        if first_unit and first_unit == second_unit:
            await ctx.reply("Не должно быть двух лимитов с одинаковым временем")
            return
        elif first_unit > 15 and second_unit > 15:
            await ctx.reply("Не должно быть больше одного лимита с временем более 15 секунд")
            return

        on_insert = {"channel": ctx.channel.name, "active": False}
        if not data:
            if "first_limit" not in values["$set"] and "second_limit" not in values["$set"]:
                await ctx.reply("Для начала установите сообщения и время")
                return

            if "timeouts" not in values["$set"]:
                values["$set"]["timeouts"] = [60, 300, 600]
            if "offline" not in values["$set"]:
                on_insert["offline"] = False
        await db.inspects.update_one(
            {"channel": ctx.channel.name},
            {"$setOnInsert": on_insert, **values},
            upsert=True,
        )

        if ctx.channel.name not in self.bot.streams:
            if values["$set"].get("offline", data.get("offline")) and data.get("active"):
                await self.set(ctx.channel.name)
            elif ctx.channel.name in self.limits:
                self.unset(ctx.channel.name)
        elif ctx.channel.name in self.limits:
            await self.set(ctx.channel.name)

        await ctx.reply("Готово.")

    async def set(self, channel: str):
        data = await db.inspects.find_one({"channel": channel})
        self.limits[channel] = {}
        self.timeouts[channel] = data["timeouts"]
        self.warned_users[channel] = {}
        self.message_log[channel] = []

        if "first_limit" in data:
            limit = data["first_limit"]
            self.limits[channel]["first_limit"] = {
                "messages": limit["messages"],
                "time_unit": limit["time_unit"],
            }
        if "second_limit" in data:
            limit = data["second_limit"]
            self.limits[channel]["second_limit"] = {
                "messages": limit["messages"],
                "time_unit": limit["time_unit"],
            }
        if "percent_limit" in data:
            self.limits[channel]["percent_limit"] = data["percent_limit"]

    def unset(self, channel: str):
        del self.limits[channel]
        del self.timeouts[channel]
        del self.warned_users[channel]
        del self.message_log[channel]


def prepare(bot):
    bot.add_cog(Inspect(bot))
