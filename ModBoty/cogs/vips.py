import time
from datetime import datetime

import twitchio
from pytz import timezone
from twitchio import BroadcasterTypeEnum, User
from twitchio.ext.commands import Cog, command, Context
from twitchio.ext.routines import routine
from pytimeparse2 import parse
import parsedatetime

from config import db, fernet

intervals = (
    ("y", 31536000),
    ("mo", 2592000),
    ("w", 604800),
    ("d", 86400),
    ("h", 3600),
    ("m", 60),
    ("s", 1),
)


def display_time(seconds: int, granularity: int = 2) -> str:
    """Returns human-readable time from number of seconds"""
    result = []

    for name, count in intervals:
        if value := seconds // count:
            seconds -= value * count
            result.append(f"{value}{name}")
    return ", ".join(result[:granularity])


class Vips(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_unvips.start(stop_on_error=False)

    @command(
        name="vip",
        aliases=["unvip", "unvips", "delunvip"],
        cooldown={"per": 0, "gen": 3},
        description="Управление випами на канале. Полное описание - https://vk.cc/ciufvM",
        flags=["editor"],
    )
    async def command(self, ctx: Context):
        if ctx.command_alias not in ("unvips", "delunvip"):
            channel = await ctx.channel.user()
            if channel.broadcaster_type == BroadcasterTypeEnum.none:
                await ctx.reply("Эта команда доступна только компаньонам и партнёрам твича")
                return

            data = await db.config.find_one({"_id": 1, "user_tokens.login": ctx.channel.name}, {"user_tokens.$": 1})
            if not data:
                await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
                return

            if not ctx.content:
                await ctx.reply("Недостаточно значений - https://vk.cc/ciufvM")
                return

            token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()

            login = ctx.content.split()[0].lstrip("@").lower()
            try:
                user = await self.bot.fetch_users(names=[login])
            except twitchio.HTTPException:
                await ctx.reply("Некорректный никнейм")
                return

            if not user:
                await ctx.reply(f"Пользователь {login} не найден")
                return

            try:
                vip = await channel.fetch_channel_vips(token, user_ids=[user[0].id])
            except twitchio.errors.Unauthorized:
                await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
                return

            if ctx.command_alias == "vip":
                if vip:
                    await ctx.reply(f"{login} уже VIP")
                    return

                mod = await channel.fetch_moderators(token, userids=[user[0].id])
                if mod:
                    await ctx.reply(f"{login} уже модератор")
                    return
                await self.vip(ctx, channel, token, user[0].id)
            else:
                if not vip:
                    await ctx.reply(f"{login} не VIP")
                    return

                await self.unvip(ctx, channel, token, user[0].id)
        elif ctx.command_alias == "unvips":
            await self.unvips(ctx)
        else:
            await self.delunvip(ctx)

    @staticmethod
    async def vip(ctx: Context, channel: User, token: str, user_id: int):
        try:
            await channel.add_channel_vip(token, user_id)
        except twitchio.errors.HTTPException:
            await ctx.reply("Произошла непонятная ошибка (создатель бота не причём) :|")
            return

        await ctx.reply(f"Добавлен VIP: {ctx.content.lstrip('@')}")

    async def unvip(self, ctx: Context, channel: User, token: str, user_id: int):
        content = ctx.content.lower().split(maxsplit=1)
        login = content[0].lstrip("@")
        if len(content) == 1:
            await channel.remove_channel_vip(token, user_id)
            await db.unvips.update_one(
                {"channel": ctx.channel.name},
                {"$pull": {"unvips": {"user_id": user_id}}},
            )
            await ctx.reply(f"Удалён VIP: {login}")
            return

        pipeline = [
            {"$match": {"channel": ctx.channel.name}},
            {
                "$project": {
                    "unvips_count": {"$size": "$unvips"},
                }
            },
        ]
        unvips_count = None
        async for data in db.unvips.aggregate(pipeline):
            unvips_count = data

        unvips_count = 0 if unvips_count is None else unvips_count["unvips_count"]
        if unvips_count >= 20:
            await ctx.reply("На канале может быть не больше 20 отложенных анвипов")
            return

        if offline := content[1].endswith("offline"):
            content[1] = content[1].rstrip(" offline")

        if content[1].startswith("in"):
            t = content[1].split(maxsplit=1)[1]
            t = parse(t)
            if t is None:
                await ctx.reply("Укажите время, через которое произойдёт анвип - https://vk.cc/ciVsiG")
                return
            if t < 60:
                await ctx.reply("Нельзя указывать прошедшую дату или близкое будущее (до минуты)")
                return
            elif t >= 315360000:
                await ctx.reply(f"{login} будет обязательно анвипнут. Но это не точно")
                return

            unvip_time = time.time() + t
            date = datetime.fromtimestamp(unvip_time, timezone("Europe/Moscow"))
            message = f'{login} будет анвипнут {date:%Y.%m.%d %H:%M} по МСК{", вне стрима" if offline else ""}'
        elif content[1].startswith("on"):
            date = content[1].split(maxsplit=1)[1]
            cal = parsedatetime.Calendar()
            date, _ = cal.parseDT(date, tzinfo=timezone("Europe/Moscow"))
            now, _ = cal.parseDT("", tzinfo=timezone("Europe/Moscow"))
            diff = date - now
            if diff.total_seconds() < 60:
                await ctx.reply("Нельзя указывать прошедшую дату или близкое будущее (до минуты)")
                return
            elif diff.total_seconds() >= 315360000:
                await ctx.reply(f"{login} будет обязательно анвипнут. Но это не точно")
                return

            unvip_time = date.timestamp()
            message = f'{login} будет анвипнут {date:%Y.%m.%d %H:%M} по МСК{", вне стрима" if offline else ""}'
        elif not content[1] and offline:
            if ctx.channel.name not in self.bot.streams:
                await ctx.reply("Сейчас нет стрима")
                return

            unvip_time = time.time()
            message = f"{login} будет анвипнут после окончания стрима"
        else:
            await ctx.reply("Неверный ввод - https://vk.cc/ciVsiG")
            return

        found = await db.unvips.find_one({"channel": ctx.channel.name, "unvips.user_id": user_id}, {"unvips.$": 1})
        if not found:
            await db.unvips.update_one(
                {"channel": ctx.channel.name},
                {
                    "$setOnInsert": {"channel": ctx.channel.name},
                    "$addToSet": {
                        "unvips": {"user_id": user_id, "login": login, "unvip_time": unvip_time, "offline": offline}
                    },
                },
                upsert=True,
            )
        else:
            await db.unvips.update_one(
                {"channel": ctx.channel.name, "unvips.user_id": user_id},
                {
                    "$set": {
                        "unvips.$": {"user_id": user_id, "login": login, "unvip_time": unvip_time, "offline": offline}
                    },
                },
            )
        await ctx.reply(message)

    async def unvips(self, ctx: Context):
        unvips = await db.unvips.find_one({"channel": ctx.channel.name})
        if not ctx.content:
            unvips = [vip["login"] for vip in unvips.get("unvips", [])]

            if not unvips:
                await ctx.reply("На вашем канале нет отложенных анвипов")
                return

            await ctx.reply(f"Отложенные анвипы: {', '.join(unvips)}")
        else:
            login = ctx.content.lower().lstrip("@")
            unvip = [vip for vip in unvips.get("unvips", []) if vip["login"] == login]
            if not unvip:
                await ctx.reply(f"Анвип {login} не найден")
                return

            if time.time() > unvip[0]["unvip_time"]:
                if unvip[0]["offline"] and ctx.channel.name in self.bot.streams:
                    await ctx.reply(f"{login} будет анвипнут после окончания стрима")
                else:
                    await ctx.reply(f"{login} будет анвипнут в ближайшее время")
                return

            date = datetime.fromtimestamp(unvip[0]["unvip_time"], timezone("Europe/Moscow"))
            await ctx.reply(
                f"Дата анвипа {login}: {date:%Y.%m.%d %H:%M} по МСК{', вне стрима' if unvip[0]['offline'] else ''}"
            )

    @staticmethod
    async def delunvip(ctx: Context):
        login = ctx.content.lower()
        found = await db.unvips.find_one({"channel": ctx.channel.name, "unvips.login": login}, {"unvips.$": 1})
        if found:
            await db.unvips.update_one(
                {"channel": ctx.channel.name},
                {"$pull": {"unvips": {"login": login}}},
            )
            await ctx.reply(f"Анвип {login} отменён")
        else:
            await ctx.reply(f"Анвип {login} не найден")

    @routine(minutes=1.0)
    async def check_unvips(self):
        tokens = None
        async for document in db.unvips.find():
            messageable = channel = token = vips = None
            unvips = {}
            already_unvipped = []
            for unvip in document["unvips"]:
                if unvip["unvip_time"] < time.time() and (
                    (unvip["offline"] and document["channel"] not in self.bot.streams) or not unvip["offline"]
                ):
                    if not messageable:
                        if not tokens:
                            data = await db.config.find_one({"_id": 1})
                            tokens = {user["login"]: user["access_token"] for user in data["user_tokens"]}

                        if document["channel"] not in tokens:
                            break

                        token = fernet.decrypt(tokens[document["channel"]].encode()).decode()

                        messageable = self.bot.get_channel(document["channel"])
                        try:
                            channel = await messageable.user()
                        except AttributeError:
                            break

                        try:
                            vips = await channel.fetch_channel_vips(token, first=100)
                            vips = [vip.id for vip in vips]
                        except twitchio.errors.Unauthorized:
                            break

                    if unvip["user_id"] in vips:
                        unvips[unvip["user_id"]] = unvip["login"]
                        await channel.remove_channel_vip(token, unvip["user_id"])
                    else:
                        already_unvipped.append(unvip["user_id"])

            if unvips or already_unvipped:
                await db.unvips.update_one(
                    {"channel": document["channel"]},
                    {"$pull": {"unvips": {"user_id": {"$in": list(unvips.keys()) + already_unvipped}}}},
                )
            if unvips:
                await messageable.send(
                    f"Анвипнут{'ы' if len(unvips.values()) > 1 else ''}: {', '.join(unvips.values())}"
                )


def prepare(bot):
    bot.add_cog(Vips(bot))
