import time

from twitchio.ext import commands

from config import db

reason = 'spam (by ModBoty)'


class Inspect(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.limits = {}
        self.timeouts = {}
        self.warned_users = {}
        self.message_log = {}

    """
    * - необязательно

    inspect [параметры]

    Параметры:
    * сообщения/время
    * лимитсообщений% - позволяет нарушать лимит сообщения/время, если сообщения пользователя занимают в чате меньше указанного процента
    * таймауты через пробел
    """

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        if message.channel.name in self.limits:
            now = time.time()
            self.message_log[message.channel.name].append({'time': now, 'author': message.author.name})
            for msg in self.message_log[message.channel.name].copy():
                if now - msg['time'] > self.limits[message.channel.name]['time_unit']:
                    del self.message_log[message.channel.name][0]
                else:
                    break

            if message.author.is_mod:
                return

            chatters = [msg['author'] for msg in self.message_log[message.channel.name]]
            count = chatters.count(message.author.name)
            handle = True

            if count > self.limits[message.channel.name]['messages']:
                if count > len(chatters) / 100 * self.limits[message.channel.name]['percent_limit']:
                    handle = False

            if not handle:
                new = []
                for msg in self.message_log[message.channel.name]:
                    if msg['author'] != message.author.name:
                        new.append(msg)

                self.message_log[message.channel.name] = new

            if not handle and message.author.name not in self.warned_users[message.channel.name]:
                self.warned_users[message.channel.name][message.author.name] = 0

                ctx = await self.bot.get_context(message)
                await ctx.reply('Без спамчика :|')
                await ctx.send(f'/timeout {message.author.name} 10 {reason}')
                await db.update_one({'channel': message.channel.name}, {'$inc': {'stats': message.author.name}})
            elif not handle:
                i = self.warned_users[message.channel.name][message.author.name]
                timeout = self.timeouts[message.channel.name][i]

                if len(self.timeouts[message.channel.name]) > self.warned_users[message.channel.name][message.author.name] + 1:
                    self.warned_users[message.channel.name][message.author.name] += 1

                await message.channel.send(f'/timeout {message.author.name} {timeout} {reason}')
                await db.update_one({'channel': message.channel.name}, {'$inc': {'stats': message.author.name}})

    @commands.command(
        name='inspect',
        cooldown={'per': 0, 'gen': 5},
        description='Установка лимита сообщений на стриме. Полное описание: https://i.imgur.com/3F7nZLJ.png',
    )
    async def inspect(self, ctx):
        if not ctx.channel.bot_is_mod:
            await ctx.reply('Боту необходима модерка для работы этой команды')
            return

        content = ctx.content.lower()
        if not content:
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            if data:
                message = f'Статус: {"включено" if data["active"] else "выключено"}. ' \
                          f'Лимит: {data["messages"]} сообщений в {data["time_unit"] if data["time_unit"] % 1 != 0 else int(data["time_unit"])} секунд. ' \
                          f'Лимит от всех сообщений в чате:  {data["percent_limit"]}%. ' \
                          f'Таймауты: {", ".join(map(str, data["timeouts"]))}.'
                await ctx.reply(message)
            else:
                await ctx.reply(f'Сначала настройте наблюдение, {self.bot._prefix}help inspect')
        elif content == 'on':
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            if data:
                if ctx.channel.name not in self.limits and ctx.channel.name in self.bot.streams:
                    await self.set(ctx.channel.name)

                await db.inspects.update_one({'channel': ctx.channel.name}, {'$set': {'active': True}})
                await ctx.reply('✅ Включено')
            else:
                await ctx.reply(f'Сначала настройте наблюдение, {self.bot._prefix}help inspect')
        elif content == 'off':
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            if data:
                if ctx.channel.name in self.limits:
                    self.unset(ctx.channel.name)
                await db.inspects.update_one({'channel': ctx.channel.name}, {'$set': {'active': False}})
                await ctx.reply('❌ Выключено')
            else:
                await ctx.reply(f'Сначала настройте наблюдение, {self.bot._prefix}help inspect')
        elif content == 'stats':
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            if not data.get('stats'):
                await ctx.reply('Статистика не найдена')
                return

            items = data['stats'].items()
            sorted_users = sorted(items, key=lambda x: x[1], reverse=True)

            top = []
            for place, user in enumerate(sorted_users[:5], start=1):
                name = user[0][:1] + u'\U000E0000' + user[0][1:]
                top.append(f'{place}. {name} - {user[1]}{" сообщений" if place == 1 else ""}')

            await ctx.reply(f'Топ спамеров за стрим: {", ".join(top)}')
        elif content.startswith('stats'):
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            user = content.split()[1]
            if user not in data['stats']:
                await ctx.reply('У пользователя 0 отстранений')
                return

            items = data['stats'].items()
            sorted_users = sorted(items, key=lambda x: x[1], reverse=True)

            for pos in range(len(sorted_users)):
                if ctx.author.name in sorted_users[pos]:
                    place = pos + 1
                    timeouts = sorted_users[pos][1]
                    break

            await ctx.reply(f'{place} место ({timeouts} отстранений)')
        else:
            content = content.split()

            values = {}
            for value in content:
                if '/' in value:
                    try:
                        messages, time_unit = value.replace(',', '.').split('/')
                        messages = int(messages)
                        time_unit = round(float(time_unit), 1)
                    except ValueError:
                        await ctx.reply('Неверная запись времени или количества сообщений')
                        return

                    if not 1 <= time_unit <= 15:
                        await ctx.reply('Время не должно быть меньше 1 или больше 15 секунд')
                        return
                    if not 1 <= messages <= time_unit:
                        await ctx.reply('Количество сообщений не должно быть меньше 1 или больше указанного времени.')
                        return

                    values['messages'] = messages
                    values['time_unit'] = time_unit
                elif value.endswith('%'):
                    try:
                        percent_limit = int(value.strip('%'))
                    except ValueError:
                        await ctx.reply('Неверная запись лимита в процентах')
                        return

                    if not 0 <= percent_limit < 100:
                        await ctx.reply('Неверная запись лимита в процентах')
                        return

                    values['percent_limit'] = percent_limit
                elif value == 'online':
                    values['offline'] = False
                elif value == 'always':
                    values['offline'] = True
                else:
                    try:
                        timeout = int(value)

                        values['timeouts'] = [] if 'timeouts' not in values else values['timeouts']
                        values['timeouts'].append(timeout)
                    except ValueError:
                        await ctx.reply('Неверная запись таймаутов или команды')
                        return

                    if not 1 <= timeout <= 1209600:
                        await ctx.reply('Неверное значение таймаута')
                        return

            data = await db.inspects.find_one({'channel': ctx.channel.name})
            if not data:
                if 'messages' not in values:
                    await ctx.reply('Для начала установите сообщения и время')
                    return

                if 'timeouts' not in values:
                    values['timeouts'] = [600]

                await db.inspects.update_one({'channel': ctx.channel.name}, {
                    '$setOnInsert': {'channel': ctx.channel.name, 'active': False, 'offline': False},
                    '$set': values}, upsert=True)
            else:
                await db.inspects.update_one({'channel': ctx.channel.name}, {'$set': values})

            if ctx.channel.name in self.limits:
                await self.set(ctx.channel.name)

            await ctx.reply('Готово.')

    async def set(self, channel):
        data = await db.inspects.find_one({'channel': channel})
        self.warned_users[channel] = {}
        self.limits[channel] = {'messages': data['messages'], 'time_unit': data['time_unit'], 'percent_limit': data['percent_limit']}
        self.timeouts[channel] = data['timeouts']
        self.message_log[channel] = []

    def unset(self, channel):
        del self.limits[channel]
        del self.timeouts[channel]
        del self.warned_users[channel]
        del self.message_log[channel]


def prepare(bot):
    bot.add_cog(Inspect(bot))
