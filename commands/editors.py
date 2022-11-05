from twitchio.ext import commands, routines

from config import db


class Editors(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.get_editors.start(stop_on_error=False)

    @commands.command(
        name="editor",
        aliases=["editors", "dele", "unban", "ban"],
        cooldown={"per": 0, "gen": 3},
        description="Настройка редакторов бота и управление доступом к командам. Полное описание - https://vk.cc/cijFyF ",
        flags=["whitelist"],
    )
    async def command(self, ctx: commands.Context):
        if not ctx.content and ctx.command_alias != "editors":
            await ctx.reply("Недостаточно значений - https://vk.cc/cijFyF")
            return

        if ctx.command_alias != "editors" and not ctx.author.is_broadcaster and ctx.author.name not in self.bot.admins:
            await ctx.reply("Эта команда доступна только стримеру")
            return

        if ctx.command_alias == "editor":
            await self.editor(ctx)
        elif ctx.command_alias == "editors":
            await self.editors(ctx)
        elif ctx.command_alias == "ban":
            await self.ban(ctx)
        elif ctx.command_alias == "unban":
            await self.unban(ctx)
        else:
            await self.dele(ctx)

    async def editor(self, ctx: commands.Context):
        login = ctx.content.lower()
        user = await self.bot.fetch_users(names=[login])
        if not user:
            await ctx.reply("Пользователь не найден")
            return

        if login in self.bot.editors.get(ctx.channel.name, []):
            await ctx.reply(f"{login} уже редактор")
            return

        self.bot.editors[ctx.channel.name] = self.bot.editors.get(ctx.channel.name, []) + [login]
        await db.editors.update_one(
            {"channel": ctx.channel.name},
            {"$setOnInsert": {"channel": ctx.channel.name}, "$addToSet": {"editors": {"login": login}}},
            upsert=True,
        )
        await ctx.reply(f"Добавлен редактор: {login}")

    async def editors(self, ctx: commands.Context):
        editors = ", ".join(self.bot.editors.get(ctx.channel.name, []))

        if not editors:
            await ctx.reply("На вашем канале ещё нет редакторов")
            return

        await ctx.reply(f"Редакторы бота на канале {ctx.channel.name}: {editors}")

    async def dele(self, ctx: commands.Context):
        if not self.bot.editors.get(ctx.channel.name):
            await ctx.reply("На вашем канале нет редакторов")
            return

        login = ctx.content.lower()
        if login not in self.bot.editors[ctx.channel.name]:
            await ctx.reply("Редактор не найден")
            return

        self.bot.editors[ctx.channel.name].remove(login)
        await db.editors.update_one({"channel": ctx.channel.name}, {"$pull": {"editors": {"login": login}}})
        await ctx.reply(f"Удалён редактор: {login}")

    async def ban(self, ctx: commands.Context):
        command = ctx.content.lower().lstrip(self.bot.prefix)
        if (
            not (command := self.bot.get_command_name(command))
            or (flags := self.bot.get_command(command).flags)
            and "admin" not in flags
        ):
            if ctx.content.lower() == "all":
                self.bot.editor_commands[ctx.channel.name] = ["all"]
                await db.editors.update_one(
                    {"channel": ctx.channel.name},
                    {"$setOnInsert": {"channel": ctx.channel.name}, "$set": {"banned": [{"name": "all"}]}},
                    upsert=True,
                )
                await ctx.reply("Теперь все команды доступны только редакторам бота")
                return
            await ctx.reply("Команда не найдена")
            return

        if command in self.bot.editor_commands.get(ctx.channel.name, []):
            await ctx.reply("Команда уже ограничена")
            return

        if "whitelist" in flags:
            await ctx.reply("Для этой команды нельзя ограничить доступ")
            return

        self.bot.editor_commands[ctx.channel.name] = self.bot.editor_commands.get(ctx.channel.name, []) + [command]
        await db.editors.update_one(
            {"channel": ctx.channel.name},
            {"$setOnInsert": {"channel": ctx.channel.name}, "$addToSet": {"banned": {"name": command}}},
            upsert=True,
        )
        message = f"Команда {self.bot.prefix}{command} теперь доступна только для редакторов бота"
        await ctx.reply(message)

    async def unban(self, ctx: commands.Context):
        command = ctx.content.lower().lstrip(self.bot.prefix)
        if (
            not (command := self.bot.get_command_name(command))
            or (flags := self.bot.get_command(command).flags)
            and "admin" not in flags
        ):
            if ctx.content.lower() == "all":
                self.bot.editor_commands[ctx.channel.name] = []
                await db.editors.update_one(
                    {"channel": ctx.channel.name},
                    {"$setOnInsert": {"channel": ctx.channel.name}, "$pull": {"banned": {"name": "all"}}},
                    upsert=True,
                )
                await ctx.reply("Теперь все команды доступны модераторам канала")
                return
            await ctx.reply("Команда не найдена")
            return

        if command not in self.bot.editor_commands.get(ctx.channel.name, []):
            await ctx.reply("У команды нет ограничений")
            return

        self.bot.editor_commands[ctx.channel.name].remove(command)
        await db.editors.update_one({"channel": ctx.channel.name}, {"$pull": {"banden": {"name": command}}})

    @routines.routine(iterations=1)
    async def get_editors(self):
        async for document in db.editors.find():
            self.bot.editors[document["channel"]] = [editor["login"] for editor in document.get("editors", [])]
            self.bot.editor_commands[document["channel"]] = [command["name"] for command in document.get("banned", [])]


def prepare(bot: commands.Bot):
    bot.add_cog(Editors(bot))
