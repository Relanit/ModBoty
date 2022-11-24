import time
import configparser
import logging

import aiohttp
import motor.motor_asyncio
from cryptography.fernet import Fernet

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)
log_handler = logging.FileHandler("bot.log", "w")
log_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
logger.addHandler(log_handler)

config = configparser.ConfigParser()
config.read("../config.ini")

client = motor.motor_asyncio.AsyncIOMotorClient(config["Mongo"]["mongo"])
db = client.modboty

fernet = Fernet(config["Mongo"]["key"].encode())


async def get_config():
    data = await db.config.find_one({"_id": 1})
    access_token = config["Bot"]["access_token"] or fernet.decrypt(data["access_token"].encode()).decode()
    refresh_token = fernet.decrypt(data["refresh_token"].encode()).decode() if "refresh_token" in data else ""
    config["Bot"]["channels"] = config["Bot"]["channels"] or " ".join(data["channels"])

    if refresh_token:
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"OAuth {access_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    url = f'https://id.twitch.tv/oauth2/token?client_id={config["Twitch"]["client_id"]}&client_secret={config["Twitch"]["client_secret"]}&refresh_token={refresh_token}&grant_type=refresh_token'

                    async with session.post(
                        url,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ) as response:
                        response = await response.json()

                    access_token = response["access_token"]
                    refresh_token = response["refresh_token"]
                    enc_token = fernet.encrypt(access_token.encode()).decode()
                    enc_refresh = fernet.encrypt(refresh_token.encode()).decode()
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
                    logger.info("Bot token expired, new token generated")

    config["Bot"]["refresh_token"] = refresh_token
    config["Bot"]["access_token"] = access_token


loop = client.get_io_loop()
loop.run_until_complete(get_config())
