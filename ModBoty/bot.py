import time
from pathlib import Path

import aiohttp
import twitchio.errors
from twitchio.ext.commands import Bot, Context, CommandNotFound
from twitchio.ext.routines import routine
from twitchio import Message

from config import config, db, fernet
from cooldown import Cooldown


class ModBoty(Bot, Cooldown):
    def __init__(self):
        super().__init__(
            token=config["Bot"]["access_token"],
            initial_channels=config["Bot"]["channels"].split(),
            prefix=config["Bot"]["prefix"],
        )
        Cooldown.__init__(self, config["Bot"]["channels"].split())

        self.admin = config["Bot"]["admin"]
        self.editors: dict[str, list[str]] = {}
        self.editor_commands: dict[str, list[str]] = {}
        self.streams: list[str] = []

        for cog in [path.stem for path in Path("cogs").glob("*py")]:
            self.load_module(f"cogs.{cog}")

        self.clear_data.start(stop_on_error=False)
        self.check_streams.start(stop_on_error=False)
        self.refresh_tokens.start(stop_on_error=False)

    async def event_ready(self):
        print(f"Logged in as {self.nick}")

    async def event_message(self, message: Message):
        if message.echo:
            return

        if message.content.startswith(self.prefix):
            content = message.content.lstrip(self.prefix)
            if not content:
                return

            command = content.split(maxsplit=1)[0]
            command_lower = command.lower()

            if command_name := self.get_command_name(command_lower):
                message.content = message.content.replace(command, command_lower)
                if await self.check_command(command_name, message, admin=message.author.name == self.admin):
                    await self.handle_commands(message)

    async def event_command_error(self, ctx: Context, error: Exception):
        if isinstance(error, CommandNotFound):
            return

    @routine(minutes=1.0)
    async def check_streams(self):
        channels = config["Bot"]["channels"].split()
        try:
            streams = await self.fetch_streams(user_logins=channels)
        except aiohttp.ClientConnectorError as e:
            print(time.time())
            print(repr(e))
            return
        except twitchio.errors.Unauthorized as e:
            print(time.time())
            print(repr(e))
            return
        except twitchio.HTTPException as e:
            print(time.time())
            print(repr(e))
            return

        for channel in channels:
            if next((s for s in streams if s.user.name.lower() == channel), None):  # check if channel is streaming
                if channel not in self.streams:
                    self.streams.append(channel)

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

    @routine(hours=5)
    async def clear_data(self):
        channels = config["Bot"]["channels"].split()

        for channel in channels:
            if channel not in self.streams and channel not in self.cogs["Inspect"].limits:
                data = await db.inspects.find_one({"channel": channel})
                if data and data["active"] and data["offline"]:
                    await self.cogs["Inspect"].set(channel)

            self.cooldowns[channel] = {}
            if channel in self.cogs["Links"].cooldowns:
                self.cogs["Links"].cooldowns[channel] = {}

    @routine(minutes=5)
    async def refresh_tokens(self):
        data = await db.config.find_one({"_id": 1})

        if config["Bot"]["refresh_token"] and data["expire_time"] - time.time() < 900:  # refresh bot user token
            url = f'https://id.twitch.tv/oauth2/token?client_id={config["Twitch"]["client_id"]}&client_secret={config["Twitch"]["client_secret"]}&refresh_token={config["Bot"]["refresh_token"]}&grant_type=refresh_token'

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers={"Content-Type": "application/x-www-form-urlencoded"}) as response:
                    response = await response.json()

            self._http.token = self._connection._token = config["Bot"]["access_token"] = response["access_token"]
            config["Bot"]["refresh_token"] = response["refresh_token"]
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
                url = f'https://id.twitch.tv/oauth2/token?client_id={config["Twitch"]["client_id"]}&client_secret={config["Twitch"]["client_secret"]}&refresh_token={refresh_token}&grant_type=refresh_token'

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
