from twitchio.ext import commands

from config import db


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="help",
        aliases=["commands"],
        cooldown={"per": 3, "gen": 0},
        description="Эта команда.",
    )
    async def help(self, ctx: commands.Context):
        content = ctx.content.lstrip(self.bot.prefix).lower()
        if not content:
            message = f"Документация - https://vk.cc/chCevV | Напишите {self.bot.prefix}help [команда], чтобы узнать описание команды"
            await ctx.reply(message)
            return

        if command := self.bot.get_command_name(content.split()[0]):
            data = self.bot.get_command(command)
            if "admin" in data.flags:
                await ctx.reply("Несуществующая команда")
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

            message = (
                f'{self.bot.prefix}{command}{f" {aliases}:" if aliases else ":"} '
                f"{data.description.format(prefix=self.bot.prefix)} Кд: {cooldown}"
            )

        else:
            command = content.split()[0]
            cog = self.bot.get_cog("Link")

            if (
                command not in cog.links.get(ctx.channel.name, [])
                and command not in cog.links_aliases.get(ctx.channel.name, []).keys()
            ):  # check if command is game alias
                cog = self.bot.get_cog("StreamInfo")
                if command in cog.aliases.get(ctx.channel.name, []):
                    game_id = cog.aliases[ctx.channel.name][command]
                    name = cog.games[ctx.channel.name][game_id]
                    aliases = [
                        alias
                        for alias, _ in cog.aliases[ctx.channel.name].items()
                        if cog.aliases[ctx.channel.name][alias] == game_id
                    ]
                    aliases = f'{self.bot.prefix}{str(f" {self.bot.prefix}").join(aliases)}'
                    await ctx.reply(f"{aliases} - элиасы категории {name}. Кд: общий 3с")
                elif game := [
                    game for game in cog.games.get(ctx.channel.name, {}).items() if game[1].lower() == content
                ]:
                    aliases = [
                        alias
                        for alias, _ in cog.aliases[ctx.channel.name].items()
                        if cog.aliases[ctx.channel.name][alias] == game[0][0]
                    ]
                    aliases = f'{self.bot.prefix}{str(f" {self.bot.prefix}").join(aliases)}'
                    await ctx.reply(f"{aliases} - элиасы категории {game[0][1]}. Кд: общий 3с")
                else:
                    await ctx.reply("Несуществующая команда")
                    return
            elif command in cog.links_aliases.get(ctx.channel.name, []):
                command = cog.links_aliases[ctx.channel.name][command]

            data = await db.links.find_one(
                {"channel": ctx.channel.name},
                {"links": {"$elemMatch": {"name": command}}, "private": 1},
            )

            aliases = data["links"][0]["aliases"] if "aliases" in data["links"][0] else []

            if aliases:
                aliases = f'({self.bot.prefix}{str(f", {self.bot.prefix}").join(aliases)})'

            private = data["links"][0]["private"] if "private" in data["links"][0] else data["private"]

            timer = ""
            cog = self.bot.get_cog("Timer")

            if command in cog.timers.get(ctx.channel.name, []):
                offline_raw = await db.timers.find_one({"channel": ctx.channel.name}, {"offline": 1})
                offline = offline_raw["offline"]
                timer = cog.timers[ctx.channel.name][command]
                timer = (
                    f'Установлен {"активный" if timer.get("active", True) else "неактивный"} таймер: '
                    f'{timer["number"]} сообщений раз в {timer["interval"]}м'
                    f'{", с announce" if timer.get("announce", False) in timer else ""}'
                    f'{"." if timer.get("offline", offline) else ", только на стриме."}'
                )

            message = (
                f'{self.bot.prefix}{command}{f" {aliases}." if aliases else "."} Доступ: '
                f'{"приватный" if private else "публичный"}. Кд: общий 3с. {timer}'
            )

        await ctx.reply(message)


def prepare(bot: commands.Bot):
    bot.add_cog(Help(bot))
