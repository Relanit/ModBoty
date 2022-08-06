import asyncio

from twitchio.ext import commands

from config import CHANNELS

reason = 'Сообщение, содержащее запрещённую фразу (ModBoty)'


class MassBan(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.message_history = {}
        self.ban_phrases = {}
        self.timeouts = {}
        self.running = set()
        self.queue = {}

        for channel in CHANNELS:
            self.message_history[channel] = []

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        if message.author.is_mod:
            if message.content.startswith(self.bot._prefix):
                content = message.content.lstrip(self.bot._prefix)
                if not content:
                    return

                command = content.split(maxsplit=1)[0].lower()
                if command == 'stop':
                    await self.stop(message)
            return

        self.message_history[message.channel.name].append((message.author.name, message.content))
        if len(self.message_history[message.channel.name]) >= 50:
            del self.message_history[message.channel.name][0]

        if message.channel.name in self.ban_phrases:
            if self.ban_phrases[message.channel.name] in message.content.lower():
                if message.channel.name in self.running:
                    self.queue[message.channel.name].append(message.author.name)
                else:
                    while message.channel.limited:
                        await asyncio.sleep(0.1)
                    if message.channel.name in self.ban_phrases:
                        if message.channel.name in self.timeouts:
                            await message.channel.send(f'/timeout {message.author.name} {self.timeouts[message.channel.name]} {reason}')
                        else:
                            await message.channel.send(f'/ban {message.author.name} {reason}')

    @commands.command(
        name='mb',
        aliases=['mt'],
        cooldown={'per': 0, 'gen': 5},
        description='!mb value - массбан, !mt duration value - массмут. !stop для завершения.'
    )
    async def mass_ban(self, ctx):
        if not ctx.channel.bot_is_mod:
            await ctx.reply('Боту необходима модерка для работы этой команды')
            return

        content = ctx.content.lower()

        if not content:
            if ctx.command_alias == 'mb':
                await ctx.send('Введите банфразу')
            else:
                await ctx.send('Введите время и мутфразу')
            return

        ban_phrase = content

        if ctx.command_alias == 'mt':
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
                self.timeouts[ctx.channel.name] = timeout
            except ValueError:
                self.timeouts[ctx.channel.name] = 300
        else:
            self.timeouts.pop(ctx.channel.name, None)

        while ctx.limited:
            await asyncio.sleep(0.1)
        await ctx.reply('Запущено')

        self.running.add(ctx.channel.name)
        self.ban_phrases[ctx.channel.name] = ban_phrase
        self.queue[ctx.channel.name] = []
        banned_users = []

        for message in self.message_history[ctx.channel.name].copy():
            if ban_phrase in message[1].lower() and message[0] not in banned_users:
                while ctx.limited:
                    await asyncio.sleep(0.1)
                if ctx.channel.name in self.ban_phrases:
                    if ctx.channel.name in self.timeouts:
                        await ctx.send(f'/timeout {message[0]} {self.timeouts[ctx.channel.name]} {reason}')
                    else:
                        await ctx.send(f'/ban {message[0]} {reason}')
                    banned_users.append(message[0])
                    await asyncio.sleep(0.25)
                else:
                    return

        for user in self.queue[ctx.channel.name]:
            if user not in banned_users:
                while ctx.limited:
                    await asyncio.sleep(0.1)
                if ctx.channel.name in self.ban_phrases:
                    if ctx.channel.name in self.timeouts:
                        await ctx.send(f'/timeout {user} {self.timeouts[ctx.channel.name]} {reason}')
                    else:
                        await ctx.send(f'/ban {user} {reason}')
                    banned_users.append(user)
                    await asyncio.sleep(0.25)
                else:
                    return

        self.running.remove(ctx.channel.name)
        self.queue.pop(ctx.channel.name)

    async def stop(self, message):
        if message.channel.name in self.ban_phrases:
            self.ban_phrases.pop(message.channel.name, None)
            self.timeouts.pop(message.channel.name, None)
            self.running.discard(message.channel.name)
            self.queue.pop(message.channel.name, None)
            ctx = await self.bot.get_context(message)
            while ctx.limited:
                await asyncio.sleep(0.1)
            await ctx.reply('Остановлено')


def prepare(bot):
    bot.add_cog(MassBan(bot))
