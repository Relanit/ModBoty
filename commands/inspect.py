import time

from twitchio.ext import commands

from config import db


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
                await ctx.reply('Без спамчика :)')
                await ctx.send(f'/timeout {message.author.name} 10 spam (by SvinBot)')
            elif not handle:
                i = self.warned_users[message.channel.name][message.author.name]
                timeout = self.timeouts[message.channel.name][i]

                if len(self.timeouts[message.channel.name]) > self.warned_users[message.channel.name][message.author.name] + 1:
                    self.warned_users[message.channel.name][message.author.name] += 1

                await message.channel.send(f'/timeout {message.author.name} {timeout} spam (by SvinBot)')

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
        else:
            content = content.split()

            messages = 0
            time_unit = 0
            percent_limit = 0
            timeouts = []
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
                elif value.endswith('%'):
                    try:
                        percent_limit = int(value.strip('%'))
                    except ValueError:
                        await ctx.reply('Неверная запись лимита в процентах')
                        return

                    if not 0 <= percent_limit < 100:
                        await ctx.reply('Неверная запись лимита в процентах')
                        return
                else:
                    try:
                        timeout = int(value)
                        timeouts.append(timeout)
                    except ValueError:
                        await ctx.reply('Неверная запись таймаутов или команды')
                        return

                    if not 1 <= timeout <= 1209600:
                        await ctx.reply('Неверное значение таймаута')
                        return

            data = await db.inspects.find_one({'channel': ctx.channel.name})
            if not data:
                if not messages:
                    await ctx.reply('Для начала установите сообщения и время')
                    return

                if not timeouts:
                    timeouts.append(600)

                await db.inspects.update_one({'channel': ctx.channel.name}, {
                    '$setOnInsert': {'channel': ctx.channel.name, 'active': False},
                    '$set': {'messages': messages, 'time_unit': time_unit, 'percent_limit': percent_limit, 'timeouts': timeouts}}, upsert=True)
            else:
                values = {}
                if messages:
                    values.update({'messages': messages, 'time_unit': time_unit})
                if percent_limit:
                    values.update({'percent_limit': percent_limit})
                if timeouts:
                    values.update({'timeouts': timeouts})
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
