import asyncio
import os

from twitchio.ext import commands, routines

from config import db

reason = 'Сообщение, содержащее запрещённую фразу (by ModBoty)'


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
                    return
        if message.channel.name in self.mutewords:
            content = message.content.lower()
            timeout = 0
            for muteword in self.mutewords[message.channel.name]:
                if muteword['muteword'] in content and muteword['timeout'] > timeout:
                    timeout = muteword['timeout']
            if timeout:
                await message.channel.send(f'/timeout {message.author.name} {timeout} {reason}')

    @commands.command(
        name='bword',
        aliases=['mword', 'delb', 'delm', 'bwords', 'mwords'],
        cooldown={'per': 0, 'gen': 5},
        description='Запрещённые слова, за отправку которых пользователь получает бан/мут. Полное описание: https://i.imgur.com/6qvUgfN.png '
    )
    async def command(self, ctx):
        if not ctx.channel.bot_is_mod:
            await ctx.reply('Боту необходима модерка для работы этой команды')
            return

        if not ctx.content and ctx.command_alias not in ('bwords', 'mwords'):
            await ctx.reply('Пустой ввод')
            return

        if ctx.command_alias == 'bword':
            await self.add_banword(ctx)
        elif ctx.command_alias == 'delb':
            await self.delete_banword(ctx)
        elif ctx.command_alias == 'mword':
            await self.add_muteword(ctx)
        elif ctx.command_alias == 'delm':
            await self.delete_muteword(ctx)
        elif ctx.command_alias == 'bwords':
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

        for word in self.banwords.get(ctx.channel.name, []):
            if word in banword:
                await ctx.reply('Часть фразы уже есть в банвордах канала')
                return

        if len(banword) > 20:
            await ctx.reply('Длина банворда не должна превышать 20 символов')
            return

        if ctx.channel.name not in self.banwords:
            self.banwords[ctx.channel.name] = []

        self.banwords[ctx.channel.name].append(banword)
        await db.banwords.update_one({'channel': ctx.channel.name}, {'$setOnInsert': {'channel': ctx.channel.name},
                                                                     '$addToSet': {'banwords': banword}}, upsert=True)
        await ctx.reply('Добавлено')

    async def delete_banword(self, ctx):
        banword = ctx.content.lower()

        if banword not in self.banwords.get(ctx.channel.name, []):
            await ctx.reply('Банворд не найден')
            return

        self.banwords[ctx.channel.name].remove(banword)
        await db.banwords.update_one({'channel': ctx.channel.name}, {'$pull': {'banwords': banword}})
        await ctx.reply('Удалено')

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

        if not 1 <= timeout <= 1209600:
            await ctx.reply('Неверное время мута')
            return

        muteword = ' '.join(content[1:]).lower()

        if len(muteword) > 20:
            await ctx.reply('Длина мутворда не должна превышать 20 символов')
            return

        found = False
        for item in self.mutewords.get(ctx.channel.name, []):
            if item['muteword'] == muteword:
                found = True
                break
            elif item['muteword'] in muteword:
                await ctx.reply('Часть фразы уже есть в списке мутвордов канала')
                return

        message = 'Добавлено'
        if found:
            await db.banwords.update_one({'channel': ctx.channel.name}, {'$pull': {'mutewords': {'muteword': muteword}}})
            message = f'Изменено'

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
                self.mutewords[ctx.channel.name].remove(item)
                break

        if not found:
            await ctx.reply('Мутворд не найден')
            return

        await db.banwords.update_one({'channel': ctx.channel.name}, {'$pull': {'mutewords': {'muteword': muteword}}})
        await ctx.reply(f'Удалено')

    async def list_banwords(self, ctx):
        if not self.banwords.get(ctx.channel.name):
            await ctx.reply('На вашем канале ещё нет банвордов')
        else:
            message = f'Банворды канала {ctx.channel.name}: ' + ' | '.join(self.banwords[ctx.channel.name])
            message2 = ''

            if len(message) > 500:
                message = f'Банворды канала {ctx.channel.name}: '

                for banword in self.banwords[ctx.channel.name]:
                    banword = banword + ' | ' if banword != self.banwords[ctx.channel.name][-1] else banword
                    if len(message + banword) < 500:
                        message += banword
                    else:
                        message2 += banword

            user = await ctx.author.user()
            await ctx.reply('Список банвордов отправлен в личные сообщения')
            await user.send_whisper(token=os.getenv('TOKEN'), from_user_id=self.bot.user_id, to_user_id=user.id,
                                    message=message)
            if message2:
                await asyncio.sleep(1)
                await user.send_whisper(token=os.getenv('TOKEN'), from_user_id=self.bot.user_id, to_user_id=user.id,
                                        message=message2)

    async def list_mutewords(self, ctx):
        if not self.mutewords.get(ctx.channel.name):
            await ctx.reply('На вашем канале ещё нет мутвордов')
        else:
            message = f'Мутворды канала {ctx.channel.name}: ' + ' | '.join([muteword['muteword'] + ' ' + str(muteword['timeout']) for muteword in self.mutewords[ctx.channel.name]])
            message2 = ''

            if len(message) > 500:
                message = f'Мутворды канала {ctx.channel.name}: '

                for muteword in self.mutewords[ctx.channel.name]:
                    muteword = muteword['muteword'] + ' ' + str(muteword['timeout']) + ' | ' if muteword != self.mutewords[ctx.channel.name][-1] else muteword['muteword'] + ' ' + str(muteword['timeout'])

                    if len(message + muteword) < 500:
                        message += muteword
                    else:
                        message2 += muteword

            user = await ctx.author.user()
            await ctx.reply('Список мутвордов отправлен в личные сообщения')
            await user.send_whisper(token=os.getenv('TOKEN'), from_user_id=self.bot.user_id, to_user_id=user.id,
                                    message=message)
            if message2:
                await asyncio.sleep(1)
                await user.send_whisper(token=os.getenv('TOKEN'), from_user_id=self.bot.user_id, to_user_id=user.id,
                                        message=message2)

    @routines.routine(iterations=1)
    async def get_banwords(self):
        async for document in db.banwords.find():
            if 'banwords' in document:
                self.banwords[document['channel']] = document['banwords']
            if 'mutewords' in document:
                self.mutewords[document['channel']] = document['mutewords']


def prepare(bot):
    bot.add_cog(Banwords(bot))
