import asyncio
import os
import time

from twitchio.ext import commands

reason = 'Сообщение, содержащее запрещённую фразу (от ModBoty). Начато %s'


class MassBan(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.message_history = {}
        self.first_senders = {}
        self.ban_phrases = {}
        self.queue = {}

        for channel in os.getenv('CHANNELS').split('&'):
            self.message_history[channel] = []
            self.first_senders[channel] = []

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        if message.channel.name in self.ban_phrases and message.author.is_mod:
            if message.content.startswith(self.bot._prefix):
                content = message.content.lstrip(self.bot._prefix)
                if not content:
                    return

                command = content.split(maxsplit=1)[0].lower()
                if command == 'stop':
                    self.ban_phrases.pop(message.channel.name, None)
                    self.queue.pop(message.channel.name, None)
                    ctx = await self.bot.get_context(message)
                    while ctx.limited:
                        await asyncio.sleep(0.1)
                    await ctx.reply('Остановлено')
            return

        self.message_history[message.channel.name].append({'author': message.author.name, 'content': message.content})
        if len(self.message_history[message.channel.name]) >= 50:
            del self.message_history[message.channel.name][0]

        for msg in self.first_senders[message.channel.name].copy():
            if time.time() - msg['time'] > 15:
                del self.first_senders[message.channel.name][0]
            else:
                break

        if message.tags['first-msg'] == '1':
            self.first_senders[message.channel.name].append({'time': time.time(), 'author': message.author.name})
            if self.ban_phrases.get(message.channel.name) == '':
                self.queue[message.channel.name].append(message.author.name)

        if self.ban_phrases.get(message.channel.name):
            if self.ban_phrases[message.channel.name] in message.content.lower():
                self.queue[message.channel.name].append(message.author.name)


    @commands.command(
        name='mb',
        aliases=['mt', 'm', 'mbf'],
        cooldown={'per': 0, 'gen': 60},
        description='Бан/мут пользователей, написавших сообщение с указанной фразой или первое сообщение в чате. Полное описание - https://vk.cc/chCfLq '
    )
    async def mass_ban(self, ctx):
        if not ctx.channel.bot_is_mod:
            await ctx.reply('Боту необходима модерка для работы этой команды')
            return

        content = ctx.content.lower()

        if not content and ctx.command_alias != 'mbf':
            if ctx.command_alias == 'mb':
                await ctx.send('Введите банфразу')
            else:
                await ctx.send('Введите время и мутфразу')
            return

        ban_phrase = content if ctx.command_alias != 'mbf' else ''

        if ctx.command_alias in ('mt', 'm'):
            content_split = content.split(' ', 1)
            try:
                timeout = int(content_split[0])
                if len(content_split) == 1:
                    await ctx.send('Введите мутфразу')
                    return
                if not 1 <= timeout <= 1209600:
                    await ctx.reply('Неверное значение таймаута')
                    return
                ban_phrase = content_split[1]
            except ValueError:
                timeout = 300
            text = f'/timeout %s {timeout} {reason % ctx.author.name}'
        else:
            text = f'/ban %s {reason % ctx.author.name}'

        while ctx.limited:
            await asyncio.sleep(0.1)
        await ctx.reply('Запущено')

        start = time.time()
        self.ban_phrases[ctx.channel.name] = ban_phrase
        self.queue[ctx.channel.name] = []
        banned_users = []

        if ban_phrase:
            for message in self.message_history[ctx.channel.name].copy():
                if ban_phrase in message['content'].lower() and message['author'] not in banned_users:
                    while ctx.limited:
                        await asyncio.sleep(0.1)
                    if ctx.channel.name in self.ban_phrases:
                        await ctx.send(text % message['author'])
                        banned_users.append(message['author'])
                        await asyncio.sleep(0.3)
                    else:
                        return
        else:
            for message in self.first_senders[ctx.channel.name].copy():
                while ctx.limited:
                    await asyncio.sleep(0.1)
                if ctx.channel.name in self.ban_phrases:
                    await ctx.send(text % message['author'])
                    banned_users.append(message['author'])
                    await asyncio.sleep(0.3)
                else:
                    return

        while ctx.channel.name in self.ban_phrases:
            for user in self.queue[ctx.channel.name]:
                if user not in banned_users:
                    while ctx.limited:
                        await asyncio.sleep(0.1)
                    if ctx.channel.name in self.ban_phrases:
                        await ctx.send(text % user)
                        banned_users.append(user)
                        await asyncio.sleep(0.3)
                    else:
                        return

            if time.time() - start > 300:
                self.ban_phrases.pop(ctx.channel.name, None)
                self.queue.pop(ctx.channel.name, None)
                return

            banned_users.clear()
            self.queue.get(ctx.channel.name, []).clear()
            await asyncio.sleep(0.1)


def prepare(bot):
    bot.add_cog(MassBan(bot))
