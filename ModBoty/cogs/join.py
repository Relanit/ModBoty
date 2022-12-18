import twitchio
from twitchio.ext.commands import Cog, command, Context

from config import db, config


class JoinChannel(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(name="join", aliases=["part"], flags=["admin"])
    async def join_channel(self, ctx: Context):
        channel = ctx.content.lstrip("@").rstrip(",").lower()
        if ctx.command_alias == "join":
            try:
                user = await self.bot.fetch_users(names=[channel])
            except twitchio.HTTPException:
                await ctx.reply("Некорректный никнейм")
                return

            if not user:
                await ctx.reply("Канал не найден")
                return
            elif channel in config["Bot"]["channels"]:
                await ctx.reply("Канал уже подключён")
                return

            self.bot.cooldowns[channel] = {}
            cog = self.bot.get_cog("MassBan")
            cog.message_history[channel] = []
            await db.config.update_one({"_id": 1}, {"$addToSet": {"channels": channel}})
            await self.bot.join_channels([channel])
            config["Bot"]["channels"] = config["Bot"]["channels"] + " " + channel
            await ctx.reply("Добавлен")
        else:
            if not channel:
                channel = ctx.channel.name
            else:
                data = await db.channels.find_one({"_id": 1})
                channels = data["channels"]
                if channel not in channels:
                    await ctx.reply("Канал не подключён")
                    return

            self.bot.cooldowns.pop(channel)
            cog = self.bot.get_cog("MassBan")
            cog.message_history.pop(channel)
            await db.config.update_one({"_id": 1}, {"$pull": {"channels": channel}})
            await self.bot.part_channels([channel])
            channels = config["Bot"]["channels"].split()
            channels.remove(channel)
            config["Bot"]["channels"] = " ".join(channels)
            await ctx.reply("Удалён")


def prepare(bot):
    bot.add_cog(JoinChannel(bot))
