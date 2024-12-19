import json

from bot import Bot

with open ('./config.json') as config_file:
	env = json.load(config_file)['default']
bot = Bot(env['server_id'], env['vote_channel_id'], env['announce_channel_id'])

with open('./token.txt') as token_file:
	token = token_file.read().strip()
bot.run(token)
