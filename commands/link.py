import asyncio
import time

from twitchio.ext import commands, routines

from config import db


class Link(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.links = {}
        self.links_aliases = {}
        self.cooldowns = {}
        self.mod_cooldowns = {}
        self.get_links.start(stop_on_error=False)

    @commands.Cog.event()
    async def event_message(self, message):
        if message.echo:
            return

        content = message.content
        if 'reply-parent-msg-id' in message.tags:
            content = message.content.split(' ', 1)[1]

        if content.startswith(self.bot._prefix):
            content = content.lstrip(self.bot._prefix)
            if not content:
                return

            link = content.split(maxsplit=1)[0].lower()

            if link in self.links.get(message.channel.name, []) or (link := self.links_aliases.get(message.channel.name, {}).get(link, '')):
                data = await db.links.find_one({'channel': message.channel.name, 'links.name': link}, {'private': 1, 'links.$': 1})
                private = data['private'] if 'private' not in data['links'][0] else data['links'][0]['private']
                text = data['links'][0]['text']

                if message.author.is_mod:
                    content = ' '.join(content.split()[1:3])
                    num = 1

                    if 'a' in content or 'а' in content:
                        content = content.replace('a', ' ').replace('а', ' ').strip(' ')
                        text = f'/announce {text.split(maxsplit=1)[1]}' if 'announce' in text else f'/announce {text}'

                    if content:
                        try:
                            num = min(int(content.split(maxsplit=1)[0]), 15)
                        except ValueError:
                            num = 1

                    if num > 1:
                        if time.time() < self.mod_cooldowns[message.channel.name].get(link, 0):
                            return
                        self.mod_cooldowns[message.channel.name][link] = time.time() + 2.5

                    for i in range(num):
                        await message.channel.send(text)
                        await asyncio.sleep(0.1)
                elif not private and time.time() > self.cooldowns[message.channel.name].get(link, 0):
                    ctx = await self.bot.get_context(message)
                    await ctx.reply(text)
                    self.cooldowns[message.channel.name][link] = time.time() + 2.5

    @commands.command(
        name='link',
        aliases=['links', 'del', 'public', 'aliases'],
        cooldown={'per': 0, 'gen': 3},
        description='Создание кастомных команд-ссылок.'
    )
    async def link(self, ctx):
        if not (ctx.channel.bot_is_vip or ctx.channel.bot_is_mod):
            await ctx.reply('Боту необходима випка или модерка для работы этой команды')
            return

        key = {'channel': ctx.channel.name}
        if ctx.command_alias == 'links':
            if self.links.get(ctx.channel.name, None):
                message = f'Доступные ссылки: {self.bot._prefix}{str(" " + self.bot._prefix).join(self.links[ctx.channel.name])}'
                await ctx.reply(message)
            else:
                await ctx.reply('На вашем канале ещё нет ссылок')
            return
        elif ctx.command_alias == 'public':
            if (content := ctx.content.lower()) in ('on', 'off'):
                values = {'$unset': {'links.$[].private': ''}}
                if content == 'on':
                    values['$set'] = {'private': False}
                    message = 'Теперь ссылки могут быть вызваны любыми участниками чата'
                else:
                    values['$set'] = {'private': True}
                    message = 'Теперь ссылки могут быть вызваны только модераторами'
            else:
                await ctx.reply('Напишите on или off, чтобы сделать ссылки публичными или приватными')
                return
        elif ctx.command_alias == 'del':
            content = ctx.content.split()
            if not content:
                await ctx.reply(f'Пустой ввод - {self.bot._prefix}help link')
                return

            link = content[0].lower()
            if link in self.links.get(ctx.channel.name, []) or (link := self.links_aliases.get(ctx.channel.name, {}).get(link, '')):
                values = {'$pull': {'links': {'name': link}}}
                self.links[ctx.channel.name].remove(link)
                if self.links_aliases.get(ctx.channel.name, {}):
                    self.links_aliases[ctx.channel.name] = {alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if name != link}
                self.cooldowns.get(ctx.channel.name, {}).pop(link, None)

                cog = self.bot.get_cog('Timer')
                if link in cog.timers.get(ctx.channel.name, []):
                    await db.timers.update_one(key, {'$pull': {'timers': {'link': link}}})
                    message = f'Удалены ссылка и таймер {self.bot._prefix}{link}'
                    del cog.timers[ctx.channel.name][link]
                else:
                    message = f'Удалено {self.bot._prefix}{link}'
            else:
                await ctx.reply('Ссылка не найдена')
                return
        elif ctx.command_alias == 'aliases':
            content = ctx.content.lower().split()
            if len(content) < 1:
                await ctx.reply('Напишите элиасы к команде через пробел')
                return

            link = content[0].lower().lstrip(self.bot._prefix)
            aliases = set()

            if link in self.links.get(ctx.channel.name, []):
                for alias in content[1:]:
                    alias = alias.lstrip(self.bot._prefix)
                    if self.bot.get_command_name(alias) or alias in ['public', 'private']:
                        await ctx.reply(f'Нельзя создать ссылку с таким названием - {alias}')
                        return
                    elif alias in self.links.get(ctx.channel.name, []):
                        await ctx.reply(f'Нельзя указывать названия ссылок в элиасах - {alias}')
                        return
                    elif self.links_aliases.get(ctx.channel.name, {}).get(alias, link) != link:
                        await ctx.reply(f'Нельзя указывать элиасы существующих ссылок - {alias}')
                        return
                    elif len(alias) > 15:
                        await ctx.reply(f'Нельзя создать элиас длиной более 15 символов - {alias}')
                        return
                    aliases.add(alias)
            elif link := self.links_aliases.get(ctx.channel.name, {}).get(link, ''):
                await ctx.reply(f'Ссылка не найдена, возможно вы имели в виду {self.bot._prefix}{link}')
                return
            else:
                await ctx.reply('Ссылка не найдена')
                return

            key['links.name'] = link
            if len(aliases) > 5:
                await ctx.reply('Максимальное количество элиасов к ссылке - 5')
                return

            if aliases:
                values = {'$set': {'links.$.aliases': list(aliases)}}
                message = f'Обновлены элиасы {self.bot._prefix}{link}'
                for alias in aliases:
                    self.links_aliases[ctx.channel.name][alias] = link
            else:
                values = {'$unset': {'links.$.aliases': ''}}
                message = f'Удалены элиасы {self.bot._prefix}{link}'
                self.links_aliases[ctx.channel.name] = {alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if name != link}
        else:
            content = ctx.content.split()
            if len(content) < 2:
                await ctx.reply(f'Пустой ввод - {self.bot._prefix}help link')
                return
            elif len(self.links.get(ctx.channel.name, [])) == 40:
                await ctx.reply('Достигнут лимит количества ссылок - 40')
                return

            link = content[0].lower().lstrip(self.bot._prefix)

            private = None
            if content[1].lower() == 'private':
                private = True
            elif content[1].lower() == 'public':
                private = False

            if self.bot.get_command_name(link) or link in ['public', 'private']:
                await ctx.reply(f'Нельзя создать ссылку с таким названием - {link}')
                return
            elif '.' in link or '$' in link:
                await ctx.reply('Нельзя создать ссылку с точкой или $ в названии')
                return
            elif len(link) > 15:
                await ctx.reply('Нельзя создать ссылку с названием длиной более 15 символов')
                return

            offset = 0
            if private is not None:
                offset = 1

            text = None
            if content[1 + offset:]:
                announcements = ['announceblue', 'announcegreen', 'announceorange', 'announcepurple']
                text = ' '.join(content[1 + offset:])
                for announcement in announcements:
                    text = text.replace(announcement, 'announce')

            if name := self.links_aliases.get(ctx.channel.name, {}).get(link, ''):
                link = name

            if not (text or link in self.links.get(ctx.channel.name, [])):
                await ctx.reply(f'Пустой ввод - {self.bot._prefix}help link')
                return

            if ctx.channel.name in self.links:
                if link in self.links[ctx.channel.name]:
                    message = f'Изменено {self.bot._prefix}{link}'
                    key['links.name'] = link
                    values = {'$set': {}}
                    if private is not None:
                        values['$set']['links.$.private'] = private
                    if text:
                        values['$set']['links.$.text'] = text
                else:
                    message = f'Добавлено {self.bot._prefix}{link}'
                    self.links[ctx.channel.name].add(link)
                    values = {'$addToSet': {'links': {'name': link, 'text': text}}}
                    if private is not None:
                        values['$addToSet']['links']['private'] = private
            else:
                message = f'Добавлено {self.bot._prefix}{link}'
                self.links[ctx.channel.name] = {link}
                values = {'$setOnInsert': {'channel': ctx.channel.name, 'private': True},
                          '$addToSet': {'links': {'name': link, 'text': text}}}
                if private is not None:
                    values['$addToSet']['links']['private'] = private

        await db.links.update_one(key, values, upsert=True)
        await ctx.reply(message)

    @routines.routine(iterations=1)
    async def get_links(self):
        async for document in db.links.find():
            self.links[document['channel']] = {link['name'] for link in document['links']}
            self.links_aliases[document['channel']] = {alias: link['name'] for link in document['links'] if 'aliases' in link for alias in link['aliases']}
            self.cooldowns[document['channel']] = {}
            self.mod_cooldowns[document['channel']] = {}


def prepare(bot):
    bot.add_cog(Link(bot))
