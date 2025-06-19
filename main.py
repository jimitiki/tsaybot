import io
import json
import logging

import click

from bot import Bot

@click.command()
def main(config_path: io.TextIOWrapper):
@click.option('--config', 'config_file', envvar='TSAYBOT_CONFIG_PATH', default='config.json', type=click.File())
def main(config_file: io.TextIOWrapper):

	config = json.load(config_file)['default']
	bot = Bot(config['server'], config['vote_channel'], config['announce_channel'], config['voice_channel'], config['role'])

	log_handler = logging.FileHandler('discord.log')	# Logs exclusively emitted by the discord.py library
	with open('token.txt') as token_file:
		token = token_file.read().strip()
	bot.run(token, log_handler=log_handler)

if __name__ == '__main__':

	main()
