import os
import asyncio

import aiohttp
import motor.motor_asyncio
from cryptography.fernet import Fernet

db = motor.motor_asyncio.AsyncIOMotorClient(os.getenv('MONGO')).modboty

fernet = Fernet(os.getenv('KEY').encode())


async def get_channels():
    data = await db.config.find_one({'_id': 1})
    token = fernet.decrypt(data['test1'].encode()).decode()
    refresh_token = fernet.decrypt(data['test2'].encode()).decode()
    channels = data['channels']
    os.environ['CHANNELS'] = '&'.join(channels)

    url = 'https://id.twitch.tv/oauth2/validate'
    headers = {'Authorization': f'OAuth {token}'}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 401:
                url = f'https://id.twitch.tv/oauth2/token?client_id={os.getenv("CLIENT_ID")}&client_secret={os.getenv("CLIENT_SECRET")}&refresh_token={refresh_token}&grant_type=refresh_token'

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers={'Content-Type': 'application/x-www-form-urlencoded'}) as response:
                        response = await response.json()

                token = response['access_token']
                refresh_token = response['refresh_token']
                enc_token = fernet.encrypt(token.encode()).decode()
                enc_refresh = fernet.encrypt(refresh_token.encode()).decode()
                await db.config.update_one({'_id': 1}, {'$set': {'access_token': enc_token, 'refresh_token': enc_refresh}})

    os.environ['TOKEN'] = token
    os.environ['REFRESH_TOKEN'] = refresh_token


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(get_channels())
