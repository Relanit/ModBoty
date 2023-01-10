import asyncio
import time

from twitchio.ext.commands import Cog, command, Context
from twitchio import Message

from config import db


def conv(n: int) -> str:
    """Converts a number to an ending for the word 'элиас' in Russian"""
    endings = ["а", "ов", ""]
    n %= 100
    if 5 <= n <= 20:
        s = endings[1]
    else:
        i = n % 10
        if i == 1:
            s = endings[2]
        elif i in [2, 3, 4]:
            s = endings[0]
        else:
            s = endings[1]
    return s


class Links(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.links: dict[str, list[str]] = {}
        self.links_aliases: dict[str, dict[str, str]] = {}
        self.cooldowns: dict[str, dict[str, float]] = {}
        self.mod_cooldowns: dict[str, float] = {}

    async def __ainit__(self):
        async for document in db.links.find():
            self.links[document["channel"]] = [link["name"] for link in document["links"]]
            self.links_aliases[document["channel"]] = {
                alias: link["name"] for link in document["links"] if "aliases" in link for alias in link["aliases"]
            }
            self.cooldowns[document["channel"]] = {link["name"]: {"per": {}, "gen": 0} for link in document["links"]}
            self.mod_cooldowns[document["channel"]] = 0

    @Cog.event()
    async def event_message(self, message: Message):
        if message.echo:
            return

        content = message.content
        reply = ""
        if message.content.startswith("@"):
            reply, content = (
                message.content.split(maxsplit=1)
                if len(message.content.split(maxsplit=1)) > 1
                else ("", message.content)
            )

        if content.startswith(self.bot.prefix):
            content = content.lstrip(self.bot.prefix).lower()
            if not content:
                return

            link = content.split(maxsplit=1)[0]

            if link := self.get_link_name(message.channel.name, link):
                if not message.author.is_mod and (
                    time.time() < self.cooldowns[message.channel.name][link]["gen"]
                    or time.time() < self.cooldowns[message.channel.name][link]["per"].get(message.author.name, 0)
                ):
                    return

                data = await db.links.find_one(
                    {"channel": message.channel.name, "links.name": link},
                    {"private": 1, "announce": 1, "links.$": 1},
                )
                private = data["private"] if "private" not in data["links"][0] else data["links"][0]["private"]
                text = data["links"][0]["text"]

                if message.author.is_mod or message.author.name == self.bot.admin:
                    content, announce = " ".join(content.split()[1:3]), ""

                    if {"а", "a", "ф", "f"} & set(content):
                        content = (
                            content.replace("a", " ").replace("а", " ").replace("ф", " ").replace("f", " ").strip(" ")
                        )
                        announce = data["links"][0].get("announce") or data["announce"]

                    num = 1
                    if content:
                        try:
                            num = min(int(content.split(maxsplit=1)[0]), 15)
                        except ValueError:
                            num = 1

                    if num > 2:
                        if time.time() < self.mod_cooldowns[message.channel.name]:
                            return

                        self.mod_cooldowns[message.channel.name] = time.time() + 3
                        cooldown = max(data["links"][0].get("cooldown", {"gen": 5})["gen"], 5)
                        self.cooldowns[message.channel.name][link]["gen"] = time.time() + cooldown
                    elif time.time() < self.cooldowns[message.channel.name][link]["gen"] - 1:
                        return
                    else:
                        self.cooldowns[message.channel.name][link]["gen"] = (
                            time.time() + data["links"][0].get("cooldown", {"gen": 3})["gen"]
                        )

                    if not announce and not text.startswith("/announce") and not text.startswith(".announce"):
                        text = f"{reply} {text}" if reply and num == 1 else text
                        for _ in range(num):
                            await message.channel.send(text)
                            await asyncio.sleep(0.1)
                    else:
                        if text.startswith("/me") or text.startswith(".me"):
                            text = text.split(maxsplit=1)[1]
                        await self.bot.announce(message.channel, text, announce, num)

                elif not private:
                    cooldown = data["links"][0].get("cooldown", {"per": 0, "gen": 3})
                    (
                        self.cooldowns[message.channel.name][link]["per"][message.author.name],
                        self.cooldowns[message.channel.name][link]["gen"],
                    ) = (time.time() + cooldown["per"], time.time() + cooldown["gen"])

                    if text.startswith("/announce") or text.startswith(".announce"):
                        text = text.split(maxsplit=1)[1]

                    if reply:
                        await message.channel.send(f"{reply} {text}")
                    else:
                        ctx = await self.bot.get_context(message)
                        await ctx.reply(text)

    @command(
        name="link",
        aliases=["links", "del", "aliases", "public", "announce", "linkcd"],
        cooldown={"per": 0, "gen": 3},
        description="Кастомные команды для спама (от модераторов) или вызова пользователями. Полное описание  ‒  https://vk.cc/chCfKt ",
        flags=["bot-vip"],
    )
    async def command(self, ctx: Context):
        if ctx.command_alias != "link" and not self.links.get(ctx.channel.name, None):
            await ctx.reply("На вашем канале ещё нет команд")
            return

        if ctx.command_alias == "link":
            await self.link(ctx)
        elif ctx.command_alias == "links":
            await self.view_links(ctx)
        elif ctx.command_alias == "del":
            await self.delete(ctx)
        elif ctx.command_alias == "aliases":
            await self.aliases(ctx)
        elif ctx.command_alias == "public":
            await self.public(ctx)
        elif ctx.command_alias == "announce":
            await self.announce(ctx)
        else:
            await self.linkcd(ctx)

    async def link(self, ctx: Context):
        content = ctx.content.split()
        if len(content) < 2:
            await ctx.reply("Недостаточно значений ‒ https://vk.cc/chCfKt")
            return

        link = content[0].lower().lstrip(self.bot.prefix)
        found = self.get_link_name(ctx.channel.name, link)

        if len(self.links.get(ctx.channel.name, [])) == 40 and not found:
            await ctx.reply("Достигнут лимит количества команд ‒ 40")
            return

        link = found or link

        if not found:
            StreamInfo = self.bot.cogs["StreamInfo"]
            if link in StreamInfo.aliases.get(ctx.channel.name, []):
                name = StreamInfo.games[ctx.channel.name][StreamInfo.aliases[ctx.channel.name][link]]
                await ctx.reply(f"Название {self.bot.prefix}{link} уже занято категорией {name}")
                return
            if self.bot.get_command_name(link):
                await ctx.reply(f"Название {self.bot.prefix}{link} уже занято командой бота")
                return
            elif len(link) > 30:
                await ctx.reply("Нельзя создать команду с названием длиной более 30 символов")
                return

        text = " ".join(content[1:])

        if not text or ((text.startswith(".") or text.startswith("/")) and len(text.split()) == 1):
            await ctx.reply("Недостаточно значений ‒ https://vk.cc/chCfKt")
            return

        key = {"channel": ctx.channel.name}
        if ctx.channel.name in self.links:
            if found:
                message = f"Изменено {self.bot.prefix}{link}"
                key["links.name"] = link
                values = {"$set": {"links.$.text": text}}
            else:
                message = f"Добавлено {self.bot.prefix}{link}"
                self.links[ctx.channel.name].append(link)
                self.cooldowns[ctx.channel.name][link] = {"per": {}, "gen": 0}
                values = {"$addToSet": {"links": {"name": link, "text": text}}}

        else:
            message = f"Добавлено {self.bot.prefix}{link}"
            self.links[ctx.channel.name] = [link]
            self.cooldowns[ctx.channel.name] = {link: {"per": {}, "gen": 0}}
            self.mod_cooldowns[ctx.channel.name] = 0
            values = {
                "$setOnInsert": {
                    "channel": ctx.channel.name,
                    "private": False,
                    "announce": "primary",
                },
                "$addToSet": {"links": {"name": link, "text": text}},
            }

        await db.links.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def view_links(self, ctx: Context):
        def truncate(content, length=450, suffix="..."):
            if len(content) <= length:
                return content, ""
            else:
                return (
                    content[:length].rsplit(" ", 1)[0] + suffix,
                    content[:length].rsplit(" ", 1)[1] + content[length:],
                )

        links = await db.links.find_one({"channel": ctx.channel.name}, {"links": 1, "private": 1})
        if not ctx.content:
            message, message2 = truncate(
                f'Доступные команды: {self.bot.prefix}{str(f" {self.bot.prefix}").join(self.links[ctx.channel.name])}'
            )

        elif ctx.content.lower() == "public":
            links = [link["name"] for link in links["links"] if not link.get("private", links["private"])]
            message, message2 = truncate(
                f'Публичные команды: {self.bot.prefix}{str(f" {self.bot.prefix}").join(links)}'
                if links
                else "Публичные команды отсутствуют"
            )

        elif ctx.content.lower() == "private":
            links = [link["name"] for link in links["links"] if link.get("private", links["private"])]
            message, message2 = truncate(
                f'Приватные команды: {self.bot.prefix}{str(f" {self.bot.prefix}").join(links)}'
                if links
                else "Приватные команды отсутствуют"
            )

        else:
            message, message2 = "Неверный ввод ‒ https://vk.cc/chCfKt", ""

        await ctx.reply(message)
        if message2:
            await ctx.reply(message2)

    async def delete(self, ctx: Context):
        content = ctx.content.split()
        if not content:
            await ctx.reply("Недостаточно значений ‒ https://vk.cc/chCfKt")
            return

        link = content[0].lower().lstrip(self.bot.prefix)
        if link := self.get_link_name(ctx.channel.name, link):
            self.links[ctx.channel.name].remove(link)

            if self.links_aliases.get(ctx.channel.name, {}):
                self.links_aliases[ctx.channel.name] = {
                    alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if name != link
                }  # remove aliases of link

            self.cooldowns.get(ctx.channel.name, {}).pop(link, None)
            Timers = self.bot.cogs["Timers"]

            if link in Timers.timers.get(ctx.channel.name, []):
                await db.timers.update_one({"channel": ctx.channel.name}, {"$pull": {"timers": {"link": link}}})
                message = f"Удалены команда и таймер {self.bot.prefix}{link}"
                del Timers.timers[ctx.channel.name][link]
            else:
                message = f"Удалено {self.bot.prefix}{link}"
        else:
            await ctx.reply("Команда не найдена")
            return

        await db.links.update_one({"channel": ctx.channel.name}, {"$pull": {"links": {"name": link}}})
        await ctx.reply(message)

    async def aliases(self, ctx: Context):
        content = [word.lstrip(self.bot.prefix) for word in ctx.content.lower().split()]
        if len(content) == 1:
            if not (link := self.get_link_name(ctx.channel.name, content[0])):
                await ctx.reply("Команда не найдена")
                return

            data = await db.links.find_one(
                {"channel": ctx.channel.name},
                {"links": {"$elemMatch": {"name": link}}, "private": 1},
            )

            aliases = data["links"][0].get("aliases", [])

            if aliases:
                aliases = f"{', '.join(aliases)}"

            message = f'Название ‒ {link}{f", элиасы ‒ {aliases}" if aliases else ""}'
            await ctx.reply(message)
            return

        if len(content) < 3 and content[1] == "add" or len(content) < 2:
            await ctx.reply("Напишите название команды, действие (add или del) и элиасы через пробел")
            return

        link, action, aliases = content[0], content[1], set(content[2:]) if len(content) > 2 else []

        if (link := self.get_link_name(ctx.channel.name, link)) and action != "add" and link != content[0]:
            await ctx.reply(f'Команда "{content[0]}" не найдена, возможно вы имели в виду "{link}"')
            return

        if not link:
            await ctx.reply(f'Команда "{content[0]}" не найдена')
            return

        if action not in ("add", "del"):
            await ctx.reply("Напишите название команды, действие (add или del) и элиасы через пробел")
            return

        current_aliases = {
            alias
            for alias in self.links_aliases[ctx.channel.name]
            if self.links_aliases[ctx.channel.name][alias] == link
        }

        if not current_aliases and action == "del":
            await ctx.reply(f"У команды {link} нет элиасов")
            return

        if action == "add":
            if len(aliases) + len(current_aliases) > 5:
                await ctx.reply(
                    f"Максимальное количество элиасов к команде ‒ 5. "
                    f'У команды "{link}" на данный момент {len(current_aliases)} элиас{conv(len(current_aliases))}: '
                    f'{", ".join(current_aliases)}'
                )
                return

            StreamInfo = self.bot.cogs["StreamInfo"]
            for alias in aliases:
                if alias in current_aliases:
                    await ctx.reply(f'Элиас "{alias}" уже есть у данной команды')
                    return
                if self.bot.get_command_name(alias):
                    await ctx.reply(f'Элиас "{alias}" уже занят командой бота')
                    return
                if alias in StreamInfo.aliases.get(ctx.channel.name, []):
                    name = StreamInfo.games[ctx.channel.name][StreamInfo.aliases[ctx.channel.name][alias]]
                    await ctx.reply(f'Элиас "{alias}" уже занят категорией {name}')
                    return
                if alias in self.links.get(ctx.channel.name, []):
                    await ctx.reply(f'Элиас "{alias}" уже занят командой с таким названием')
                    return
                if self.links_aliases.get(ctx.channel.name, {}).get(alias, link) != link:
                    await ctx.reply(f'У другой команды уже есть элиас "{alias}"')
                    return
                if len(alias) > 30:
                    await ctx.reply(f"Нельзя создать элиас длиной более 30 символов ‒ {self.bot.prefix}{alias}")
                    return

            values = {"$push": {"links.$.aliases": {"$each": list(aliases)}}}
            message = f"Обновлены элиасы {self.bot.prefix}{link}"

            if ctx.channel.name not in self.links_aliases:
                self.links_aliases[ctx.channel.name] = {}

            for alias in aliases:
                self.links_aliases[ctx.channel.name][alias] = link
        elif aliases:
            found, not_found = current_aliases & aliases, aliases - current_aliases

            if not found:
                await ctx.reply("Указанные элиасы не найдены" if len(aliases) > 1 else "Указанный элиас не найден")
                return

            join = f", {self.bot.prefix}"

            phrase1 = "Удалены элиасы" if len(found) > 1 else "Удалён элиас"
            phrase2 = "не найдены элиасы" if len(not_found) > 1 else "не найден элиас"

            message = (
                f"{phrase1} {self.bot.prefix}{join.join(found)} "
                f"команды {self.bot.prefix}{link}{f', {phrase2} {self.bot.prefix}{join.join(not_found)}' if not_found else ''} "
            )

            values = {"$pull": {"links.$.aliases": {"$in": list(found)}}}
            self.links_aliases[ctx.channel.name] = {
                alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if alias not in found
            }

        else:
            values = {"$unset": {"links.$.aliases": ""}}
            message = f"Удалены элиасы {self.bot.prefix}{link}"
            self.links_aliases[ctx.channel.name] = {
                alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if name != link
            }
        await db.links.update_one({"channel": ctx.channel.name, "links.name": link}, values)
        await ctx.reply(message)

    async def public(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Недостаточно значений ‒ https://vk.cc/chCfKt")
            return

        try:
            content_split = ctx.content.lower().lstrip(self.bot.prefix).split()
            link, action = content_split

            if not (link := self.get_link_name(ctx.channel.name, link)):
                await ctx.reply(f"Команда {self.bot.prefix}{content_split[0]} не найдена")
                return

            if action not in ("on", "off"):
                await ctx.reply(
                    "Ошибка, напишите название/элиас команды и on/off, чтобы сделать команду публичной/приватной"
                )
                return

            key = {"channel": ctx.channel.name, "links.name": link}
        except ValueError:
            action = ctx.content.lower()

            if action not in ("on", "off"):
                await ctx.reply("Ошибка, напишите on/off, чтобы сделать команды публичными/приватными")
                return

            link = None
            key = {"channel": ctx.channel.name}

        if not link:
            values = {}
            if action == "on":
                values["$set"] = {"private": False}
                message = "Теперь команды могут быть вызваны любыми участниками чата"
            else:
                values["$set"] = {"private": True}
                message = "Теперь команды могут быть вызваны только модераторами"
        else:
            values = {"$set": {"links.$.private": action == "off"}}
            message = f"Теперь команда {self.bot.prefix}{link} может быть вызвана {'только модераторами' if action == 'off' else 'всеми участниками чата'}"

        await db.links.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def announce(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Недостаточно значений  ‒  https://vk.cc/ciVrFK")
            return

        content_split = ctx.content.lower().split()
        link = content_split[0]

        values = {}
        key = {"channel": ctx.channel.name}

        if link := self.get_link_name(ctx.channel.name, link):
            if len(content_split) == 2:
                color = content_split[1]

                if color not in ["blue", "green", "orange", "purple", "primary"]:
                    await ctx.reply("Неверный цвет, доступные цвета: blue, green, orange, purple, primary")
                    return

                values["$set"] = {"links.$.announce": color}
                message = f"Изменён цвет announce для {self.bot.prefix}{link}"

            else:
                message = f"Сброшен цвет announce для {self.bot.prefix}{link}"
                values["$unset"] = {"links.$.announce": 1}
            key["links.name"] = link

        elif ctx.content.lower() in ["blue", "green", "orange", "purple", "primary"]:
            values["$set"] = {"announce": ctx.content.lower()}
            message = "Изменён цвет announce"
        elif len(content_split) == 1:
            await ctx.reply("Неверный цвет, доступные цвета: blue, green, orange, purple, primary")
            return
        else:
            await ctx.reply(f"Команда {self.bot.prefix}{content_split[0]} не найдена")
            return

        await db.links.update_one(key, values)
        await ctx.reply(message)

    async def linkcd(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Недостаточно значений ‒ https://vk.cc/chCfKt")
            return

        content_split = ctx.content.replace(self.bot.prefix, "").lower().split()

        try:
            link, per, gen = content_split
            per, gen = int(per), int(gen)
        except ValueError:
            await ctx.reply("Введите название команды, личный и общий кд в виде целого числа")
            return

        if not (link := self.get_link_name(ctx.channel.name, link)):
            await ctx.reply(f'Команда "{content_split[0]}" не найдена')
            return

        if gen < 3:
            await ctx.reply("Общий кд не может быть меньше 3 секунд")
            return

        key = {"channel": ctx.channel.name, "links.name": link}
        values = {"$set": {"links.$.cooldown": {"per": per, "gen": gen}}}
        await db.links.update_one(key, values)
        await ctx.reply(f"Изменён кд команды {self.bot.prefix}{link}")

    def get_link_name(self, channel: str, alias: str) -> str | None:
        """Retrieves link name if found"""
        if alias in self.links.get(channel, []):
            return alias
        elif alias in self.links_aliases.get(channel, []):
            return self.links_aliases[channel][alias]
        return


def prepare(bot):
    bot.add_cog(Links(bot))
    bot.loop.run_until_complete(bot.cogs["Links"].__ainit__())
