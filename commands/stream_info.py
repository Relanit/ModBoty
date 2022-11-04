import difflib
import time
from typing import Optional

import twitchio
from twitchio.ext import commands, routines
from twitchio.models import Game
from twitchio import Message, User

from config import db, fernet


def similarity(s1: str, s2: str) -> float:
    """Return a measure of the strings' similarity (float in [0,1])."""
    matcher = difflib.SequenceMatcher(None, s1, s2)
    return matcher.ratio()


class StreamInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.games = {}
        self.aliases = {}
        self.cooldowns = {}
        self.get_games.start(stop_on_error=False)

    @commands.Cog.event()
    async def event_message(self, message: Message):
        if message.echo:
            return

        if message.content.startswith(self.bot.prefix):
            content = message.content.lower().lstrip(self.bot.prefix)
            if not content:
                return

            if (
                content in self.aliases.get(message.channel.name, {})
                and message.author.is_mod
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

                user = await ctx.channel.user()
                token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()
                game = [Game(self.aliases[message.channel.name][content] | {"box_art_url": ""})]
                self.cooldowns[message.channel.name] = time.time() + 3
                await self.g(ctx, user, token, game)

    @commands.command(
        name="t",
        aliases=["g", "addg", "delg", "games"],
        cooldown={"per": 0, "gen": 3},
        description="Изменение настроек стрима. Полное описание - https://vk.cc/ciaLzx",
    )
    async def command(self, ctx: commands.Context):
        data = await db.config.find_one({"_id": 1, "user_tokens.login": ctx.channel.name}, {"user_tokens.$": 1})
        if not data:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        if not ctx.content and ctx.command_alias != "games":
            await ctx.reply("Недостаточно значений - https://vk.cc/ciaLzx")
            return

        token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()

        user = await ctx.channel.user()

        if ctx.command_alias == "t":
            await self.t(ctx, user, token)
        elif ctx.command_alias == "g":
            await self.g(ctx, user, token)
        elif ctx.command_alias == "addg":
            await self.addg(ctx)
        elif ctx.command_alias == "delg":
            await self.delg(ctx)
        else:
            await self.list_games(ctx)

    @staticmethod
    async def t(ctx: commands.Context, user: User, token: str):
        try:
            await user.modify_stream(token, title=ctx.content[:140])
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        await ctx.reply(f"Установлено название стрима - {ctx.content[:140]}")

    async def g(self, ctx: commands.Context, user: User, token: str, game: Optional[list[Game]] = None):
        game = game or await self.bot.fetch_games(names=[ctx.content])

        if not game:
            games = await self.bot.fetch_top_games()
            new_game = ""
            sim = 0
            for g in games:
                if (new_sim := similarity(ctx.content.lower(), g.name.lower())) > sim:
                    new_game = g
                    sim = new_sim

            if sim < 0.5:
                await ctx.reply("Категория не найдена")
                return

            game = [new_game]

        try:
            await user.modify_stream(token, game[0].id)
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        await ctx.reply(f"Установлена категория {game[0].name}")

    async def addg(self, ctx: commands.Context):
        try:
            alias, name = ctx.content.lower().split(maxsplit=1)
        except ValueError:
            await ctx.reply("Недостаточно значений - https://vk.cc/ciaLzx")
            return

        if len(self.aliases.get(ctx.channel.name, {})) == 30:
            await ctx.reply("Достигнут лимит по количеству элиасов категорий - 30")
            return

        if len(alias) > 15:
            await ctx.reply("Маскимальная длина элисаса - 15")
            return

        game = await self.bot.fetch_games(names=[name])
        if not game:
            await ctx.reply(f'Категория "{name}" не найдена')
            return

        if self.aliases.get(ctx.channel.name, {}).get(alias, {}).get("id", game[0].id) != game[0].id:
            await ctx.reply(
                f'Элиас {self.bot.prefix}{alias} уже занят категорией {self.aliases[ctx.channel.name][alias]["name"]}'
            )
            return

        if self.aliases.get(ctx.channel.name, {}).get(alias, {}).get("id") == game[0].id:
            await ctx.reply("Такой элиас уже существует")
            return

        cog = self.bot.get_cog("Link")
        if alias in cog.links.get(ctx.channel.name, []) or alias in cog.links_aliases.get(ctx.channel.name, []):
            await ctx.reply(f"Элиас {self.bot.prefix}{alias} уже занят командой")
            return

        if self.bot.get_command_name(alias):
            await ctx.reply(f"Элиас {self.bot.prefix}{alias} уже занят командой")
            return

        key = {"channel": ctx.channel.name}

        message = f"Добавлено {self.bot.prefix}{alias}"
        if ctx.channel.name in self.games:
            if game[0].id in self.games[ctx.channel.name]:
                self.aliases[ctx.channel.name][alias] = {
                    "name": game[0].name,
                    "id": game[0].id,
                }
                key["games.id"] = game[0].id
                values = {"$addToSet": {"games.$.aliases": alias}}
            else:
                self.games[ctx.channel.name].add(game[0].id)
                self.aliases[ctx.channel.name][alias] = {
                    "name": game[0].name,
                    "id": game[0].id,
                }
                values = {
                    "$addToSet": {
                        "games": {
                            "name": game[0].name,
                            "id": game[0].id,
                            "aliases": [alias],
                        }
                    }
                }
        else:
            self.games[ctx.channel.name] = {game[0].id}
            self.aliases[ctx.channel.name] = {alias: {"name": game[0].name, "id": game[0].id}}
            self.cooldowns[ctx.channel.name] = 0
            values = {
                "$setOnInsert": {"channel": ctx.channel.name},
                "$addToSet": {
                    "games": {
                        "name": game[0].name,
                        "id": game[0].id,
                        "aliases": [alias],
                    }
                },
            }

        await db.game_aliases.update_one(key, values, upsert=True)
        await ctx.reply(message)

    async def delg(self, ctx: commands.Context):
        if not (alias := ctx.content.lower()):
            await ctx.reply("Недостаточно значений - https://vk.cc/ciaLzx")
            return

        if alias not in self.aliases.get(ctx.channel.name, []):
            await ctx.reply("Элиас не найден")
            return

        game = self.aliases[ctx.channel.name].pop(alias)

        await db.game_aliases.update_one(
            {"channel": ctx.channel.name, "games.id": game["id"]},
            {"$pull": {"games.$.aliases": alias}},
        )
        await ctx.reply(f"Удалено - {self.bot.prefix}{alias}")

    async def list_games(self, ctx: commands.Context):
        if not self.aliases.get(ctx.channel.name, None):
            await ctx.reply("На вашем канале ещё нет элиасов категорий")
            return

        message = (
            f"Доступные элиасы категорий: {self.bot.prefix}"
            f'{str(f" {self.bot.prefix}").join(self.aliases[ctx.channel.name])}'
        )
        await ctx.reply(message)

    @routines.routine(iterations=1)
    async def get_games(self):
        async for document in db.game_aliases.find():
            self.aliases[document["channel"]] = {
                alias: {"name": game["name"], "id": game["id"]}
                for game in document["games"]
                for alias in game["aliases"]
            }
            self.games[document["channel"]] = {game["id"] for game in document["games"]}
            self.cooldowns[document["channel"]] = 0


def prepare(bot: commands.Bot):
    bot.add_cog(StreamInfo(bot))
