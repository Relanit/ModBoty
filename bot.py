import os
from pathlib import Path

from twitchio.ext import commands

from config import CHANNELS
from cooldown import Cooldown


class ModBoty(commands.Bot, Cooldown):
    def __init__(self):
        super().__init__(token=os.getenv('TOKEN'), prefix='!', initial_channels=CHANNELS)
        self.admins = ['relanit']

        for command in [path.stem for path in Path('commands').glob('*py')]:
            self.load_module(f'commands.{command}')

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


bot = ModBoty()
bot.run()
