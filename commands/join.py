from twitchio.ext import commands

from config import db


class JoinChannel(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name='mjoin',
        aliases=['mpart'],
        flags=['admin']
    )
    async def join_channel(self, ctx):
        channel = ctx.content.lower()
        if ctx.command_alias == 'mjoin':
            user = await self.bot.fetch_users(names=[channel])
            if not user:
                await ctx.reply('❌ Несуществующий логин')
                return

            self.bot.cooldowns[channel] = {}
            cog = self.bot.get_cog('MassBan')
            cog.message_history[channel] = []
            await db.channels.update_one({'_id': 1}, {'$addToSet': {'channels': channel}})
            await self.bot.join_channels([channel])
            await ctx.reply('✅ Добавлен')
        else:
            if not channel:
                channel = ctx.channel.name
            else:
                data = await db.channels.find_one({'_id': 1})
                channels = data['channels']
                if channel not in channels:
                    await ctx.reply('❌ Канал не подключён')
                    return

            self.bot.cooldowns.pop(channel)
            cog = self.bot.get_cog('MassBan')
            cog.message_history.pop(channel)
            await db.channels.update_one({'_id': 1}, {'$pull': {'channels': channel}})
            await self.bot.part_channels([channel])
            await ctx.reply('✅ Удалён')


def prepare(bot):
    bot.add_cog(JoinChannel(bot))
