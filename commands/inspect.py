import asyncio
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

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        if message.channel.name in self.limits:
            now = time.time()
            self.message_log[message.channel.name].append({'time': now, 'author': message.author.name})

            first_limit = self.limits[message.channel.name].get('first_limit', {})
            second_limit = self.limits[message.channel.name].get('second_limit', {})
            main_limit, secondary_limit = (first_limit, second_limit) if first_limit.get('time_unit', 0) > second_limit.get('time_unit', 0) else (second_limit, first_limit)

            for msg in self.message_log[message.channel.name].copy():
                if now - msg['time'] > main_limit['time_unit']:
                    del self.message_log[message.channel.name][0]
                else:
                    break

            if message.author.is_mod:
                return

            percent_limit = self.limits[message.channel.name].get('percent_limit', 0)

            chatters = [msg['author'] for msg in self.message_log[message.channel.name]]
            count = chatters.count(message.author.name)
            handle = True

            if count > main_limit['messages']:
                handle = False
                if percent_limit and not (count > len(chatters) / 100 * percent_limit):
                    handle = True

            if secondary_limit and handle:
                if main_limit['time_unit'] < secondary_limit['time_unit'] * 2:
                    message_log = self.message_log[message.channel.name].copy()
                    for msg in message_log.copy():
                        if now - msg['time'] > secondary_limit['time_unit']:
                            del message_log[0]
                        else:
                            break
                    chatters = [msg['author'] for msg in message_log]
                else:
                    chatters = []
                    for msg in self.message_log[message.channel.name][::-1]:
                        if now - msg['time'] > secondary_limit['time_unit']:
                            break
                        else:
                            chatters.append(msg['author'])

                count = chatters.count(message.author.name)

                if count > secondary_limit['messages']:
                    handle = False
                    if percent_limit and not (count > len(chatters) / 100 * percent_limit):
                        handle = True

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

                while ctx.limited:
                    await asyncio.sleep(0.1)

                await ctx.send(f'/timeout {message.author.name} 10 {reason}')
                if message.channel.name in self.bot.streams:
                    await db.inspects.update_one({'channel': message.channel.name},
                                                 {'$inc': {f'stats.{message.author.name}': 1}})
            elif not handle:
                i = self.warned_users[message.channel.name][message.author.name]
                timeout = self.timeouts[message.channel.name][i]

                if len(self.timeouts[message.channel.name]) > self.warned_users[message.channel.name][message.author.name] + 1:
                    self.warned_users[message.channel.name][message.author.name] += 1

                while message.channel.limited:
                    await asyncio.sleep(0.1)

                await message.channel.send(f'/timeout {message.author.name} {timeout} {reason}')
                if message.channel.name in self.bot.streams:
                    await db.inspects.update_one({'channel': message.channel.name},
                                                 {'$inc': {f'stats.{message.author.name}': 1}})

    @commands.command(
        name='inspect',
        cooldown={'per': 0, 'gen': 5},
        description='Ограничения на количество отправленных сообщений. Полное описание: https://i.imgur.com/kTCeDVf.png ',
    )
    async def inspect(self, ctx):
        if not ctx.channel.bot_is_mod:
            await ctx.reply('Боту необходима модерка для работы этой команды')
            return

        content = ctx.content.lower()
        if not content:
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            if not data:
                await ctx.reply(f'Сначала настройте наблюдение, {self.bot._prefix}help inspect')
                return

            first_limit = data['first_limit'] if 'first_limit' in data else False
            second_limit = data['second_limit'] if 'second_limit' in data else False
            percent_limit = f'Лимит от всех сообщений в чате:  {data["percent_limit"]}%.' if 'percent_limit' in data else False

            if second_limit:
                second_limit = f' {second_limit["messages"]}//{second_limit["time_unit"] if second_limit["time_unit"] % 1 != 0 else int(second_limit["time_unit"])}.'
            if first_limit:
                first_limit = f'{first_limit["messages"]}/{first_limit["time_unit"] if first_limit["time_unit"] % 1 != 0 else int(first_limit["time_unit"])}{", " if second_limit else ""}'

            message = f'Статус: {"включено" if data["active"] else "выключено"}. ' \
                      f'Лимиты: {first_limit if first_limit else ""}' \
                      f'{second_limit if second_limit else "."} ' \
                      f'{percent_limit if percent_limit else ""} ' \
                      f'Таймауты: {", ".join(map(str, data["timeouts"]))}. ' \
                      f'{"Только на стриме." if not data["offline"] else ""}'
            await ctx.reply(message)
        elif content == 'on':
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            if data:
                if ctx.channel.name not in self.limits:
                    if ctx.channel.name in self.bot.streams or data['offline']:
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

            if not data or not data.get('stats'):
                await ctx.reply('Статистика не найдена')
                return

            items = data['stats'].items()
            sorted_users = sorted(items, key=lambda x: x[1], reverse=True)
            number = len(sorted_users)

            top = []
            for place, user in enumerate(sorted_users[:5], start=1):
                name = user[0][:1] + u'\U000E0000' + user[0][1:]
                top.append(f'{place}. {name} - {user[1]}{" отстранений" if place == 1 else ""}')

            await ctx.reply(f'Всего отстранено: {number}. Топ спамеров за стрим: {", ".join(top)}')
        elif content.startswith('stats'):
            data = await db.inspects.find_one({'channel': ctx.channel.name})

            if not data.get('stats'):
                await ctx.reply('Статистика не найдена')
                return

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
            values = {'$set': {}, '$unset': {}}
            inspect = await db.inspects.find_one({'channel': ctx.channel.name}) or {}

            for value in content:
                if '/' in value:
                    split, limit = ('//', 'second_limit') if '//' in value else ('/', 'first_limit')

                    if value.replace('/', ''):
                        try:
                            messages, time_unit = value.replace(',', '.').split(split)
                            messages = int(messages)
                            time_unit = round(float(time_unit), 1)
                        except ValueError:
                            await ctx.reply('Неверная запись времени или количества сообщений')
                            return

                        if not 1 <= time_unit <= 60:
                            await ctx.reply('Время не должно быть меньше 1 или больше 60 секунд')
                            return
                        if not 1 <= messages <= 60:
                            await ctx.reply('Количество сообщений не должно быть меньше 1 или больше 60.')
                            return

                        values['$set'][limit] = {'messages': messages, 'time_unit': time_unit}
                    elif inspect and 'first_limit' in inspect \
                            and 'second_limit' in inspect and not ('first_limit' in values['$unset'] or 'second_limit' in values['$unset']):
                        values['$unset'][limit] = 1
                    else:
                        await ctx.reply('Чтобы удалить лимит, должен быть установлен другой')
                        return
                elif value.endswith('%'):
                    percent_limit = value.strip('%')

                    if percent_limit:
                        try:
                            percent_limit = int(percent_limit)
                        except ValueError:
                            await ctx.reply('Неверная запись лимита в процентах')
                            return

                        if not 0 <= percent_limit < 100:
                            await ctx.reply('Неверная запись лимита в процентах')
                            return

                    if not percent_limit:
                        values['$unset']['percent_limit'] = 1
                    else:
                        values['$set']['percent_limit'] = percent_limit
                elif value == 'online':
                    values['$set']['offline'] = False
                elif value == 'always':
                    values['$set']['offline'] = True
                else:
                    try:
                        timeout = int(value)
                        values['$set']['timeouts'] = [] if 'timeouts' not in values['$set'] else values['$set']['timeouts']
                        values['$set']['timeouts'].append(timeout)
                    except ValueError:
                        await ctx.reply('Неверная запись таймаутов или команды')
                        return

                    if not 1 <= timeout <= 1209600:
                        await ctx.reply('Неверное значение таймаута')
                        return

            first_unit = values['$set'].get('first_limit', inspect.get('first_limit', {})).get('time_unit', 0)
            second_unit = values['$set'].get('second_limit', inspect.get('second_limit', {})).get('time_unit', 0)
            if first_unit and first_unit == second_unit:
                await ctx.reply('Не должно быть двух лимитов с одинаковым временем')
                return
            elif first_unit > 15 and second_unit > 15:
                await ctx.reply('Не должно быть больше одного лимита с временем более 15 секунд')
                return

            on_insert = {'channel': ctx.channel.name, 'active': False}
            if not inspect:
                if not ('first_limit' in values['$set'] or 'second_limit' in values['$set']):
                    await ctx.reply('Для начала установите сообщения и время')
                    return

                if 'timeouts' not in values['$set']:
                    values['$set']['timeouts'] = [60, 300, 600]
                if 'offline' not in values['$set']:
                    on_insert['offline'] = False
            await db.inspects.update_one({'channel': ctx.channel.name}, {'$setOnInsert': on_insert, **values}, upsert=True)

            if ctx.channel.name not in self.bot.streams:
                if values['$set'].get('offline', inspect.get('offline')) and inspect.get('active'):
                    await self.set(ctx.channel.name)
                elif ctx.channel.name in self.limits:
                    self.unset(ctx.channel.name)
            elif ctx.channel.name in self.limits:
                await self.set(ctx.channel.name)

            await ctx.reply('Готово.')

    async def set(self, channel):
        data = await db.inspects.find_one({'channel': channel})
        self.limits[channel] = {}
        self.timeouts[channel] = data['timeouts']
        self.warned_users[channel] = {}
        self.message_log[channel] = []

        if 'first_limit' in data:
            limit = data['first_limit']
            self.limits[channel]['first_limit'] = {'messages': limit['messages'], 'time_unit': limit['time_unit']}
        if 'second_limit' in data:
            limit = data['second_limit']
            self.limits[channel]['second_limit'] = {'messages': limit['messages'], 'time_unit': limit['time_unit']}
        if 'percent_limit' in data:
            self.limits[channel]['percent_limit'] = data['percent_limit']

    def unset(self, channel):
        del self.limits[channel]
        del self.timeouts[channel]
        del self.warned_users[channel]
        del self.message_log[channel]


def prepare(bot):
    bot.add_cog(Inspect(bot))
