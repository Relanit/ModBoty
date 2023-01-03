from twitchio.ext.commands import Cog, command, Context

from config import db


class Help(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(
        name="help",
        cooldown={"per": 3, "gen": 0},
        description="Эта команда.",
        flags=["whitelist", "mention"],
    )
    async def help(self, ctx: Context):
        content = ctx.content.lstrip(self.bot.prefix).lower()
        if not content:
            mention = ctx.message.custom_tags.get("mention") or ctx.author.mention
            message = f"{mention} Документация ‒ https://vk.cc/chCevV | Напишите {self.bot.prefix}help [команда], чтобы узнать описание команды"
            await ctx.send(message)
            return

        alias = content.split()[0]
        if command_name := self.bot.get_command_name(alias):
            await self.command_info(ctx, command_name)
        elif link := self.bot.get_cog("Links").get_link_name(ctx.channel.name, alias):
            await self.link_info(ctx, link)
        else:
            await self.game_info(ctx, alias)

    async def command_info(self, ctx: Context, command_name: str):
        command = self.bot.get_command(command_name)
        if "admin" in command.flags:
            await ctx.reply("Команда не найдена. Список команд ‒ https://vk.cc/chCevV")
            return

        aliases = ""
        if command.aliases:
            aliases = f'({self.bot.prefix}{str(f", {self.bot.prefix}").join(command.aliases)})'

        per = command.cooldown["per"]
        gen = command.cooldown["gen"]
        if per and gen:
            cooldown = f"личный {per}с, общий {gen}с."
        elif per:
            cooldown = f"личный {per}с."
        else:
            cooldown = f"общий {gen}с."

        editor = command.name in self.bot.editor_commands.get(ctx.channel.name, []) or "editor" in command.flags

        mention = ctx.message.custom_tags.get("mention") or ctx.author.mention
        message = (
            f'{mention} {self.bot.prefix}{command.name}{f" {aliases}:" if aliases else ":"} '
            f"{command.description.format(prefix=self.bot.prefix)} Кд: {cooldown}"
            f'{" Для редакторов бота" if editor else ""}'
        )
        await ctx.send(message)

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

        mention = ctx.message.custom_tags.get("mention") or ctx.author.mention
        message = (
            f'{mention} {self.bot.prefix}{link}{f" {aliases}." if aliases else "."} Доступ: '
            f'{"приватный" if private else "публичный"}. Кд: общий 3с. {timer}'
        )

        await ctx.send(message)

    async def game_info(self, ctx: Context, game: str):
        cog = self.bot.get_cog("StreamInfo")
        mention = ctx.message.custom_tags.get("mention") or ctx.author.mention

        if game in cog.aliases.get(ctx.channel.name, []):
            game_id = cog.aliases[ctx.channel.name][game]
            name = cog.games[ctx.channel.name][game_id]
            aliases = [
                alias
                for alias, _ in cog.aliases[ctx.channel.name].items()
                if cog.aliases[ctx.channel.name][alias] == game_id
            ]
            aliases = f'{self.bot.prefix}{str(f" {self.bot.prefix}").join(aliases)}'
            message = f"{mention} {aliases} ‒ элиасы категории {name}. Кд: общий 3с"
        elif game := [
            game for game in cog.games.get(ctx.channel.name, {}).items() if game[1].lower() == ctx.content.lower()
        ]:
            aliases = [
                alias
                for alias, _ in cog.aliases[ctx.channel.name].items()
                if cog.aliases[ctx.channel.name][alias] == game[0][0]
            ]
            aliases = f'{self.bot.prefix}{str(f" {self.bot.prefix}").join(aliases)}'
            message = f"{mention} {aliases} ‒ элиасы категории {game[0][1]}. Кд: общий 3с"
        else:
            message = f"{ctx.author.mention} Команда не найдена. Список команд ‒ https://vk.cc/chCevV"

        await ctx.send(message)


def prepare(bot):
    bot.add_cog(Help(bot))
