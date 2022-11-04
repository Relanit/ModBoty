import os

from twitchio.ext import commands

from config import db


class JoinChannel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="mjoin", aliases=["mpart"], flags=["admin"])
    async def join_channel(self, ctx: commands.Context):
        channel = ctx.content.lower()
        if ctx.command_alias == "mjoin":
            user = await self.bot.fetch_users(names=[channel])
            if not user:
                await ctx.reply("❌ Несуществующий логин")
                return
            elif channel in os.environ["CHANNELS"]:
                await ctx.reply("❌ Уже добавлен")
                return

            self.bot.cooldowns[channel] = {}
            cog = self.bot.get_cog("MassBan")
            cog.message_history[channel] = []
            await db.config.update_one({"_id": 1}, {"$addToSet": {"channels": channel}})
            await self.bot.join_channels([channel])
            os.environ["CHANNELS"] = os.environ["CHANNELS"] + "&" + channel
            await ctx.reply("✅ Добавлен")
        else:
            if not channel:
                channel = ctx.channel.name
            else:
                data = await db.channels.find_one({"_id": 1})
                channels = data["channels"]
                if channel not in channels:
                    await ctx.reply("❌ Канал не подключён")
                    return

            self.bot.cooldowns.pop(channel)
            cog = self.bot.get_cog("MassBan")
            cog.message_history.pop(channel)
            await db.config.update_one({"_id": 1}, {"$pull": {"channels": channel}})
            await self.bot.part_channels([channel])
            channels = os.environ["CHANNELS"].split("&")
            channels.remove(channel)
            os.environ["CHANNELS"] = "&".join(channels)
            await ctx.reply("✅ Удалён")


def prepare(bot: commands.Bot):
    bot.add_cog(JoinChannel(bot))
