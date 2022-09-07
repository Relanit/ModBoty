import asyncio

from twitchio.ext import commands


class Mail(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name='mail',
        flags=['admin']
    )
    async def mail(self, ctx):
        if not ctx.content.lstrip('/announce'):
            await ctx.reply('Укажите текст')
            return

        await ctx.reply('Рассылка начата')

        announce = True if ctx.content.startswith('/announce') else False

        for channel in self.bot.connected_channels:
            if channel.name != ctx.channel.name:
                if announce:
                    if channel.bot_is_mod:
                        while channel.limited:
                            await asyncio.sleep(0.1)
                        await channel.send(ctx.content)
                    else:
                        while channel.limited:
                            await asyncio.sleep(0.1)
                        await channel.send(ctx.content.split(maxsplit=1)[1])
                else:
                    while channel.limited:
                        await asyncio.sleep(0.1)
                    await channel.send(ctx.content)
                await asyncio.sleep(3)

        await ctx.reply('Рассылка закончена')


def prepare(bot):
    bot.add_cog(Mail(bot))
