import twitchio.errors
from twitchio import BroadcasterTypeEnum, User
from twitchio.ext import commands
from twitchio.models import Poll

from config import db, fernet


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="poll",
        aliases=["delpoll"],
        cooldown={"per": 0, "gen": 3},
        description="Создание и завершение опросов. Полное описание - https://vk.cc/chVYL4",
    )
    async def command(self, ctx: commands.Context):
        user = await ctx.channel.user()
        if user.broadcaster_type == BroadcasterTypeEnum.none:
            await ctx.reply("Эта команда доступна только компаньонам и партнёрам твича")
            return

        data = await db.config.find_one({"_id": 1, "user_tokens.login": ctx.channel.name}, {"user_tokens.$": 1})
        if not data:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()

        try:
            polls = await user.fetch_polls(token)
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        if ctx.command_alias == "poll":
            if polls[0].status == "ACTIVE":
                await ctx.reply("На канале уже есть активный вопрос")
                return
            await self.poll(ctx, user, token)
        else:
            if polls[0].status != "ACTIVE":
                await ctx.reply("На канале нет активных опросов")
                return
            await self.delp(ctx, user, token, polls[0])

    @staticmethod
    async def poll(ctx: commands.Context, user: User, token: str):
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

        await user.create_poll(token, title, choices, duration)
        await ctx.reply(f"Создан опрос - {title}")

    @staticmethod
    async def delp(ctx: commands.Context, user: User, token: str, poll: Poll):
        await user.end_poll(token, poll.id, "TERMINATED")
        await ctx.reply("Опрос удалён")


def prepare(bot: commands.Bot):
    bot.add_cog(Polls(bot))
