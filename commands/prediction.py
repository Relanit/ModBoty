import os

import aiohttp
import twitchio
from twitchio import BroadcasterTypeEnum, User
from twitchio.ext.commands import Cog, command, Context
from twitchio.models import Prediction

from config import db, fernet


class Predictions(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command(
        name="pred",
        aliases=["endpred", "delpred", "lockpred"],
        cooldown={"per": 0, "gen": 3},
        description="Создание и редактирование ставок. Полное описание - https://vk.cc/chZLJH",
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
            predictions = await channel.get_predictions(token)
        except twitchio.errors.Unauthorized:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        if ctx.command_alias == "pred":
            if predictions[0].ended_at is None:
                await ctx.reply("Ставка уже активна")
                return
            await self.pred(ctx, channel, token)
        else:
            if predictions[0].ended_at is not None:
                await ctx.reply("Нет активных ставок")
                return

            if ctx.command_alias == "endpred":
                await self.endpred(ctx, channel, token, predictions[0])
            elif ctx.command_alias == "delpred":
                await self.delpred(ctx, channel, token, predictions[0])
            else:
                await self.lockpred(ctx, channel, token, predictions[0])

    @staticmethod
    async def pred(ctx: Context, channel: User, token: str):
        content_split = ctx.content.split("/")
        if len(content_split) < 3:
            await ctx.reply("Недостаточно значений - https://vk.cc/chZLJH")
            return

        try:
            duration, title = content_split[0].split(maxsplit=1)
        except ValueError:
            await ctx.reply("Недостаточно значений - https://vk.cc/chZLJH")
            return

        try:
            duration = int(duration)
        except ValueError:
            await ctx.reply("Продолжительность должна быть числом")
            return

        if not 1 <= duration <= 1800:
            await ctx.reply("Продолжительность должна быть от 1 до 1800 секунд")
            return

        if len(title) > 45:
            await ctx.reply("Длина заголовка должна быть до 45 символов")
            return

        outcomes_raw = content_split[1:]
        outcomes = []

        for outcome in outcomes_raw:
            if len(outcome) > 25:
                await ctx.reply("Длина исхода должна быть до 25 символов")
                return
            elif outcome != "":
                outcomes.append({"title": outcome})

        if len(outcomes) < 2:
            await ctx.reply("Недостаточное количество исходов")
            return
        elif len(outcomes) > 10:
            await ctx.reply("Максимальное количество исходов - 10")
            return

        async with aiohttp.ClientSession() as session:
            url = "https://api.twitch.tv/helix/predictions"
            headers = {
                "Authorization": f"Bearer {token}",
                "Client-Id": os.getenv("CLIENT_ID"),
                "Content-Type": "application/json",
            }

            json = {
                "broadcaster_id": str(channel.id),
                "title": title,
                "outcomes": outcomes,
                "prediction_window": duration,
            }
            async with session.post(url, headers=headers, json=json) as response:
                response = await response.json()

        if response.get("status") == 403:
            await ctx.reply("На вашем канале недоступны баллы канала")
            return
        elif response.get("status") == 401:
            await ctx.reply("Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI")
            return

        await ctx.reply(f"Создана ставка - {title}")

    @staticmethod
    async def endpred(ctx: Context, channel: User, token: str, prediction: Prediction):
        if not ctx.content:
            await ctx.reply("Введите номер верного исхода")
            return

        try:
            outcome_id = int(ctx.content)
        except ValueError:
            await ctx.reply("Номер верного исхода должен быть числом")
            return

        if not 1 <= outcome_id <= len(prediction.outcomes):
            await ctx.reply("Неверный номер исхода")
            return

        outcome_id = prediction.outcomes[outcome_id - 1].outcome_id
        await channel.end_prediction(
            token,
            prediction.prediction_id,
            "RESOLVED",
            winning_outcome_id=outcome_id,
        )
        await ctx.reply("Ставка завершена")

    @staticmethod
    async def delpred(ctx: Context, channel: User, token: str, prediction: Prediction):
        await channel.end_prediction(token, prediction.prediction_id, "CANCELED")
        await ctx.reply("Ставка удалена")

    @staticmethod
    async def lockpred(ctx: Context, channel: User, token: str, prediction: Prediction):
        await channel.end_prediction(token, prediction.prediction_id, "LOCKED")
        await ctx.reply("Ставка заблокирована")


def prepare(bot):
    bot.add_cog(Predictions(bot))
