import os
import time
from pathlib import Path

import aiohttp
from twitchio.ext import commands, routines
from twitchio.ext.commands import Context, CommandNotFound
from twitchio import Message

from config import db, fernet
from cooldown import Cooldown


class ModBoty(commands.Bot, Cooldown):
    def __init__(self):
        super().__init__(
            token=os.getenv("TOKEN"),
            initial_channels=os.getenv("CHANNELS").split("&"),
            prefix="!",
        )
        self.admins = ["relanit"]
        self.streams = set()

        for command in [path.stem for path in Path("commands").glob("*py")]:
            self.load_module(f"commands.{command}")

        self.check_streams.start(stop_on_error=False)
        self.refresh_tokens.start(stop_on_error=False)
        Cooldown.__init__(self, os.getenv("CHANNELS").split("&"))

    async def event_ready(self):
        print(f"Logged in as {self.nick}")

    async def event_message(self, message: Message):
        if message.echo:
            return

        content = message.content
        if message.content.startswith("@"):
            content = (
                message.content.split(maxsplit=1)[1] if len(message.content.split(maxsplit=1)) > 1 else message.content
            )

        if content.startswith(self.prefix):
            content = content.lstrip(self.prefix)
            if not content:
                return

            command = content.split(maxsplit=1)[0]
            command_lower = command.lower()

            if command_name := self.get_command_name(command_lower):
                message.content = message.content.replace(command, command_lower)
                if await self.check_command(command_name, message, admin=message.author.name in self.admins):
                    await self.handle_commands(message)

    async def event_command_error(self, ctx: Context, error: Exception):
        if isinstance(error, CommandNotFound):
            return

    @routines.routine(minutes=1.0, iterations=0)
    async def check_streams(self):
        channels = os.getenv("CHANNELS").split("&")
        streams = await self.fetch_streams(user_logins=channels)

        for channel in channels:
            if next((s for s in streams if s.user.name.lower() == channel), None):  # check if channel is streaming
                if channel not in self.streams:
                    self.streams.add(channel)

                    if (data := await db.inspects.find_one({"channel": channel})) and data["active"]:
                        await db.inspects.update_one({"channel": channel}, {"$set": {"stats": {}}})
                        await self.cogs["Inspect"].set(channel)
            elif channel in self.streams:  # check if stream ended
                self.streams.remove(channel)

                if channel == "t2x2":
                    messageable = self.get_channel(channel)
                    await messageable.send("@Relanit запись стрима dinkDonk")

                if (data := await db.inspects.find_one({"channel": channel})) and data["active"] and data["offline"]:
                    await self.cogs["Inspect"].set(channel)
                elif data and data["active"]:
                    self.cogs["Inspect"].unset(channel)
            elif (
                channel not in self.cogs["Inspect"].limits or time.time() % 36000 < 60
            ):  # set or refresh inspect data in offline chat if enabled
                data = await db.inspects.find_one({"channel": channel})

                if data and data["active"] and data["offline"]:
                    await self.cogs["Inspect"].set(channel)

    @routines.routine(minutes=5, iterations=0)
    async def refresh_tokens(self):
        data = await db.config.find_one({"_id": 1})

        if data["expire_time"] - time.time() < 900:  # refresh bot user token
            url = f'https://id.twitch.tv/oauth2/token?client_id={os.getenv("CLIENT_ID")}&client_secret={os.getenv("CLIENT_SECRET")}&refresh_token={os.getenv("REFRESH_TOKEN")}&grant_type=refresh_token'

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers={"Content-Type": "application/x-www-form-urlencoded"}) as response:
                    response = await response.json()

            self._http.token = response["access_token"]
            self._connection._token = response["access_token"]
            os.environ["TOKEN"] = response["access_token"]
            os.environ["REFRESH_TOKEN"] = response["refresh_token"]
            enc_token = fernet.encrypt(response["access_token"].encode()).decode()
            enc_refresh = fernet.encrypt(response["refresh_token"].encode()).decode()
            await db.config.update_one(
                {"_id": 1},
                {
                    "$set": {
                        "access_token": enc_token,
                        "refresh_token": enc_refresh,
                        "expire_time": time.time() + response["expires_in"],
                    }
                },
            )

        for user in data.get("user_tokens", []):  # refresh channels' user tokens
            if user["expire_time"] - time.time() < 900:
                refresh_token = fernet.decrypt(user["refresh_token"].encode()).decode()
                url = f'https://id.twitch.tv/oauth2/token?client_id={os.getenv("CLIENT_ID")}&client_secret={os.getenv("CLIENT_SECRET")}&refresh_token={refresh_token}&grant_type=refresh_token'

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ) as response:
                        response = await response.json()

                if response == {"status": 400, "message": "Invalid refresh token"}:
                    await db.config.update_one({"_id": 1}, {"$pull": {"user_tokens": {"login": user["login"]}}})
                else:
                    token_data = {
                        "login": user["login"],
                        "access_token": fernet.encrypt(response["access_token"].encode()).decode(),
                        "refresh_token": fernet.encrypt(response["refresh_token"].encode()).decode(),
                        "expire_time": time.time() + response["expires_in"],
                    }
                    await db.config.update_one(
                        {"_id": 1, "user_tokens.login": user["login"]},
                        {"$set": {"user_tokens.$": token_data}},
                    )


bot = ModBoty()
bot.run()
