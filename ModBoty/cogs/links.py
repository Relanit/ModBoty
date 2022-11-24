import asyncio
import time

from twitchio.ext.commands import Cog, command, Context
from twitchio import Message

from config import db


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
            self.cooldowns[document["channel"]] = {}
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
            content = content.lstrip(self.bot.prefix)
            if not content:
                return

            link = content.split(maxsplit=1)[0].lower()

            if link := self.get_link_name(message.channel.name, link):
                if (
                    (
                        (message.author.is_mod or message.author.name == self.bot.admin)
                        and time.time() < self.cooldowns[message.channel.name].get(link, 0) - 2
                    )
                    or not message.author.is_mod
                    and time.time() < self.cooldowns[message.channel.name].get(link, 0)
                ):
                    return

                data = await db.links.find_one(
                    {"channel": message.channel.name, "links.name": link},
                    {"private": 1, "announce": 1, "links.$": 1},
                )
                private = data["private"] if "private" not in data["links"][0] else data["links"][0]["private"]
                text = data["links"][0]["text"]

                if message.author.is_mod or message.author.name == self.bot.admin:
                    content = " ".join(content.split()[1:3])
                    announce = ""

                    if "a" in content or "а" in content:
                        content = content.replace("a", " ").replace("а", " ").strip(" ")
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
                        self.cooldowns[message.channel.name][link] = time.time() + 5
                    elif time.time() < self.cooldowns[message.channel.name].get(link, 0) - 2:
                        return
                    else:
                        self.cooldowns[message.channel.name][link] = time.time() + 3

                    if not announce and not text.startswith("/announce") and not text.startswith(".announce"):
                        text = f"{reply} {text}" if reply and num == 1 else text
                        for _ in range(num):
                            await message.channel.send(text)
                            await asyncio.sleep(0.1)
                    else:
                        if text.startswith("/me") or text.startswith(".me"):
                            text = text.split(maxsplit=1)[1]
                        await self.bot.announce(message.channel, text, announce, num)

                elif not private and time.time() > self.cooldowns[message.channel.name].get(link, 0):
                    self.cooldowns[message.channel.name][link] = time.time() + 3

                    if text.startswith("/announce") or text.startswith(".announce"):
                        text = text.split(maxsplit=1)[1]

                    if reply:
                        await message.channel.send(f"{reply} {text}")
                    else:
                        ctx = await self.bot.get_context(message)
                        await ctx.reply(text)

    @command(
        name="link",
        aliases=["links", "del", "aliases", "public", "announce"],
        cooldown={"per": 0, "gen": 3},
        description="Кастомные команды для спама (от модераторов) или вызова пользователями. Полное описание - https://vk.cc/chCfKt ",
        flags=["bot-vip"],
    )
    async def command(self, ctx: Context):
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
        else:
            await self.announce(ctx)

    async def link(self, ctx: Context):
        content = ctx.content.split()
        if len(content) < 2:
            await ctx.reply("Недостаточно значений - https://vk.cc/chCfKt")
            return

        link = content[0].lower().lstrip(self.bot.prefix)
        found = self.get_link_name(ctx.channel.name, link)

        if len(self.links.get(ctx.channel.name, [])) == 40 and not found:
            await ctx.reply("Достигнут лимит количества ссылок - 40")
            return

        link = found or link

        private = None
        if content[1].lower() == "private":
            private = True
        elif content[1].lower() == "public":
            private = False

        if not found:
            cog = self.bot.get_cog("StreamInfo")
            if link in cog.aliases.get(ctx.channel.name, []):
                name = cog.games[ctx.channel.name][cog.aliases[ctx.channel.name][link]]
                await ctx.reply(f"Название {self.bot.prefix}{link} уже занято категорией {name}")
                return
            if self.bot.get_command_name(link) or link in ["public", "private"]:
                await ctx.reply(f"Название {self.bot.prefix}{link} уже занято командой бота")
                return
            elif len(link) > 15:
                await ctx.reply("Нельзя создать ссылку с названием длиной более 15 символов")
                return

        offset = 1 if private is not None else 0
        text = " ".join(content[1 + offset :]) if content[1 + offset :] else ""

        if not (text or found) or ((text.startswith(".") or text.startswith("/")) and len(text.split()) == 1):
            await ctx.reply("Недостаточно значений - https://vk.cc/chCfKt")
            return

        key = {"channel": ctx.channel.name}
        if ctx.channel.name in self.links:
            if found:
                message = f"Изменено {self.bot.prefix}{link}"
                key["links.name"] = link
                values = {"$set": {}}
                if private is not None:
                    values["$set"]["links.$.private"] = private
                if text:
                    values["$set"]["links.$.text"] = text
            else:
                message = f"Добавлено {self.bot.prefix}{link}"
                self.links[ctx.channel.name].append(link)
                values = {"$addToSet": {"links": {"name": link, "text": text}}}
                if private is not None:
                    values["$addToSet"]["links"]["private"] = private
        else:
            message = f"Добавлено {self.bot.prefix}{link}"
            self.links[ctx.channel.name] = [link]
            self.cooldowns[ctx.channel.name] = {link: 0}
            self.mod_cooldowns[ctx.channel.name] = 0
            values = {
                "$setOnInsert": {
                    "channel": ctx.channel.name,
                    "private": False,
                    "announce": "primary",
                },
                "$addToSet": {"links": {"name": link, "text": text}},
            }
            if private is not None:
                values["$addToSet"]["links"]["private"] = private

        await db.links.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def view_links(self, ctx: Context):
        if not self.links.get(ctx.channel.name, None):
            await ctx.reply("На вашем канале ещё нет ссылок")
            return

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
                f'Доступные ссылки: {self.bot.prefix}{str(f" {self.bot.prefix}").join(self.links[ctx.channel.name])}'
            )

        elif ctx.content.lower() == "public":
            links = [link["name"] for link in links["links"] if not link.get("private", links["private"])]
            message, message2 = truncate(
                f'Публичные ссылки: {self.bot.prefix}{str(f" {self.bot.prefix}").join(links)}'
                if links
                else "Публичные ссылки отсутствуют"
            )

        elif ctx.content.lower() == "private":
            links = [link["name"] for link in links["links"] if link.get("private", links["private"])]
            message, message2 = truncate(
                f'Приватные ссылки: {self.bot.prefix}{str(f" {self.bot.prefix}").join(links)}'
                if links
                else "Приватные ссылки отсутствуют"
            )

        else:
            message, message2 = "Неверный ввод - https://vk.cc/chCfKt", ""

        await ctx.reply(message)
        if message2:
            await ctx.reply(message2)

    async def delete(self, ctx: Context):
        content = ctx.content.split()
        if not content:
            await ctx.reply("Недостаточно значений - https://vk.cc/chCfKt")
            return

        link = content[0].lower().lstrip(self.bot.prefix)
        if link := self.get_link_name(ctx.channel.name, link):
            self.links[ctx.channel.name].remove(link)

            if self.links_aliases.get(ctx.channel.name, {}):
                self.links_aliases[ctx.channel.name] = {
                    alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if name != link
                }  # remove aliases of link

            self.cooldowns.get(ctx.channel.name, {}).pop(link, None)
            cog = self.bot.get_cog("Timers")

            if link in cog.timers.get(ctx.channel.name, []):
                await db.timers.update_one({"channel": ctx.channel.name}, {"$pull": {"timers": {"link": link}}})
                message = f"Удалены ссылка и таймер {self.bot.prefix}{link}"
                del cog.timers[ctx.channel.name][link]
            else:
                message = f"Удалено {self.bot.prefix}{link}"
        else:
            await ctx.reply("Ссылка не найдена")
            return

        await db.links.update_one({"channel": ctx.channel.name}, {"$pull": {"links": {"name": link}}})
        await ctx.reply(message)

    async def aliases(self, ctx: Context):
        content = ctx.content.lower().split()
        if len(content) < 1:
            await ctx.reply("Напишите элиасы к команде через пробел")
            return

        link = content[0].lower().lstrip(self.bot.prefix)
        aliases = set()

        if link in self.links.get(ctx.channel.name, []):
            cog = self.bot.get_cog("StreamInfo")
            for alias in content[1:]:
                alias = alias.lstrip(self.bot.prefix)
                if self.bot.get_command_name(alias) or alias == "private":
                    await ctx.reply(f"Название {self.bot.prefix}{alias} уже занято командой")
                    return
                if alias in cog.aliases.get(ctx.channel.name, []):
                    name = cog.games[ctx.channel.name][cog.aliases[ctx.channel.name][alias]]
                    await ctx.reply(f"Название {self.bot.prefix}{alias} уже занято категорией {name}")
                    return
                if alias in self.links.get(ctx.channel.name, []):
                    await ctx.reply(f"Нельзя указывать названия существующих ссылок - {self.bot.prefix}{alias}")
                    return
                if self.links_aliases.get(ctx.channel.name, {}).get(alias, link) != link:
                    await ctx.reply(f"Нельзя указывать элиасы существующих ссылок - {self.bot.prefix}{alias}")
                    return
                if len(alias) > 15:
                    await ctx.reply(f"Нельзя создать элиас длиной более 15 символов - {self.bot.prefix}{alias}")
                    return
                aliases.add(alias)
        elif link := self.get_link_name(ctx.channel.name, link):
            await ctx.reply(f"Ссылка не найдена, возможно вы имели в виду {self.bot.prefix}{link}")
            return
        else:
            await ctx.reply("Ссылка не найдена")
            return

        if len(aliases) > 5:
            await ctx.reply("Максимальное количество элиасов к ссылке - 5")
            return

        if aliases:
            values = {"$set": {"links.$.aliases": list(aliases)}}
            message = f"Обновлены элиасы {self.bot.prefix}{link}"

            if ctx.channel.name not in self.links_aliases:
                self.links_aliases[ctx.channel.name] = {}

            self.links_aliases[ctx.channel.name] = {
                alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if name != link
            }

            for alias in aliases:
                self.links_aliases[ctx.channel.name][alias] = link
        else:
            values = {"$unset": {"links.$.aliases": ""}}
            message = f"Удалены элиасы {self.bot.prefix}{link}"
            self.links_aliases[ctx.channel.name] = {
                alias: name for alias, name in self.links_aliases[ctx.channel.name].items() if name != link
            }

        await db.links.update_one({"channel": ctx.channel.name, "links.name": link}, values)
        await ctx.reply(message)

    @staticmethod
    async def public(ctx: Context):
        if (content := ctx.content.lower()) in ("on", "off"):
            values = {}
            if content == "on":
                values["$set"] = {"private": False}
                message = "Теперь ссылки могут быть вызваны любыми участниками чата"
            elif content == "off":
                values["$set"] = {"private": True}
                message = "Теперь ссылки могут быть вызваны только модераторами"
            else:
                await ctx.reply("Ошибка, Напишите on или off, чтобы сделать ссылки публичными или приватными")
                return
        else:
            await ctx.reply("Напишите on или off, чтобы сделать ссылки публичными или приватными")
            return

        await db.links.update_one({"channel": ctx.channel.name}, values, upsert=True)
        await ctx.reply(message)

    async def announce(self, ctx: Context):
        if not self.links.get(ctx.channel.name, None):
            await ctx.reply("На вашем канале ещё нет ссылок")
            return

        if not ctx.content:
            await ctx.reply("Недостаточно значений - https://vk.cc/ciVrFK")
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
