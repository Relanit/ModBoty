import asyncio

from twitchio.ext.routines import routine
from twitchio.ext.commands import Cog, command, Context
from twitchio import Message

from config import db, config

reason = "Сообщение, содержащее запрещённую фразу (от ModBoty)"


def truncate(content: str, length: int = 450, suffix: str = "..."):
    if len(content) <= length:
        return content, ""
    else:
        return (
            content[:length].rsplit(" | ", 1)[0] + suffix,
            content[:length].rsplit(" | ", 1)[1] + content[length:],
        )


class Banwords(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.banwords: dict[str, list[str]] = {}
        self.mutewords: dict[str, list[dict[str, str | int]]] = {}

        self.get_banwords.start(stop_on_error=False)

    @Cog.event()
    async def event_message(self, message: Message):
        if message.echo:
            return

        if message.channel.name == "t2x2" and message.tags["first-msg"] == "1" and "бум" in message.content.lower():
            await message.channel.send(f"/timeout {message.author.name} 600 {reason}")

        if message.channel.name in self.banwords:
            content = message.content.lower()
            for banword in self.banwords[message.channel.name]:
                if banword in content:
                    await message.channel.send(f"/ban {message.author.name} {reason}")
                    return
        if message.channel.name in self.mutewords:
            content = message.content.lower()
            timeout = 0
            for muteword in self.mutewords[message.channel.name]:
                if muteword["muteword"] in content and muteword["timeout"] > timeout:
                    timeout = muteword["timeout"]
            if timeout:
                await message.channel.send(f"/timeout {message.author.name} {timeout} {reason}")

    @command(
        name="bword",
        aliases=["mword", "delb", "delm", "bwords", "mwords"],
        cooldown={"per": 0, "gen": 3},
        description="Запрещённые слова, за отправку которых пользователь получает бан/мут. Полное описание - https://vk.cc/chCfIC ",
        flags=["bot-mod"],
    )
    async def command(self, ctx: Context):
        if not ctx.content and ctx.command_alias not in ("bwords", "mwords"):
            await ctx.reply("Недостаточно значений - https://vk.cc/chCfIC")
            return

        if ctx.command_alias == "bword":
            await self.bword(ctx)
        elif ctx.command_alias == "delb":
            await self.delb(ctx)
        elif ctx.command_alias == "mword":
            await self.mword(ctx)
        elif ctx.command_alias == "delm":
            await self.delm(ctx)
        elif ctx.command_alias == "bwords":
            await self.bwords(ctx)
        else:
            await self.mwords(ctx)

    async def bword(self, ctx: Context):
        if len(self.banwords.get(ctx.channel.name, [])) + len(self.mutewords.get(ctx.channel.name, [])) == 50:
            await ctx.reply("Достигнут лимит банвордов и мутвордов - 50")
            return

        banword = ctx.content.lower()

        if banword in self.banwords.get(ctx.channel.name, []):
            await ctx.reply("Банворд уже добавлен")
            return

        for word in self.banwords.get(ctx.channel.name, []):
            if word in banword:
                await ctx.reply("Часть фразы уже есть в банвордах канала")
                return

        if len(banword) > 20:
            await ctx.reply("Длина банворда не должна превышать 20 символов")
            return

        if ctx.channel.name not in self.banwords:
            self.banwords[ctx.channel.name] = []

        self.banwords[ctx.channel.name].append(banword)
        await db.banwords.update_one(
            {"channel": ctx.channel.name},
            {
                "$setOnInsert": {"channel": ctx.channel.name},
                "$addToSet": {"banwords": banword},
            },
            upsert=True,
        )
        await ctx.reply("Добавлено")

    async def delb(self, ctx: Context):
        banword = ctx.content.lower()

        if banword not in self.banwords.get(ctx.channel.name, []):
            await ctx.reply("Банворд не найден")
            return

        self.banwords[ctx.channel.name].remove(banword)
        await db.banwords.update_one({"channel": ctx.channel.name}, {"$pull": {"banwords": banword}})
        await ctx.reply("Удалено")

    async def mword(self, ctx: Context):
        content = ctx.content.split()
        if len(content) < 2:
            await ctx.reply("Укажите время мута в секундах и фразу")
            return

        muteword = " ".join(content[1:]).lower()

        found = False
        for item in self.mutewords.get(ctx.channel.name, []):
            if item["muteword"] == muteword:
                found = item
                break
            elif item["muteword"] in muteword:
                await ctx.reply("Часть фразы уже есть в списке мутвордов канала")
                return

        if (
            len(self.banwords.get(ctx.channel.name, [])) + len(self.mutewords.get(ctx.channel.name, [])) == 50
            and not found
        ):
            await ctx.reply("Достигнут лимит банвордов и мутвордов - 50")
            return

        try:
            timeout = int(content[0])
        except ValueError:
            await ctx.reply("Укажите время мута в секундах")
            return

        if not 1 <= timeout <= 1209600:
            await ctx.reply("Допустимая длительность мута от 1 до 1209600 секунд")
            return

        if len(muteword) > 20:
            await ctx.reply("Длина мутворда не должна превышать 20 символов")
            return

        message = "Добавлено"
        if found:
            await db.banwords.update_one(
                {"channel": ctx.channel.name, "mutewords.muteword": muteword},
                {"$set": {"mutewords.$.timeout": timeout}},
            )
            self.mutewords[ctx.channel.name].remove(found)
            message = "Изменено"
        else:
            if ctx.channel.name not in self.mutewords:
                self.mutewords[ctx.channel.name] = []

            await db.banwords.update_one(
                {"channel": ctx.channel.name},
                {
                    "$setOnInsert": {"channel": ctx.channel.name},
                    "$push": {"mutewords": {"timeout": timeout, "muteword": muteword}},
                },
                upsert=True,
            )
        self.mutewords[ctx.channel.name].append({"muteword": muteword, "timeout": timeout})
        await ctx.reply(message)

    async def delm(self, ctx: Context):
        muteword = ctx.content.lower()

        found = False
        for item in self.mutewords.get(ctx.channel.name, []):
            if item["muteword"] == muteword:
                found = True
                self.mutewords[ctx.channel.name].remove(item)
                break

        if not found:
            await ctx.reply("Мутворд не найден")
            return

        await db.banwords.update_one(
            {"channel": ctx.channel.name},
            {"$pull": {"mutewords": {"muteword": muteword}}},
        )
        await ctx.reply("Удалено")

    async def bwords(self, ctx: Context):
        if not self.banwords.get(ctx.channel.name):
            await ctx.reply("На вашем канале ещё нет банвордов")
        else:
            message, message2 = truncate(
                f"Банворды канала {ctx.channel.name}: " + " | ".join(self.banwords[ctx.channel.name])
            )

            if config["Bot"]["refresh_token"]:
                user = await ctx.author.user()
                await user.send_whisper(
                    token=config["Bot"]["access_token"],
                    from_user_id=self.bot.user_id,
                    to_user_id=user.id,
                    message=message,
                )
                if message2:
                    await asyncio.sleep(1)
                    await user.send_whisper(
                        token=config["Bot"]["access_token"],
                        from_user_id=self.bot.user_id,
                        to_user_id=user.id,
                        message=message2,
                    )
                await ctx.reply("Список банвордов отправлен в личные сообщения")
            else:
                await ctx.reply(message)
                if message2:
                    await ctx.reply(message2)

    async def mwords(self, ctx: Context):
        if not self.mutewords.get(ctx.channel.name):
            await ctx.reply("На вашем канале ещё нет мутвордов")
        else:
            message, message2 = truncate(
                f"Мутворды канала {ctx.channel.name}: "
                + " | ".join(
                    [
                        muteword["muteword"] + " " + str(muteword["timeout"])
                        for muteword in self.mutewords[ctx.channel.name]
                    ]
                )
            )

            if config["Bot"]["refresh_token"]:
                user = await ctx.author.user()
                await user.send_whisper(
                    token=config["Bot"]["access_token"],
                    from_user_id=self.bot.user_id,
                    to_user_id=user.id,
                    message=message,
                )
                if message2:
                    await asyncio.sleep(1)
                    await user.send_whisper(
                        token=config["Bot"]["access_token"],
                        from_user_id=self.bot.user_id,
                        to_user_id=user.id,
                        message=message2,
                    )
                await ctx.reply("Список мутвордов отправлен в личные сообщения")
            else:
                await ctx.reply(message)
                if message2:
                    await ctx.reply(message2)

    @routine(iterations=1)
    async def get_banwords(self):
        async for document in db.banwords.find():
            if "banwords" in document:
                self.banwords[document["channel"]] = document["banwords"]
            if "mutewords" in document:
                self.mutewords[document["channel"]] = document["mutewords"]


def prepare(bot):
    bot.add_cog(Banwords(bot))
