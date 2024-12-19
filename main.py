import json
import logging

from bot import Bot

with open ('./config.json') as config_file:
	env = json.load(config_file)['default']
bot = Bot(env['server_id'], env['vote_channel_id'], env['announce_channel_id'])

log_handler = logging.FileHandler('discord.log')	# Logs exclusively emitted by the discord.py library
with open('./token.txt') as token_file:
	token = token_file.read().strip()
bot.run(token, log_handler=log_handler)
