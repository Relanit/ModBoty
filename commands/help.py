from twitchio.ext import commands

from config import db


class Help(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name='help',
        aliases=['commands'],
        cooldown={'per': 5, 'gen': 0},
        description='Эта команда.'
    )
    async def help(self, ctx):
        content = ctx.content.lstrip(self.bot._prefix).lower()
        if not content:
            message = f'Доступные команды - https://pastebin.com/wTD5z2AQ | ' \
                      f'Напишите {self.bot._prefix}help [команда], чтобы узнать описание команды'
            await ctx.reply(message)
            return

        command = self.bot.get_command_name(content.split()[0])
        if not command:
            await ctx.reply('Несуществующая команда')
            return

        data = self.bot.get_command(command)
        if 'admin' in data.flags:
            await ctx.reply('Несуществующая команда')
            return

        aliases = ''
        if data.aliases:
            aliases = f'({self.bot._prefix}{str(", " + self.bot._prefix).join(data.aliases)})'

        per = data.cooldown['per']
        gen = data.cooldown['gen']
        if per and gen:
            cooldown = f'личный {per}с, общий {gen}с.'
        elif per:
            cooldown = f'личный {per}с.'
        else:
            cooldown = f'общий {gen}с.'

        message = f'{self.bot._prefix}{command}{":" if not aliases else " " + aliases + ":"} ' \
                  f'{data.description.format(prefix=self.bot._prefix)} ' \
                  f'Кд: {cooldown}'

        await ctx.reply(message)


def prepare(bot):
    bot.add_cog(Help(bot))
