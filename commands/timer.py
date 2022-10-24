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
        if message.echo or type(message.author).__name__ == 'WhisperChatter' or message.channel.name not in self.timers:
            return

        self.messages_from_timer[message.channel.name] += 1

    @commands.command(
        name='timer',
        aliases=['delt', 'timers'],
        cooldown={'per': 0, 'gen': 3},
        description='Автоматическая отправка команд с определённым интервалом. Полное описание - https://vk.cc/chCfMF '
    )
    async def timer(self, ctx):
        if not (ctx.channel.bot_is_vip or ctx.channel.bot_is_mod):
            await ctx.reply('Боту необходима випка или модерка для работы этой команды')
            return

        if ctx.command_alias != 'timers':
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
            elif value in ('a', 'а'):
                timer['announce'] = True
            elif value == 'noa':
                timer['announce'] = False
            elif value == 'on':
                timer['active'] = True
            elif value == 'off':
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

        if link not in self.timers.get(ctx.channel.name, []) and not interval and not number:
            await ctx.reply('Не указан интервал (в минутах) или количество сообщений')
            return
        elif interval and not number:
            await ctx.reply('Не указано количество сообщений')
            return
        elif interval and interval < 3:
            if number > 3:
                await ctx.reply('Таймеры с периодом меньше трёх минут могут отправлять не более трёх сообщений')
                return

            num = 1 + sum(bool(t['interval'] < 3 and t.get('active', True) and l != link) for l, t in self.timers.get(ctx.channel.name, {}).items())

            if num > 2:
                await ctx.reply('На канале может быть не более двух активных таймеров с периодом менее трёх минут')
                return
        elif number > 5:
            num = 1 + sum(bool(t['number'] > 5 and t.get('active', True) and l != link) for l, t in self.timers.get(ctx.channel.name, {}).items())

            if num > 3:
                await ctx.reply('На канале может быть не более трёх активных таймеров с количеством сообщений больше пяти')
                return

        if link not in self.timers.get(ctx.channel.name, []):
            if len(self.timers.get(ctx.channel.name, {})) == 10:
                await ctx.reply('На канале может быть не более десяти таймеров')
                return

            num = 1 + sum(bool(t.get('active', True)) for l, t in self.timers.get(ctx.channel.name, {}).items())

            if num > 5:
                await ctx.reply('На канале может быть не более пяти активных таймеров')
                return
        elif timer.get('active') and self.timers[ctx.channel.name].get(link):
            num = 0
            t = self.timers[ctx.channel.name][link]
            if t['interval'] < 3:
                if t['number'] > 3:
                    await ctx.reply('Таймеры с периодом меньше трёх минут могут отправлять не более трёх сообщений')
                    return
                if not t.get('active', True):
                    num = 1
            for l, t in self.timers.get(ctx.channel.name, {}).items():
                if t['interval'] < 3 and t.get('active', True) and l != link:
                    num += 1
            if num > 2:
                await ctx.reply('На канале может быть не более двух активных таймеров с периодом менее трёх минут')
                return

            num = 0
            if t['number'] > 5 and not t.get('active', True):
                num = 1
            for l, t in self.timers.get(ctx.channel.name, {}).items():
                if t['number'] > 5 and t.get('active', True) and l != link:
                    num += 1
            if num > 3:
                await ctx.reply('На канале может быть не более трёх активных таймеров с количеством сообщений больше пяти')
                return

            num = 1 + sum(bool(t.get('active', True)) for l, t in self.timers.get(ctx.channel.name, {}).items())

            if num > 5:
                await ctx.reply('На канале может быть не более пяти активных таймеров')
                return

        if ctx.channel.name not in self.timers:
            self.timers[ctx.channel.name] = {}
            self.messages_from_timer[ctx.channel.name] = 0

        if exist := link in self.timers[ctx.channel.name]:
            key['timers.link'] = link
            values = {'$set': {f'timers.$.{key}': value for key, value in (timer | {'link': link}).items()}}
            self.timers[ctx.channel.name][link] = self.timers[ctx.channel.name][link] | timer | {'cooldown': 0}
            message = f'Изменён таймер {self.bot._prefix}{link}'
        else:
            values = {'$setOnInsert': {'channel': ctx.channel.name, 'offline': False}, '$addToSet': {'timers': timer | {'link': link}}}
            self.timers[ctx.channel.name][link] = timer | {'cooldown': 0}
            message = f'Добавлен таймер {self.bot._prefix}{link}'
            self.offline[ctx.channel.name] = False

        if exist and 'active' in timer:
            if timer['active']:
                message = f'Включён таймер {self.bot._prefix}{link}'
            else:
                message = f'Выключен таймер {self.bot._prefix}{link}'

        await db.timers.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def delt(self, ctx, link):
        del self.timers[ctx.channel.name][link]
        await db.timers.update_one({'channel': ctx.channel.name}, {'$pull': {'timers': {'link': link}}})
        await ctx.reply(f'Удалён таймер {self.bot._prefix}{link}')

    async def list_timers(self, ctx):
        if not self.timers.get(ctx.channel.name):
            message = 'На вашем канале ещё нет таймеров'
        elif not ctx.content:
            message = f'Установленные таймеры: {self.bot._prefix}{str(f" {self.bot._prefix}").join(self.timers[ctx.channel.name])}'
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

    @routines.routine(seconds=11, iterations=0)
    async def check_timers(self):
        for channel in self.timers:
            timers = list(self.timers[channel])
            shuffle(timers)

            for timer in timers:
                if self.timers[channel][timer].get('active', True):
                    if channel not in self.bot.streams and not self.timers[channel][timer].get('offline', self.offline[channel]):
                        continue
                    if time.time() > self.timers[channel][timer]['cooldown'] and \
                                self.messages_from_timer[channel] >= self.timers[channel][timer]['number'] + 7:
                        cog = self.bot.get_cog('Link')

                        if self.timers[channel][timer]['number'] > 2 and time.time() - cog.mod_cooldowns.get(channel, 0) < 3:
                            continue
                        elif self.timers[channel][timer]['number'] < 3 and time.time() - cog.cooldowns.get(timer, 0) < 5:
                            continue

                        data = await db.links.find_one({'channel': channel, 'links.name': timer}, {'announce': 1, 'links.$': 1})
                        text = data['links'][0]['text']
                        announce = ''

                        if self.timers[channel][timer].get('announce'):
                            announce = data['links'][0].get('announce') or data['announce']

                        cog = self.bot.get_cog('Link')
                        messageable = self.bot.get_channel(channel)

                        cog.cooldowns[channel][timer] = time.time() + 3
                        if self.timers[channel][timer]['number'] > 2:
                            cog.mod_cooldowns[channel] = time.time() + 3
                            cog.cooldowns[channel][timer] = time.time() + 5

                        self.timers[channel][timer]['cooldown'] = time.time() + self.timers[channel][timer]['interval'] * 60

                        if not (announce or text.startswith('/announce') or text.startswith('.announce')):
                            for _ in range(self.timers[channel][timer]['number']):
                                await messageable.send(text)
                                await asyncio.sleep(0.1)
                        else:
                            if text.startswith('/me') or text.startswith('.me'):
                                text = text.split(maxsplit=1)[1]
                            await self.bot.announce(messageable, text, announce, self.timers[channel][timer]['number'])

                        self.messages_from_timer[channel] = 0

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
