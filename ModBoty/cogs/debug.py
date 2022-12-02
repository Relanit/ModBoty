from twitchio import Message
from twitchio.ext.commands import Cog, command, Context


class Debug(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.event()
    async def event_message(self, message: Message):
        if message.echo:
            return

        if message.content.startswith(self.bot.prefix) and message.author.name == self.bot.admin:
            content = message.content.lstrip(self.bot.prefix)
            if not content:
                return

            alias = content.split(maxsplit=1)[0].lower()
            if alias == "mesdebug":
                await self.debug(message)

    @command(name="debug", flags=["admin"])
    async def command(self, ctx: Context):
        await self.debug(ctx.message)

    async def debug(self, message: Message):
        try:
            content = message.content.lstrip(self.bot.prefix).split(maxsplit=1)[1].replace("\\n", "\n")
            if "await" in content or "\n" in content:
                exec(("async def __ex(self, message): " + "".join(f"\n {l}" for l in content.split("\n"))))
                result = await locals()["__ex"](self, message)
            else:
                result = eval(content)
        except Exception as e:
            result = repr(e)
        await message.channel.send(f"@{message.author.name} {result}")


def prepare(bot):
    bot.add_cog(Debug(bot))
