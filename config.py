import os
import asyncio

import motor.motor_asyncio

db = motor.motor_asyncio.AsyncIOMotorClient(os.getenv('MONGO')).modboty

CHANNELS = []


async def get_channels():
    data = await db.config.find_one({'_id': 1})
    global CHANNELS
    CHANNELS = data['channels']


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(get_channels())
