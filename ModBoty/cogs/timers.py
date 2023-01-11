import asyncio
import time
from random import shuffle
from typing import TypedDict

from twitchio.ext.commands import Cog, command, Context
from twitchio.ext.routines import routine

from config import db


class Timer(TypedDict):
    interval: int
    number: int
    active: bool
    cooldown: float
    announce: bool
    offline: bool


class Timers(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.timers: dict[str, dict[str, Timer]] = {}
        self.offline: dict[str, bool] = {}
        self.messages_from_timer: dict[str, int] = {}

        self.check_timers.start(stop_on_error=False)

    async def __ainit__(self):
        async for document in db.timers.find():
            timers = {}
            for timer in document["timers"]:
                link = timer.pop("link")
                timer["cooldown"] = 0
                timers[link] = timer

            self.timers[document["channel"]] = timers
            self.messages_from_timer[document["channel"]] = 0
            self.offline[document["channel"]] = document["offline"]

    @Cog.event()
    async def event_message(self, message):
        if message.echo or message.channel.name not in self.timers:
            return

        self.messages_from_timer[message.channel.name] += 1

    @command(
        name="timer",
        aliases=["delt", "timers"],
        cooldown={"per": 0, "gen": 3},
        description="Автоматическая отправка команд с определённым интервалом. Полное описание  ‒  https://vk.cc/chCfMF ",
        flags=["bot-vip"],
    )
    async def command(self, ctx: Context):
        if ctx.command_alias != "timers":
            if not self.bot.cogs["Links"].links.get(ctx.channel.name, None):
                await ctx.reply("На вашем канале ещё нет команд ‒ https://vk.cc/chCfKt")
                return

            content = ctx.content.split(maxsplit=1)
            if not content:
                await ctx.reply("Недостаточно значений ‒ https://vk.cc/chCfMF")
                return

            link_alias = content[0].lstrip(self.bot.prefix).lower()
            link = self.bot.cogs["Links"].get_link_name(ctx.channel.name, link_alias)

            if not link:
                await ctx.reply(f"Команда {self.bot.prefix}{link_alias} не найдена")
                return

        if ctx.command_alias == "timer":
            await self.timer(ctx, link)
        elif ctx.command_alias == "delt":
            await self.delt(ctx, link)
        elif ctx.command_alias == "timers":
            await self.view_timers(ctx)

    async def timer(self, ctx: Context, link: str):
        key = {"channel": ctx.channel.name}
        content = ctx.content.lower().split()
        interval, messages, timer = 0, 0, {}

        for value in content[1:]:
            if value == "online":
                timer["offline"] = False
            elif value == "always":
                timer["offline"] = True
            elif value in ("a", "а"):
                timer["announce"] = True
            elif value == "noa":
                timer["announce"] = False
            elif value == "on":
                timer["active"] = True
            elif value == "off":
                timer["active"] = False
            elif not interval:
                try:
                    interval = int(value)
                    if not 1 <= interval <= 60:
                        await ctx.reply("Допустимый интервал ‒ от 1 до 60 минут")
                        return
                    timer["interval"] = interval
                except ValueError:
                    await ctx.reply("Интервал должен быть числом от 1 до 60 ‒ https://vk.cc/chCfMF")
                    return
            else:
                try:
                    messages = int(value)
                    if not 0 < messages <= 10:
                        await ctx.reply("Допустимое количество сообщений ‒ от 1 до 10")
                        return
                    timer["number"] = messages
                except ValueError:
                    await ctx.reply("Количество сообщений должно быть числом от 1 до 10 ‒ https://vk.cc/chCfMF")
                    return

        if link not in self.timers.get(ctx.channel.name, []) and not interval and not messages:
            await ctx.reply("Не указан интервал (в минутах) или количество сообщений ‒ https://vk.cc/chCfMF")
            return
        elif interval and not messages:
            await ctx.reply("Не указано количество сообщений ‒ https://vk.cc/chCfMF")
            return
        elif interval and interval < 3:
            if messages > 3:
                await ctx.reply("Таймеры с периодом меньше трёх минут могут отправлять не более трёх сообщений")
                return

            timers = 1 + sum(
                bool(t["interval"] < 3 and t.get("active", True) and l != link)
                for l, t in self.timers.get(ctx.channel.name, {}).items()
            )

            if timers > 2:
                await ctx.reply("На канале может быть не более двух активных таймеров с периодом менее трёх минут")
                return
        elif messages > 5:
            timers = 1 + sum(
                bool(t["number"] > 5 and t.get("active", True) and l != link)
                for l, t in self.timers.get(ctx.channel.name, {}).items()
            )

            if timers > 3:
                await ctx.reply(
                    "На канале может быть не более трёх активных таймеров с количеством сообщений больше пяти"
                )
                return

        if link not in self.timers.get(ctx.channel.name, []):
            if len(self.timers.get(ctx.channel.name, {})) == 10:
                await ctx.reply("На канале может быть не более десяти таймеров")
                return

            timers = 1 + sum(bool(t.get("active", True)) for l, t in self.timers.get(ctx.channel.name, {}).items())

            if timers > 5:
                await ctx.reply("На канале может быть не более пяти активных таймеров")
                return
        elif timer.get("active") and self.timers[ctx.channel.name].get(link):
            timers = 0
            current_timer = self.timers[ctx.channel.name][link]
            if current_timer["interval"] < 3:
                if current_timer["number"] > 3:
                    await ctx.reply("Таймеры с периодом меньше трёх минут могут отправлять не более трёх сообщений")
                    return
                if not current_timer.get("active", True):
                    timers = 1
            for l, t in self.timers.get(ctx.channel.name, {}).items():
                if t["interval"] < 3 and t.get("active", True) and l != link:
                    timers += 1
            if timers > 2:
                await ctx.reply("На канале может быть не более двух активных таймеров с периодом менее трёх минут")
                return

            timers = 0
            if current_timer["number"] > 5 and not current_timer.get("active", True):
                timers = 1
            for l, t in self.timers.get(ctx.channel.name, {}).items():
                if t["number"] > 5 and t.get("active", True) and l != link:
                    timers += 1
            if timers > 3:
                await ctx.reply(
                    "На канале может быть не более трёх активных таймеров с количеством сообщений больше пяти"
                )
                return

            timers = 1 + sum(bool(t.get("active", True)) for l, t in self.timers.get(ctx.channel.name, {}).items())

            if timers > 5:
                await ctx.reply("На канале может быть не более пяти активных таймеров")
                return

        if ctx.channel.name not in self.timers:
            self.timers[ctx.channel.name] = {}
            self.messages_from_timer[ctx.channel.name] = 0

        if exist := link in self.timers[ctx.channel.name]:
            key["timers.link"] = link
            values = {"$set": {f"timers.$.{key}": value for key, value in (timer | {"link": link}).items()}}
            self.timers[ctx.channel.name][link] = self.timers[ctx.channel.name][link] | timer | {"cooldown": 0}
            message = f"Изменён таймер {self.bot.prefix}{link}"
        else:
            values = {
                "$setOnInsert": {"channel": ctx.channel.name, "offline": False},
                "$addToSet": {"timers": timer | {"link": link}},
            }
            self.timers[ctx.channel.name][link] = timer | {"cooldown": 0}
            message = f"Добавлен таймер {self.bot.prefix}{link}"
            self.offline[ctx.channel.name] = False

        if exist and "active" in timer:
            if timer["active"]:
                message = f"Включён таймер {self.bot.prefix}{link}"
            else:
                message = f"Выключен таймер {self.bot.prefix}{link}"

        await db.timers.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def delt(self, ctx: Context, link: str):
        del self.timers[ctx.channel.name][link]
        await db.timers.update_one({"channel": ctx.channel.name}, {"$pull": {"timers": {"link": link}}})
        await ctx.reply(f"Удалён таймер {self.bot.prefix}{link}")

    async def view_timers(self, ctx):
        if not self.timers.get(ctx.channel.name):
            message = "На вашем канале ещё нет таймеров"
        elif not ctx.content:
            message = f'Установленные таймеры: {self.bot.prefix}{str(f" {self.bot.prefix}").join(self.timers[ctx.channel.name])}'
        elif ctx.content.lower() == "online":
            await db.timers.update_one({"channel": ctx.channel.name}, {"$set": {"offline": False}})
            message = "Теперь таймеры будут работать только на стриме"
            self.offline[ctx.channel.name] = False
        elif ctx.content.lower() == "always":
            await db.timers.update_one({"channel": ctx.channel.name}, {"$set": {"offline": True}})
            message = "Теперь таймеры будут работать и вне стрима"
            self.offline[ctx.channel.name] = True
        else:
            message = "Неверный ввод ‒ https://vk.cc/chCfMF"

        await ctx.reply(message)

    @routine(seconds=15)
    async def check_timers(self):
        for channel in self.timers:
            timers = list(self.timers[channel])
            shuffle(timers)  # shuffle so that only the first timers are not triggered all the time

            for timer in timers:
                if self.timers[channel][timer].get("active", True):
                    if channel not in self.bot.streams and not self.timers[channel][timer].get(
                        "offline", self.offline[channel]
                    ):
                        continue
                    if (
                        time.time() > self.timers[channel][timer]["cooldown"]
                        and self.messages_from_timer[channel] >= self.timers[channel][timer]["number"] + 7
                    ):
                        Links = self.bot.cogs["Links"]

                        if (
                            self.timers[channel][timer]["number"] > 2
                            and time.time() - Links.mod_cooldowns.get(channel, 0) < 3
                        ):
                            continue
                        elif (
                            self.timers[channel][timer]["number"] < 3
                            and time.time() - Links.cooldowns[channel][timer]["gen"] < 3
                        ):
                            continue

                        data = await db.links.find_one(
                            {"channel": channel, "links.name": timer},
                            {"announce": 1, "links.$": 1},
                        )
                        text = data["links"][0]["text"]
                        announce = ""

                        if self.timers[channel][timer].get("announce"):
                            announce = data["links"][0].get("announce") or data["announce"]

                        messageable = self.bot.get_channel(channel)
                        if not messageable:
                            break

                        cooldown = data["links"][0].get("cooldown", {"gen": 3})["gen"]
                        Links.cooldowns[channel][timer]["gen"] = time.time() + cooldown

                        if self.timers[channel][timer]["number"] > 2:
                            Links.mod_cooldowns[channel] = time.time() + 3
                            cooldown = max(data["links"][0].get("cooldown", {"gen": 5})["gen"], 5)
                            Links.cooldowns[channel][timer]["gen"] = time.time() + cooldown

                        self.timers[channel][timer]["cooldown"] = (
                            time.time() + self.timers[channel][timer]["interval"] * 60
                        )

                        if not (announce or text.startswith("/announce") or text.startswith(".announce")):
                            for _ in range(self.timers[channel][timer]["number"]):
                                await messageable.send(text)
                                await asyncio.sleep(0.1)
                        else:
                            if text.startswith("/me") or text.startswith(".me"):
                                text = text.split(maxsplit=1)[1]
                            await self.bot.announce(
                                messageable,
                                text,
                                announce,
                                self.timers[channel][timer]["number"],
                            )

                        self.messages_from_timer[channel] = 0


def prepare(bot):
    bot.add_cog(Timers(bot))
    bot.loop.run_until_complete(bot.cogs["Timers"].__ainit__())
