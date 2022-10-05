import os
import time
from pathlib import Path

import aiohttp
from twitchio.ext import commands, routines

from config import db, fernet
from cooldown import Cooldown


class ModBoty(commands.Bot, Cooldown):
    def __init__(self):
        super().__init__(
            token=os.getenv('TOKEN'),
            initial_channels=os.getenv('CHANNELS').split('&'),
            prefix='!',
            client_secret=os.getenv('CLIENT_SECRET')
        )
        self.admins = ['relanit']
        self.streams = set()

        for command in [path.stem for path in Path('commands').glob('*py')]:
            self.load_module(f'commands.{command}')

        self.check_streams.start(stop_on_error=False)
        self.refresh_token.start(stop_on_error=False)
        Cooldown.__init__(self, os.getenv('CHANNELS').split('&'))

    async def event_ready(self):
        print(f'Logged in as {self.nick}')

    async def event_message(self, message):
        if message.echo:
            return

        content = message.content
        if message.content.startswith('@'):
            content = message.content.split(' ', 1)[1] if len(message.content.split(' ', 1)) > 1 else message.content

        if content.startswith(self._prefix):
            content = content.lstrip(self._prefix)
            if not content:
                return

            command = content.split(maxsplit=1)[0]
            command_lower = command.lower()

            if command_name := self.get_command_name(command_lower):
                message.content = message.content.replace(command, command_lower)
                if message.author.name in self.admins:
                    if await self.handle_command(command_name, message, admin=True):
                        await self.handle_commands(message)
                elif await self.handle_command(command_name, message):
                    await self.handle_commands(message)

    async def event_command_error(self, ctx, error):
        if type(error).__name__ == 'CommandNotFound':
            return

    @routines.routine(minutes=1.0, iterations=0)
    async def check_streams(self):
        channels = os.getenv('CHANNELS').split('&')
        streams = await self.fetch_streams(user_logins=channels)

        for channel in channels:
            stream = None

            for s in streams:
                if s.user.name.lower() == channel:
                    stream = s
                    break

            if stream:
                if channel not in self.streams:
                    self.streams.add(channel)

                    if (data := await db.inspects.find_one({'channel': channel})) and data['active']:
                        await db.inspects.update_one({'channel': channel}, {'$set': {'stats': {}}})
                        await self.cogs['Inspect'].set(channel)
            else:
                if channel in self.streams:
                    self.streams.remove(channel)

                    if channel == 't2x2':
                        messageable = self.get_channel(channel)
                        await messageable.send('@Relanit запись стрима dinkDonk')

                    if (data := await db.inspects.find_one({'channel': channel})) and data['active']:
                        self.cogs['Inspect'].unset(channel)
                    elif data and data['active'] and data['offline']:
                        await self.cogs['Inspect'].set(channel)
                elif channel not in self.cogs['Inspect'].limits or time.time() % 36000 < 60:
                    data = await db.inspects.find_one({'channel': channel})

                    if data and data['active'] and data['offline']:
                        await self.cogs['Inspect'].set(channel)

    @routines.routine(minutes=5, iterations=0)
    async def refresh_token(self):
        response = await self._http.validate(token=os.getenv('TOKEN'))
        print(response)

        if response['expires_in'] < 900:
            print('expired')
            url = f'https://id.twitch.tv/oauth2/token?client_id={os.getenv("CLIENT_ID")}&client_secret={os.getenv("CLIENT_SECRET")}&refresh_token={os.getenv("REFRESH_TOKEN")}&grant_type=refresh_token'

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers={'Content-Type': 'application/x-www-form-urlencoded'}) as response:
                    response = await response.json()

            self._http.token = response['access_token']
            self._connection._token = response['access_token']
            os.environ['TOKEN'] = response['access_token']
            os.environ['REFRESH_TOKEN'] = response['refresh_token']
            enc_token = fernet.encrypt(response['access_token'].encode()).decode()
            enc_refresh = fernet.encrypt(response['refresh_token'].encode()).decode()
            await db.config.update_one({'_id': 1}, {'$set': {'access_token': enc_token, 'refresh_token': enc_refresh}})


bot = ModBoty()
bot.run()
