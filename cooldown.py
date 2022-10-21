import time


def get_cooldown_end(data):
    cooldown = data.cooldown
    now = time.time()
    per_end = now + cooldown['per']
    gen_end = now + cooldown['gen']
    return per_end, gen_end


class Cooldown:

    def __init__(self, channels):
        self.cooldowns = {channel: {} for channel in channels}

    async def handle_command(self, command, message, admin=False):
        now = time.time()
        data = self.get_command(command)

        channel = message.channel.name

        if not admin:
            user = message.author.name
            if not message.author.is_mod or 'admin' in data.flags:
                return
            if command in self.cooldowns[channel]:
                if self.cooldowns[channel][command]['gen'] < now > self.cooldowns[channel][command]['per'].get(user, 0):
                    per, gen = get_cooldown_end(data)
                    self.cooldowns[channel][command]['per'][user], self.cooldowns[channel][command]['gen'] = per, gen
                    return True

                return

            per_end, gen_end = get_cooldown_end(data)
            self.cooldowns[channel][command] = {'per': {user: per_end}, 'gen': gen_end}
            return True

        if 'admin' in data.flags:
            return True

        if command in self.cooldowns[channel]:
            _, self.cooldowns[channel][command]['gen'] = get_cooldown_end(data)
            return True

        _, gen_end = get_cooldown_end(data)
        self.cooldowns[channel][command] = {'per': {}, 'gen': gen_end}
        return True
