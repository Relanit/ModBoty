import os

import aiohttp
import twitchio
from twitchio import BroadcasterTypeEnum
from twitchio.ext import commands

from config import db, fernet


class Prediction(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name='prediction',
        aliases=['pred', 'endpred', 'delpred', 'lockpred'],
        cooldown={'per': 0, 'gen': 3},
        description='Создание и редактирование ставок. Полное описание - '
    )
    async def prediction(self, ctx):
        user = await ctx.channel.user()
        if user.broadcaster_type == BroadcasterTypeEnum.none:
            await ctx.reply('Эта команда доступна только компаньонам и партнёрам твича')
            return

        data = await db.config.find_one({'_id': 1, 'user_tokens.login': ctx.channel.name}, {'user_tokens.$': 1})
        if not data:
            await ctx.reply('Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI')
            return

        access_token = fernet.decrypt(data['user_tokens'][0]['access_token'].encode()).decode()

        if ctx.command_alias in ('prediction', 'pred'):
            await self.create_prediction(ctx, user, access_token)
        else:
            try:
                predictions = await user.get_predictions(access_token)
            except twitchio.errors.Unauthorized:
                await ctx.reply('Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI')
                return

            if predictions[0].ended_at is not None:
                await ctx.reply('Нет активных ставок')
                return

            if ctx.command_alias == 'endpred':
                await self.end_prediction(ctx, user, access_token, predictions)
            elif ctx.command_alias == 'delpred':
                await self.cancel_prediction(ctx, user, access_token, predictions)
            else:
                await self.lock_prediction(ctx, user, access_token, predictions)

    @staticmethod
    async def create_prediction(ctx, user, access_token):
        content_split = ctx.content.split('/')
        if len(content_split) < 3:
            await ctx.reply('Недостаточно значений - ')
            return

        try:
            duration, title = content_split[0].split(maxsplit=1)
        except ValueError:
            await ctx.reply('Недостаточно значений - ')
            return

        try:
            duration = int(duration)
        except ValueError:
            await ctx.reply('Продолжительность должна быть числом')
            return

        if not 1 <= duration <= 1800:
            await ctx.reply('Продолжительность должна быть от 1 до 1800 секунд')
            return

        if len(title) > 45:
            await ctx.reply('Длина заголовка должна быть до 45 символов')
            return

        outcomes_raw = content_split[1:]
        outcomes = []

        for outcome in outcomes_raw:
            if len(outcome) > 25:
                await ctx.reply('Длина исхода должна быть до 25 символов')
                return
            elif outcome != '':
                outcomes.append({'title': outcome})

        if len(outcomes) < 2:
            await ctx.reply('Недостаточное количество исходов')
            return
        elif len(outcomes) > 10:
            await ctx.reply('Максимальное количество исходов - 10')
            return

        async with aiohttp.ClientSession() as session:
            url = 'https://api.twitch.tv/helix/predictions'
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Client-Id': os.getenv('CLIENT_ID'),
                'Content-Type': 'application/json'
            }

            json = {
                'broadcaster_id': str(user.id),
                'title': title,
                'outcomes': outcomes,
                'prediction_window': duration
            }
            async with session.post(url, headers=headers, json=json) as response:
                response = await response.json()

        if response.get('status') == 403:
            await ctx.reply('На вашем канале недоступны баллы канала')
            return
        elif response.get('status') == 401:
            await ctx.reply('Для работы этой команды стримеру нужно пройти авторизацию - https://vk.cc/chZxeI')
            return
        elif 'already active' in response.get('message', ''):
            await ctx.reply('Ставка уже активна')
            return

        await ctx.reply('Ставка создана')

    @staticmethod
    async def end_prediction(ctx, user, access_token, predictions):
        if not ctx.content:
            await ctx.reply('Введите номер верного исхода')
            return

        try:
            outcome_id = int(ctx.content)
        except ValueError:
            await ctx.reply('Номер верного исхода должен быть числом')
            return

        if not 1 <= outcome_id <= len(predictions[0].outcomes):
            await ctx.reply('Неверный номер исхода')
            return

        outcome_id = predictions[0].outcomes[outcome_id-1].outcome_id
        await user.end_prediction(access_token, predictions[0].prediction_id, 'RESOLVED', winning_outcome_id=outcome_id)
        await ctx.reply('Ставка завершена')

    @staticmethod
    async def cancel_prediction(ctx, user, access_token, predictions):
        await user.end_prediction(access_token, predictions[0].prediction_id, 'CANCELED')
        await ctx.reply('Ставка удалена')

    @staticmethod
    async def lock_prediction(ctx, user, access_token, predictions):
        await user.end_prediction(access_token, predictions[0].prediction_id, 'LOCKED')
        await ctx.reply('Ставка заблокирована')


def prepare(bot):
    bot.add_cog(Prediction(bot))
