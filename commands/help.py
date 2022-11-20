from twitchio.ext.commands import Cog, command, Context

from config import db


class Help(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(
        name="help",
        cooldown={"per": 3, "gen": 0},
        description="Эта команда.",
        flags=["whitelist"],
    )
    async def help(self, ctx: Context):
        content = ctx.content.lstrip(self.bot.prefix).lower()
        if not content:
            message = f"Документация - https://vk.cc/chCevV | Напишите {self.bot.prefix}help [команда], чтобы узнать описание команды"
            await ctx.reply(message)
            return

        alias = content.split()[0]
        if command_name := self.bot.get_command_name(alias):
            await self.command_info(ctx, command_name)
        elif link := self.bot.get_cog("Link").get_link_name(ctx.channel.name, alias):
            await self.link_info(ctx, link)
        else:
            await self.game_info(ctx, alias)

    async def command_info(self, ctx: Context, command_name: str):
        data = self.bot.get_command(command_name)
        if "admin" in data.flags:
            await ctx.reply("Команда не найдена. Список команд - https://vk.cc/chCevV")
            return

        aliases = ""
        if data.aliases:
            aliases = f'({self.bot.prefix}{str(f", {self.bot.prefix}").join(data.aliases)})'

        per = data.cooldown["per"]
        gen = data.cooldown["gen"]
        if per and gen:
            cooldown = f"личный {per}с, общий {gen}с."
        elif per:
            cooldown = f"личный {per}с."
        else:
            cooldown = f"общий {gen}с."

        editor = command_name in self.bot.editor_commands.get(ctx.channel.name, []) or "editor" in data.flags

        message = (
            f'{self.bot.prefix}{command_name}{f" {aliases}:" if aliases else ":"} '
            f"{data.description.format(prefix=self.bot.prefix)} Кд: {cooldown}"
            f'{" Для редакторов бота" if editor else ""}'
        )
        await ctx.reply(message)

    async def link_info(self, ctx: Context, link: str):
        data = await db.links.find_one(
            {"channel": ctx.channel.name},
            {"links": {"$elemMatch": {"name": link}}, "private": 1},
        )

        aliases = data["links"][0]["aliases"] if "aliases" in data["links"][0] else []

        if aliases:
            aliases = f'({self.bot.prefix}{str(f", {self.bot.prefix}").join(aliases)})'

        private = data["links"][0]["private"] if "private" in data["links"][0] else data["private"]

        timer = ""
        cog = self.bot.get_cog("Timers")
        if link in cog.timers.get(ctx.channel.name, []):
            offline_raw = await db.timers.find_one({"channel": ctx.channel.name}, {"offline": 1})
            offline = offline_raw["offline"]
            timer = cog.timers[ctx.channel.name][link]
            timer = (
                f'Установлен {"активный" if timer.get("active", True) else "неактивный"} таймер: '
                f'{timer["number"]} сообщений раз в {timer["interval"]}м'
                f'{", с announce" if timer.get("announce", False) in timer else ""}'
                f'{"." if timer.get("offline", offline) else ", только на стриме."}'
            )
        message = (
            f'{self.bot.prefix}{link}{f" {aliases}." if aliases else "."} Доступ: '
            f'{"приватный" if private else "публичный"}. Кд: общий 3с. {timer}'
        )

        await ctx.reply(message)

    async def game_info(self, ctx: Context, game: str):
        cog = self.bot.get_cog("StreamInfo")
        if game in cog.aliases.get(ctx.channel.name, []):
            game_id = cog.aliases[ctx.channel.name][game]
            name = cog.games[ctx.channel.name][game_id]
            aliases = [
                alias
                for alias, _ in cog.aliases[ctx.channel.name].items()
                if cog.aliases[ctx.channel.name][alias] == game_id
            ]
            aliases = f'{self.bot.prefix}{str(f" {self.bot.prefix}").join(aliases)}'
            message = f"{aliases} - элиасы категории {name}. Кд: общий 3с"
        elif game := [
            game for game in cog.games.get(ctx.channel.name, {}).items() if game[1].lower() == ctx.content.lower()
        ]:
            aliases = [
                alias
                for alias, _ in cog.aliases[ctx.channel.name].items()
                if cog.aliases[ctx.channel.name][alias] == game[0][0]
            ]
            aliases = f'{self.bot.prefix}{str(f" {self.bot.prefix}").join(aliases)}'
            message = f"{aliases} - элиасы категории {game[0][1]}. Кд: общий 3с"
        else:
            message = "Команда не найдена. Список команд - https://vk.cc/chCevV"

        await ctx.reply(message)


def prepare(bot):
    bot.add_cog(Help(bot))
