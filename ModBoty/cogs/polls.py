import twitchio.errors
from twitchio import BroadcasterTypeEnum, User
from twitchio.ext.commands import Cog, command, Context
from twitchio.models import Poll

from config import db, fernet


class Polls(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(
        name="poll",
        aliases=["delpoll"],
        cooldown={"per": 0, "gen": 3},
        description="Создание и удаление опросов. Полное описание - https://vk.cc/cj2PKZ",
    )
    async def command(self, ctx: Context):
        channel = await ctx.channel.user()
        if channel.broadcaster_type == BroadcasterTypeEnum.none:
            await ctx.reply("Эта команда доступна только компаньонам и партнёрам твича")
            return

        data = await db.config.find_one({"_id": 1, "user_tokens.login": ctx.channel.name}, {"user_tokens.$": 1})
        if not data:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        token = fernet.decrypt(data["user_tokens"][0]["access_token"].encode()).decode()

        try:
            polls = await channel.fetch_polls(token)
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        if ctx.command_alias == "poll":
            if polls[0].status == "ACTIVE":
                await ctx.reply("На канале уже есть активный опрос")
                return
            await self.poll(ctx, channel, token)
        else:
            if polls[0].status != "ACTIVE":
                await ctx.reply("На канале нет активных опросов")
                return
            await self.delpoll(ctx, channel, token, polls[0])

    @staticmethod
    async def poll(ctx: Context, channel: User, token: str):
        sep = "\\" if "\\" in ctx.content else "/"
        content_split = ctx.content.split(sep)
        if len(content_split) < 3:
            await ctx.reply("Неверный ввод команды - https://vk.cc/cj2PKZ")
            return

        try:
            duration, title = content_split[0].split(maxsplit=1)
        except ValueError:
            duration = 60
            title = content_split[0]

        if isinstance(duration, str):
            try:
                duration = int(duration)
            except ValueError:
                await ctx.reply("Продолжительность должна быть числом")
                return
            duration = min(max(duration, 15), 1800)

        title = title[:60]

        choices = [choice[:25] for choice in content_split[1:] if choice != ""]
        if len(choices) < 2:
            await ctx.reply("Недостаточно вариантов для выбора")
            return
        elif len(choices) > 5:
            await ctx.reply("Максимальное количество вариантов - 5")
            return

        await channel.create_poll(token, title, choices, duration)
        await ctx.reply(f'Создан опрос "{title}"')

    @staticmethod
    async def delpoll(ctx: Context, channel: User, token: str, poll: Poll):
        await channel.end_poll(token, poll.id, "TERMINATED")
        await ctx.reply("Опрос удалён")


def prepare(bot):
    bot.add_cog(Polls(bot))
