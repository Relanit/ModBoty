import asyncio

from twitchio.ext import commands


class Mail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mail", flags=["admin"])
    async def mail(self, ctx):
        if not ctx.content.lstrip("/announce"):
            await ctx.reply("Укажите текст")
            return

        await ctx.reply("Рассылка начата")

        announce = bool(ctx.content.startswith("/announce") or ctx.content.startswith(".announce"))

        for channel in self.bot.connected_channels:
            while channel.limited:
                await asyncio.sleep(0.1)
            if announce:
                if channel.bot_is_mod:
                    await self.bot.announce(channel, ctx.content)
                else:
                    await channel.send(ctx.content.split(maxsplit=1)[1])
            else:
                await channel.send(ctx.content)
            await asyncio.sleep(3)

        await ctx.reply("Рассылка закончена")


def prepare(bot):
    bot.add_cog(Mail(bot))
