import os
import time

import aiohttp
import motor.motor_asyncio
from cryptography.fernet import Fernet


client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv('MONGO'))
db = client.modboty

fernet = Fernet(os.getenv('KEY').encode())


async def get_config():
    data = await db.config.find_one({'_id': 1})
    token = fernet.decrypt(data['access_token'].encode()).decode()
    refresh_token = fernet.decrypt(data['refresh_token'].encode()).decode() if 'refresh_token' in data else None
    os.environ['CHANNELS'] = '&'.join(data['channels'])

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
                await db.config.update_one({'_id': 1}, {'$set': {'access_token': enc_token, 'refresh_token': enc_refresh, 'expire_time': time.time() + response['expires_in']}})

    os.environ['REFRESH_TOKEN'] = refresh_token
    os.environ['TOKEN'] = token


loop = client.get_io_loop()
loop.run_until_complete(get_config())
