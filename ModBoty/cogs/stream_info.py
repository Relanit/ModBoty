import difflib
import time
from typing import Optional

import twitchio
from twitchio.ext.commands import Cog, command, Context
from twitchio.models import Game
from twitchio import Message, User

from config import db, fernet


def similarity(s1: str, s2: str) -> float:
    """Return a measure of the strings' similarity (float in [0,1])."""
    matcher = difflib.SequenceMatcher(None, s1, s2)
    return matcher.ratio()


class StreamInfo(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games: dict[str, dict[int, str]] = {}
        self.aliases: dict[str, dict[str, int]] = {}
        self.cooldowns: dict[str, float] = {}

    async def __ainit__(self):
        async for document in db.games.find():
            self.aliases[document["channel"]] = {
                alias: game["id"] for game in document["games"] for alias in game["aliases"]
            }
            self.games[document["channel"]] = {game["id"]: game["name"] for game in document["games"]}
            self.cooldowns[document["channel"]] = 0

    @Cog.event()
    async def event_message(self, message: Message):
        if message.echo:
            return

        if message.content.startswith(self.bot.prefix):
            content = message.content.lstrip(self.bot.prefix).lower()
            if not content:
                return

            alias = content.split(maxsplit=1)[0].lower()

            if (
                alias in self.aliases.get(message.channel.name, {})
                and (message.author.is_mod or message.author.name == self.bot.admin)
                and time.time() - self.cooldowns[message.channel.name] > 3
            ):
                data = await db.config.find_one(
                    {"_id": 1, "user_tokens.login": message.channel.name},
                    {"user_tokens.$": 1},
                )
                ctx = await self.bot.get_context(message)

                if not data:
                    await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
                    return

                channel = await ctx.channel.user()
                token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()
                game_id = self.aliases[message.channel.name][alias]
                game = Game({"id": game_id, "name": self.games[ctx.channel.name][game_id], "box_art_url": ""})
                self.cooldowns[message.channel.name] = time.time() + 3
                await self.g(ctx, channel, token, game)

    @command(
        name="t",
        aliases=["g", "addg", "delg", "games"],
        cooldown={"per": 0, "gen": 3},
        description="Изменение настроек стрима. Полное описание - https://vk.cc/ciaLzx",
    )
    async def command(self, ctx: Context):
        if not ctx.content:
            if ctx.command_alias == "t":
                await self.t(ctx)
                return
            elif ctx.command_alias == "g":
                await self.g(ctx)
                return

        data = await db.config.find_one({"_id": 1, "user_tokens.login": ctx.channel.name}, {"user_tokens.$": 1})
        if not data:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()

        channel = await ctx.channel.user()

        if ctx.command_alias == "t":
            await self.t(ctx, channel, token)
        elif ctx.command_alias == "g":
            await self.g(ctx, channel, token)
        elif ctx.command_alias == "addg":
            await self.addg(ctx)
        elif ctx.command_alias == "delg":
            await self.delg(ctx)
        else:
            await self.list_games(ctx)

    async def t(self, ctx: Context, channel: Optional[User] = None, token: Optional[str] = None):
        if not ctx.content:
            channel_info = await self.bot.fetch_channel(ctx.channel.name)
            await ctx.reply(f"Название стрима - {channel_info.title}")
            return

        try:
            await channel.modify_stream(token, title=ctx.content[:140])
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        await ctx.reply(f"Установлено название стрима - {ctx.content[:140]}")

    async def g(
        self, ctx: Context, channel: Optional[User] = None, token: Optional[str] = None, game: Optional[Game] = None
    ):
        if not game and not ctx.content:
            channel_info = await self.bot.fetch_channel(ctx.channel.name)
            await ctx.reply(f"Установленная категория - {channel_info.game_name}")
            return

        game = game or await self.bot.fetch_games(names=[ctx.content])
        if isinstance(game, list):
            game = game[0] if game else ""

        if not game:
            query = ctx.content.lower()
            top_games = await self.bot.fetch_top_games()
            new_game, sim = "", 0
            for g in top_games:
                if query in g.name.lower() and (new_sim := similarity(query, g.name.lower())) > sim:
                    new_game = g
                    sim = new_sim

            if sim:
                game = new_game
            else:
                found_games = await self.bot.search_categories(query)

                if not found_games:
                    await ctx.reply("Категория не найдена")
                    return

                game = None
                for game in found_games:
                    if query in game.name.lower():
                        game = game
                        break

                if not game:
                    game = found_games[0]

        try:
            await channel.modify_stream(token, game.id)
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        await ctx.reply(f"Установлена категория {game.name}")

    async def addg(self, ctx: Context):
        try:
            alias, name = ctx.content.lower().split(maxsplit=1)
        except ValueError:
            await ctx.reply("Недостаточно значений - https://vk.cc/ciaLzx")
            return

        if len(self.aliases.get(ctx.channel.name, {})) == 20:
            await ctx.reply("Достигнут лимит по количеству элиасов категорий - 20")
            return

        if len(alias) > 15:
            await ctx.reply("Маскимальная длина элисаса - 15")
            return

        games = await self.bot.fetch_games(names=[name])
        if not games:
            await ctx.reply(f'Категория "{name}" не найдена')
            return

        game = games[0]

        if (game_id := self.aliases.get(ctx.channel.name, {}).get(alias, game.id)) != game.id:
            await ctx.reply(
                f"Элиас {self.bot.prefix}{alias} уже занят категорией {self.games[ctx.channel.name][game_id]}"
            )
            return

        if self.aliases.get(ctx.channel.name, {}).get(alias) == game.id:
            await ctx.reply("Такой элиас уже существует")
            return

        cog = self.bot.get_cog("Links")
        if cog.get_link_name(ctx.channel.name, alias):
            await ctx.reply(f"Элиас {self.bot.prefix}{alias} уже занят ссылкой")
            return

        if self.bot.get_command_name(alias):
            await ctx.reply(f"Элиас {self.bot.prefix}{alias} уже занят командой бота")
            return

        key = {"channel": ctx.channel.name}

        message = f"Добавлено {self.bot.prefix}{alias}"
        if ctx.channel.name in self.games:
            if game.id in self.games[ctx.channel.name]:
                self.aliases[ctx.channel.name][alias] = game.id
                key["games.id"] = game.id
                values = {"$addToSet": {"games.$.aliases": alias}}
            else:
                self.games[ctx.channel.name][game.id] = game.name
                self.aliases[ctx.channel.name][alias] = game.id
                values = {
                    "$addToSet": {
                        "games": {
                            "name": game.name,
                            "id": game.id,
                            "aliases": [alias],
                        }
                    }
                }
        else:
            self.games[ctx.channel.name] = {game.id: game.name}
            self.aliases[ctx.channel.name] = {alias: game.id}
            self.cooldowns[ctx.channel.name] = 0
            values = {
                "$setOnInsert": {"channel": ctx.channel.name},
                "$addToSet": {
                    "games": {
                        "name": game.name,
                        "id": game.id,
                        "aliases": [alias],
                    }
                },
            }

        await db.games.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def delg(self, ctx: Context):
        if not (alias := ctx.content.lower()):
            await ctx.reply("Недостаточно значений - https://vk.cc/ciaLzx")
            return

        if alias not in self.aliases.get(ctx.channel.name, []):
            await ctx.reply("Элиас не найден")
            return

        game = self.aliases[ctx.channel.name].pop(alias)

        await db.games.update_one(
            {"channel": ctx.channel.name, "games.id": game},
            {"$pull": {"games.$.aliases": alias}},
        )
        await ctx.reply(f"Удалено - {self.bot.prefix}{alias}")

    async def list_games(self, ctx: Context):
        if not self.aliases.get(ctx.channel.name):
            await ctx.reply("На вашем канале ещё нет элиасов категорий")
            return

        message = (
            f"Доступные элиасы категорий: {self.bot.prefix}"
            f'{f" {self.bot.prefix}".join(self.aliases[ctx.channel.name])}'
        )
        await ctx.reply(message)


def prepare(bot):
    bot.add_cog(StreamInfo(bot))
    bot.loop.run_until_complete(bot.cogs["StreamInfo"].__ainit__())
