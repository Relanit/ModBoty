from twitchio.ext.commands import Cog, command, Context


class Debug(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(name="debug", flags=["admin"])
    async def debug(self, ctx: Context):
        try:
            ctx.content = ctx.content.replace("\\n", "\n")
            if "await" in ctx.content or "\n" in ctx.content:
                exec(("async def __ex(self, ctx): " + "".join(f"\n {l}" for l in ctx.content.split("\n"))))
                result = await locals()["__ex"](self, ctx)
            else:
                result = eval(ctx.content)
        except Exception as e:
            result = repr(e)
        await ctx.reply(result)


def prepare(bot):
    bot.add_cog(Debug(bot))
