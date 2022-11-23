import asyncio

from twitchio.ext.commands import Cog, command, Context


class Spam(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(
        name="spam",
        cooldown={"per": 0, "gen": 10},
        description="Спам текстом указанное количество раз (до 15).",
        flags=["bot-vip"],
    )
    async def send(self, ctx: Context):
        content_split = ctx.content.split()
        if not content_split:
            await ctx.reply("Введите текст")
            return

        try:
            num = min(int(content_split[0]), 15)
            if len(content_split) < 2:
                await ctx.reply("Введите текст")
                return
            message = " ".join(content_split[1:])
        except ValueError:
            num = 1
            message = " ".join(content_split)

        if not (message.startswith("/a") or message.startswith(".a")):
            for _ in range(num):
                await ctx.send(message)
                await asyncio.sleep(0.1)
        elif ctx.channel.bot_is_mod:
            await self.bot.announce(ctx.channel, message, number=num)
        else:
            await ctx.send("Боту необходима модерка для работы announce")


def prepare(bot):
    bot.add_cog(Spam(bot))
