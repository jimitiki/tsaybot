import json
import logging

from bot import Bot

with open ('./config.json') as config_file:
	env = json.load(config_file)['default']
bot = Bot(env['server'], env['vote_channel'], env['announce_channel'], env['voice_channel'], env['role'])

log_handler = logging.FileHandler('discord.log')	# Logs exclusively emitted by the discord.py library
with open('./token.txt') as token_file:
	token = token_file.read().strip()
bot.run(token, log_handler=log_handler)
