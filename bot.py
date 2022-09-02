import os
import time
from pathlib import Path

from twitchio.ext import commands, routines

from config import CHANNELS, db
from cooldown import Cooldown


class ModBoty(commands.Bot, Cooldown):
    def __init__(self):
        super().__init__(token=os.getenv('TOKEN'), prefix='!', initial_channels=CHANNELS)
        self.admins = ['relanit']
        self.streams = set()

        for command in [path.stem for path in Path('commands').glob('*py')]:
            self.load_module(f'commands.{command}')

        self.check_streams.start(stop_on_error=False)
        Cooldown.__init__(self, CHANNELS)

    async def event_ready(self):
        print(f'Logged in as {self.nick}')

    async def event_message(self, message):
        if message.echo:
            return

        content = message.content

        if message.content.startswith('@'):
            content = message.content.split(' ', 1)[1]

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
        channels = self.channels_names or CHANNELS
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
                        await db.inspects.update_one({'channel': channel}, {'$unset': {'stats': 1}})
                        await self.cogs['Inspect'].set(channel)
            else:
                if channel in self.streams:
                    self.streams.remove(channel)

                    if (data := await db.inspects.find_one({'channel': channel})) and data['active']:
                        self.cogs['Inspect'].unset(channel)
                    elif data and data['active'] and data['offline']:
                        await self.cogs['Inspect'].set(channel)
                elif channel not in self.cogs['Inspect'].limits or time.time() % 36000 < 60:
                    data = await db.inspects.find_one({'channel': channel})

                    if data and data['active'] and data['offline']:
                        await self.cogs['Inspect'].set(channel)


bot = ModBoty()
bot.run()
