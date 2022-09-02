from twitchio.ext import commands, routines

from config import db

reason = 'Запрещённая фраза (by ModBoty)'


class Banwords(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.banwords = {}
        self.mutewords = {}
        self.get_banwords.start(stop_on_error=False)

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        if message.channel.name in self.banwords:
            content = message.content.lower()
            for banword in self.banwords[message.channel.name]:
                if banword in content:
                    await message.channel.send(f'/ban {message.author.name} {reason}')
        if message.channel.name in self.mutewords:
            content = message.content.lower()
            timeout = 0
            for muteword in self.mutewords[message.channel.name]:
                if muteword['muteword'] in content and muteword['timeout'] > timeout:
                    timeout = muteword['timeout']
            if timeout:
                await message.channel.send(f'/timeout {message.author.name} {timeout} {reason}')

    @commands.command(
        name='addb',
        aliases=['delb', 'addm', 'delm', 'bw', 'mw'],
        cooldown={'per': 0, 'gen': 5},
        description='Pong.'
    )
    async def command(self, ctx):
        if not ctx.channel.bot_is_mod:
            await ctx.reply('Боту необходима модерка для работы этой команды')
            return

        if not ctx.content and ctx.command_alias not in ('bw', 'mw'):
            await ctx.reply('Пустой ввод')
            return

        if ctx.command_alias == 'addb':
            await self.add_banword(ctx)
        elif ctx.command_alias == 'delb':
            await self.delete_banword(ctx)
        elif ctx.command_alias == 'addm':
            await self.add_muteword(ctx)
        elif ctx.command_alias == 'delm':
            await self.delete_muteword(ctx)
        elif ctx.command_alias == 'bw':
            await self.list_banwords(ctx)
        else:
            await self.list_mutewords(ctx)

    async def add_banword(self, ctx):
        if len(self.banwords.get(ctx.channel.name, [])) + len(self.mutewords.get(ctx.channel.name, [])) == 30:
            await ctx.reply('Достигнут лимит банвордов и мутвордов - 30')
            return

        banword = ctx.content.lower()

        if banword in self.banwords.get(ctx.channel.name, []):
            await ctx.reply('Банворд уже добавлен')
            return

        if ctx.channel.name not in self.banwords:
            self.banwords[ctx.channel.name] = []

        self.banwords[ctx.channel.name].append(banword)
        await db.banwords.update_one({'channel': ctx.channel.name}, {'$setOnInsert': {'channel': ctx.channel.name},
                                                                     '$addToSet': {'banwords': banword}}, upsert=True)
        await ctx.reply(f'Добавлен банворд {banword}')

    async def delete_banword(self, ctx):
        banword = ctx.content.lower()

        if banword not in self.banwords.get(ctx.channel.name, []):
            await ctx.reply('Банворд не найден')
            return

        self.banwords[ctx.channel.name].remove(banword)
        await db.banwords.update_one({'channel': ctx.channel.name}, {'$pull': {'banwords': banword}})
        await ctx.reply(f'Удалён банворд {ctx.content.lower()}')

    async def add_muteword(self, ctx):
        if len(self.banwords.get(ctx.channel.name, [])) + len(self.mutewords.get(ctx.channel.name, [])) == 30:
            await ctx.reply('Достигнут лимит банвордов и мутвордов - 30')
            return

        content = ctx.content.split()
        if len(content) < 2:
            await ctx.reply('Укажите время мута в секундах и фразу')
            return

        try:
            timeout = int(content[0])
        except ValueError:
            await ctx.reply(f'Укажите время мута в секундах')
            return

        muteword = ' '.join(content[1:])

        found = False
        for item in self.mutewords.get(ctx.channel.name, []):
            if item['muteword'] == muteword:
                found = True

        message = f'Добавлен мутворд {muteword}'
        if found:
            await db.banwords.update_one({'channel': ctx.channel.name}, {'$pull': {'mutewords': {'muteword': muteword}}})
            message = f'Изменено время таймаута {muteword}'

        if ctx.channel.name not in self.mutewords:
            self.mutewords[ctx.channel.name] = []

        self.mutewords[ctx.channel.name].append({'muteword': muteword, 'timeout': timeout})
        await db.banwords.update_one({'channel': ctx.channel.name}, {'$setOnInsert': {'channel': ctx.channel.name},
                                                                     '$push': {'mutewords': {'timeout': timeout, 'muteword': muteword}}}, upsert=True)
        await ctx.reply(message)

    async def delete_muteword(self, ctx):
        muteword = ctx.content.lower()

        found = False
        for item in self.mutewords.get(ctx.channel.name, []):
            if item['muteword'] == muteword:
                found = True

        if not found:
            await ctx.reply('Мутворд не найден')
            return

        await db.banwords.update_one({'channel': ctx.channel.name}, {'$pull': {'mutewords': {'muteword': muteword}}})
        await ctx.reply(f'Удалён мутворд {ctx.content.lower()}')

    async def list_banwords(self, ctx):
        if not self.banwords.get(ctx.channel.name):
            message = 'На вашем канале ещё нет банвордов'
        else:
            message = 'Банворды канала: ' + ' | '.join(self.banwords[ctx.channel.name])
        await ctx.reply(message)

    async def list_mutewords(self, ctx):
        if not self.mutewords.get(ctx.channel.name):
            message = 'На вашем канале ещё нет мутвордов'
        else:
            message = 'Мутворды канала: ' + ' | '.join([muteword['muteword'] for muteword in self.mutewords[ctx.channel.name]])
        await ctx.reply(message)

    @routines.routine(iterations=1)
    async def get_banwords(self):
        async for document in db.banwords.find():
            if 'banwords' in document:
                self.banwords[document['channel']] = document['banwords']
            if 'mutewords' in document:
                self.mutewords[document['channel']] = document['mutewords']


def prepare(bot):
    bot.add_cog(Banwords(bot))
