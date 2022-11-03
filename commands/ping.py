from twitchio.ext import commands


class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping", cooldown={"per": 0, "gen": 5}, description="Проверка бота.")
    async def ping(self, ctx):
        await ctx.reply("Pong.")


def prepare(bot):
    bot.add_cog(Ping(bot))
