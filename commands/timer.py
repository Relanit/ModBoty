import asyncio
import time
from random import shuffle

from twitchio.ext import commands, routines

from config import db


class Timer(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.timers = {}
        self.offline = {}
        self.messages_from_timer = {}
        self.get_timers.start(stop_on_error=False)
        self.check_timers.start(stop_on_error=False)

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo or message.channel.name not in self.timers:
            return

        self.messages_from_timer[message.channel.name] += 1

    @commands.command(
        name='timer',
        aliases=['delt', 'timers'],
        cooldown={'per': 0, 'gen': 5},
        description='Автоматическая отправка ссылок с определённым интервалом. Полное описание: https://i.imgur.com/hq2H3Qv.png '
    )
    async def timer(self, ctx):
        if not (ctx.channel.bot_is_vip or ctx.channel.bot_is_mod):
            await ctx.reply('Боту необходима випка или модерка для работы этой команды')
            return

        if not ctx.command_alias == 'timers':
            content = ctx.content.split(maxsplit=1)
            if not content:
                await ctx.reply('Неверный ввод')
                return

            link = content[0].lstrip(self.bot._prefix)
            cog = self.bot.get_cog('Link')

            if link in cog.links.get(ctx.channel.name, []):
                pass
            elif link in cog.links_aliases.get(ctx.channel.name, []):
                link = cog.links_aliases[ctx.channel.name][link]
            else:
                await ctx.reply('Ссылка не найдена')
                return

        if ctx.command_alias == 'timer':
            await self.edit(ctx, link)
        elif ctx.command_alias == 'delt':
            await self.delt(ctx, link)
        elif ctx.command_alias == 'timers':
            await self.list_timers(ctx)

    async def edit(self, ctx, link):
        key = {'channel': ctx.channel.name}
        content = ctx.content.lower().split()
        interval = 0
        number = 0
        timer = {}

        for value in content[1:]:
            if value == 'online':
                timer['offline'] = False
            elif value == 'always':
                timer['offline'] = True
            elif value == 'a' or value == 'а':
                timer['announce'] = True
            elif value == 'noa':
                timer['announce'] = False
            elif 'on' in value:
                timer['active'] = True
            elif 'off' in value:
                timer['active'] = False
            elif not interval:
                try:
                    interval = int(value)
                    if not 1 <= interval <= 60:
                        await ctx.reply('Допустимый интервал - от 1 до 60 минут')
                        return
                    timer['interval'] = interval
                except ValueError:
                    await ctx.reply('Ошибка ввода')
                    return
            else:
                try:
                    number = int(value)
                    if not 0 < number <= 10:
                        await ctx.reply('Допустимое количество сообщений - от 1 до 10')
                        return
                    timer['number'] = number
                except ValueError:
                    await ctx.reply('Ошибка ввода')
                    return

        if link not in self.timers.get(ctx.channel.name, []) and not (interval or number):
            await ctx.reply('Не указан интервал (в минутах) или количество сообщений')
            return
        elif interval and not number:
            await ctx.reply('Не указано количество сообщений')
            return
        elif interval < 5:
            if number > 3:
                await ctx.reply('Таймеры с периодом меньше 5 минут могут отправлять не больше трёх сообщений')
                return

            num = 0
            for l, t in self.timers.get(ctx.channel.name, {}).items():
                if t['interval'] < 5 and t.get('active', True) and l != link:
                    num += 1
                if num == 2:
                    await ctx.reply('На канале может быть не более двух активных таймеров с периодом менее 5 минут')
                    return

        if timer.get('active') and self.timers[ctx.channel.name].get(link):
            num = 0
            t = self.timers[ctx.channel.name][link]
            if t['interval'] < 5 and t['number'] > 3:
                await ctx.reply('Таймеры с периодом меньше 5 минут могут отправлять не больше трёх сообщений')
                return
            if t['interval'] < 5 and not t.get('active', True):
                num = 1
            for l, t in self.timers.get(ctx.channel.name, {}).items():
                if t['interval'] < 5 and t.get('active', True) and l != link:
                    num += 1
                if num == 3:
                    await ctx.reply('На канале может быть не более двух активных таймеров с периодом менее 5 минут')
                    return

        if ctx.channel.name not in self.timers:
            self.timers[ctx.channel.name] = {}
            self.messages_from_timer[ctx.channel.name] = 0

        if link in self.timers[ctx.channel.name]:
            key['timers.link'] = link
            values = {'$set': {f'timers.$.{key}': value for key, value in (timer | {'link': link}).items()}}
            self.timers[ctx.channel.name][link] = self.timers[ctx.channel.name][link] | timer | {'cooldown': 0}
            message = f'Изменён таймер {self.bot._prefix}{link}'
        else:
            values = {'$setOnInsert': {'channel': ctx.channel.name, 'offline': False}, '$addToSet': {'timers': timer | {'link': link}}}
            self.timers[ctx.channel.name][link] = timer | {'cooldown': 0}
            message = f'Добавлен таймер {self.bot._prefix}{link}'
            self.offline[ctx.channel.name] = False

        await db.timers.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def delt(self, ctx, link):
        del self.timers[ctx.channel.name][link]
        await db.timers.update_one({'channel': ctx.channel.name}, {'$pull': {'timers': {'link': link}}})
        await ctx.reply(f'Удалён таймер {self.bot._prefix}{link}')

    async def list_timers(self, ctx):
        if self.timers.get(ctx.channel.name) and not ctx.content:
            message = f'Установленные таймеры: {self.bot._prefix}{str(" " + self.bot._prefix).join(self.timers[ctx.channel.name])}'
        elif not self.timers.get(ctx.channel.name):
            message = 'На вашем канале ещё нет таймеров'
        elif ctx.content.lower() == 'online':
            await db.timers.update_one({'channel': ctx.channel.name}, {'$set': {'offline': False}})
            message = 'Теперь таймеры будут работать только на стриме'
            self.offline[ctx.channel.name] = False
        elif ctx.content.lower() == 'always':
            await db.timers.update_one({'channel': ctx.channel.name}, {'$set': {'offline': True}})
            message = 'Теперь таймеры будут работать и вне стрима'
            self.offline[ctx.channel.name] = True
        else:
            message = 'Неверный ввод'
        await ctx.reply(message)

    @routines.routine(seconds=10, iterations=0)
    async def check_timers(self):
        for channel in self.timers:
            timers = list(self.timers[channel])
            shuffle(timers)

            for timer in timers:
                if self.timers[channel][timer].get('active', True):
                    if channel not in self.bot.streams and not self.timers[channel][timer].get('offline', self.offline[channel]):
                        return
                    if time.time() > self.timers[channel][timer]['cooldown'] and self.messages_from_timer[channel] >= 5:
                        data = await db.links.find_one({'channel': channel, 'links.name': timer}, {'links.$': 1})
                        text = data['links'][0]['text']

                        if self.timers[channel][timer].get('announce', False):
                            text = f'/announce {text.split(maxsplit=1)[1]}' if 'announce' in text else f'/announce {text}'

                        cog = self.bot.get_cog('Link')
                        messageable = self.bot.get_channel(channel)

                        for i in range(self.timers[channel][timer]['number']):
                            await messageable.send(text)
                            await asyncio.sleep(0.1)

                        if self.timers[channel][timer]['number'] > 2:
                            cog.mod_cooldowns[channel] = time.time() + 2.5

                        self.messages_from_timer[channel] = 0
                        cog.cooldowns[channel][timer] = time.time() + 2.5
                        self.timers[channel][timer]['cooldown'] = time.time() + self.timers[channel][timer]['interval'] * 60

    @routines.routine(iterations=1)
    async def get_timers(self):
        async for document in db.timers.find():
            timers = {}
            for timer in document['timers']:
                link = timer.pop('link')
                timer['cooldown'] = 0
                timers[link] = timer

            self.timers[document['channel']] = timers
            self.messages_from_timer[document['channel']] = 0
            self.offline[document['channel']] = document['offline']


def prepare(bot):
    bot.add_cog(Timer(bot))
