from twitchio.ext import commands

from config import db


class Help(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name='help',
        aliases=['commands'],
        cooldown={'per': 3, 'gen': 0},
        description='Эта команда.'
    )
    async def help(self, ctx):
        content = ctx.content.lstrip(self.bot._prefix).lower()
        if not content:
            message = f'Доступные команды - bword, inspect, link, mb, spam, timer  | ' \
                      f'Напишите {self.bot._prefix}help [команда], чтобы узнать описание команды'
            await ctx.reply(message)
            return

        command = self.bot.get_command_name(content.split()[0])
        if not command:
            link = content.split()[0]
            cog = self.bot.get_cog('Link')

            if not (link in cog.links.get(ctx.channel.name, []) or link in cog.links_aliases.get(ctx.channel.name, []).keys()):
                await ctx.reply('Несуществующая команда')
                return
            elif link in cog.links_aliases.get(ctx.channel.name, []):
                link = cog.links_aliases[ctx.channel.name][link]

            data = await db.links.find_one({'channel': ctx.channel.name},
                                           {'links': {'$elemMatch': {'name': link}}, 'private': 1})

            aliases = data['links'][0]['aliases'] if 'aliases' in data['links'][0] else []

            if aliases:
                aliases = f'({self.bot._prefix}{str(", " + self.bot._prefix).join(aliases)})'

            if 'private' in data['links'][0]:
                private = data['links'][0]['private']
            else:
                private = data['private']

            timer = ''
            cog = self.bot.get_cog('Timer')

            if link in cog.timers.get(ctx.channel.name, []):
                offline_raw = await db.timers.find_one({'channel': ctx.channel.name}, {'offline': 1})
                offline = offline_raw['offline']
                timer = cog.timers[ctx.channel.name][link]
                timer = f'Установлен {"активный" if timer.get("active", True) else "неактивный"} таймер: {timer["number"]} сообщений раз в {timer["interval"]}м' \
                        f'{", с announce" if timer.get("announce", False) in timer else ""}' \
                        f'{"." if timer.get("offline", offline) else ", только на стриме."}'

            message = f'{self.bot._prefix}{link}{"." if not aliases else " " + aliases + "."} ' \
                      f'Доступ: {"приватный" if private else "публичный"}. ' \
                      f'Кд 3с. {timer}'
        else:
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
