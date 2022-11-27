from twitchio.ext.commands import Cog, command, Context

from config import db


class Editors(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def __ainit__(self):
        async for document in db.editors.find():
            self.bot.editors[document["channel"]] = document.get("editors", [])
            self.bot.editor_commands[document["channel"]] = document.get("banned", [])

    @command(
        name="editor",
        aliases=["editors", "dele", "unban", "ban"],
        cooldown={"per": 0, "gen": 3},
        description="Настройка редакторов бота и управление доступом к командам. Полное описание - https://vk.cc/cijFyF ",
        flags=["whitelist"],
    )
    async def command(self, ctx: Context):
        if not ctx.content and ctx.command_alias != "editors":
            await ctx.reply("Недостаточно значений - https://vk.cc/cijFyF")
            return

        if ctx.command_alias != "editors" and not ctx.author.is_broadcaster and ctx.author.name != self.bot.admin:
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

    async def editor(self, ctx: Context):
        if len(self.bot.editors.get(ctx.channel.name, [])) == 10:
            await ctx.reply("На канале может быть не более 10 редакторов")
            return

        login = ctx.content.lower().lstrip("@")
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
            {"$setOnInsert": {"channel": ctx.channel.name}, "$addToSet": {"editors": login}},
            upsert=True,
        )
        await ctx.reply(f"Добавлен редактор: {login}")

    async def editors(self, ctx: Context):
        editors = ", ".join(self.bot.editors.get(ctx.channel.name, []))

        if not editors:
            await ctx.reply("На вашем канале ещё нет редакторов")
            return

        await ctx.reply(f"Редакторы бота на канале {ctx.channel.name}: {editors}")

    async def dele(self, ctx: Context):
        if not self.bot.editors.get(ctx.channel.name):
            await ctx.reply("На вашем канале нет редакторов")
            return

        login = ctx.content.lower().lstrip("@")
        if login not in self.bot.editors[ctx.channel.name]:
            await ctx.reply("Редактор не найден")
            return

        self.bot.editors[ctx.channel.name].remove(login)
        await db.editors.update_one({"channel": ctx.channel.name}, {"$pull": {"editors": login}})
        await ctx.reply(f"Удалён редактор: {login}")

    async def ban(self, ctx: Context):
        command_name = ctx.content.lower().lstrip(self.bot.prefix)
        if (
            not (command_name := self.bot.get_command_name(command_name))
            or (flags := self.bot.get_command(command_name).flags)
            and "admin" in flags
        ):
            if ctx.content.lower() == "all":
                self.bot.editor_commands[ctx.channel.name] = [
                    command_name
                    for command_name in self.bot.commands.keys()
                    if "whitelist" not in (flags := self.bot.get_command(command_name).flags)
                    and "admin" not in flags
                    and "editor" not in flags
                ]

                await db.editors.update_one(
                    {"channel": ctx.channel.name},
                    {
                        "$setOnInsert": {"channel": ctx.channel.name},
                        "$set": {"banned": self.bot.editor_commands[ctx.channel.name]},
                    },
                    upsert=True,
                )

                await ctx.reply("Теперь все команды доступны только редакторам бота")
                return
            await ctx.reply("Команда не найдена")
            return

        if command_name in self.bot.editor_commands.get(ctx.channel.name, []) or "editor" in flags:
            await ctx.reply("Команда уже ограничена")
            return

        if "whitelist" in flags:
            await ctx.reply("Для этой команды нельзя ограничить доступ")
            return

        self.bot.editor_commands[ctx.channel.name] = self.bot.editor_commands.get(ctx.channel.name, []) + [command_name]
        await db.editors.update_one(
            {"channel": ctx.channel.name},
            {"$setOnInsert": {"channel": ctx.channel.name}, "$addToSet": {"banned": command_name}},
            upsert=True,
        )
        message = f"Команда {self.bot.prefix}{command_name} теперь доступна только для редакторов бота"
        await ctx.reply(message)

    async def unban(self, ctx: Context):
        command_name = ctx.content.lower().lstrip(self.bot.prefix)
        if (
            not (command_name := self.bot.get_command_name(command_name))
            or (flags := self.bot.get_command(command_name).flags)
            and "admin" in flags
        ):
            if ctx.content.lower() == "all":
                self.bot.editor_commands[ctx.channel.name] = []
                await db.editors.update_one(
                    {"channel": ctx.channel.name},
                    {"$setOnInsert": {"channel": ctx.channel.name}, "$set": {"banned": []}},
                    upsert=True,
                )
                await ctx.reply("Теперь все команды доступны модераторам канала")
                return
            await ctx.reply("Команда не найдена")
            return

        if "editor" in flags:
            await ctx.reply("Для этой команды нельзя снять ограничения")
            return

        if command not in self.bot.editor_commands.get(ctx.channel.name, []):
            await ctx.reply("У команды нет ограничений")
            return

        self.bot.editor_commands[ctx.channel.name].remove(command)
        await db.editors.update_one({"channel": ctx.channel.name}, {"$pull": {"banned": command}})
        await ctx.reply(f"Теперь команда {self.bot.prefix}{command} доступна всем модераторам")


def prepare(bot):
    bot.add_cog(Editors(bot))
    bot.loop.run_until_complete(bot.cogs["Editors"].__ainit__())
