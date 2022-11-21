from twitchio.ext.commands import Cog, command, Context


class Ping(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(name="ping", cooldown={"per": 0, "gen": 5}, description="Проверка бота.", flags=["whitelist"])
    async def ping(self, ctx: Context):
        await ctx.reply("Pong.")


def prepare(bot):
    bot.add_cog(Ping(bot))
