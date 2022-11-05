from twitchio.ext import commands


class Ping(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="ping", cooldown={"per": 0, "gen": 5}, description="Проверка бота.", flags=["whitelist"])
    async def ping(self, ctx: commands.Context):
        await ctx.reply("Pong.")


def prepare(bot: commands.Bot):
    bot.add_cog(Ping(bot))
