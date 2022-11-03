import twitchio.errors
from twitchio import BroadcasterTypeEnum
from twitchio.ext import commands

from config import db, fernet


class Poll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="poll",
        aliases=["delp"],
        cooldown={"per": 0, "gen": 3},
        description="Создание и завершение опросов. Полное описание - https://vk.cc/chVYL4",
    )
    async def poll(self, ctx):
        user = await ctx.channel.user()
        if user.broadcaster_type == BroadcasterTypeEnum.none:
            await ctx.reply("Эта команда доступна только компаньонам и партнёрам твича")
            return

        data = await db.config.find_one({"_id": 1, "user_tokens.login": ctx.channel.name}, {"user_tokens.$": 1})
        if not data:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        access_token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()

        if ctx.command_alias == "poll":
            await self.create_poll(ctx, user, access_token)
        else:
            await self.end_poll(ctx, user, access_token)

    @staticmethod
    async def create_poll(ctx, user, access_token):
        content_split = ctx.content.split("/")
        if len(content_split) < 3:
            await ctx.reply("Недостаточно значений - https://vk.cc/chVYL4")
            return

        try:
            duration, title = content_split[0].split(maxsplit=1)
        except ValueError:
            await ctx.reply("Недостаточно значений - https://vk.cc/chVYL4")
            return

        try:
            duration = int(duration)
        except ValueError:
            await ctx.reply("Продолжительность должна быть числом")
            return

        if not 15 <= duration <= 1800:
            await ctx.reply("Продолжительность должна быть от 15 до 1800 секунд")
            return

        if len(title) > 60:
            await ctx.reply("Длина заголовка должна быть до 60 символов")
            return

        choices = content_split[1:]

        for choice in choices:
            if len(choice) > 25:
                await ctx.reply("Длина варианта должна быть до 25 символов")
                return
            elif choice == "":
                choices.remove(choice)

        if len(choices) < 2:
            await ctx.reply("Недостаточно вариантов для выбора")
            return
        elif len(choices) > 5:
            await ctx.reply("Максимальное количество вариантов - 5")
            return

        try:
            await user.create_poll(access_token, title, choices, duration)
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        await ctx.reply(f"Создан опрос - {title}")

    @staticmethod
    async def end_poll(ctx, user, access_token):
        try:
            polls = await user.fetch_polls(access_token)
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        if polls[0].status != "ACTIVE":
            await ctx.reply("На канале нет активных опросов")
            return

        await user.end_poll(access_token, polls[0].id, "TERMINATED")
        await ctx.reply("Опрос удалён")


def prepare(bot):
    bot.add_cog(Poll(bot))
