import io
import logging
import tomllib

import click

from bot import Bot, logger as bot_logger

@click.command()
@click.option('--config', 'config_file', envvar='TSAYBOT_CONFIG_PATH', default='config.toml', type=click.File(mode='rb'))
@click.option('--token', 'token_file', envvar='TSAYBOT_DISCORD_TOKEN_PATH', default='token.txt', type=click.File())
def main(config_file: io.BufferedReader, token_file: io.TextIOWrapper):

	config = tomllib.load(config_file)
	discord_cfg = config['discord']
	bot = Bot(discord_cfg['server'], discord_cfg['vote_channel'], discord_cfg['announce_channel'], discord_cfg['voice_channel'], discord_cfg['role'])

	log_handler = logging.FileHandler('discord.log')	# Logs exclusively emitted by the discord.py library
	bot_logger.setLevel(logging.DEBUG)
	handler = logging.FileHandler('bot.log')
	formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {message} (task: {taskName})', style = '{')
	handler.setFormatter(formatter)
	bot_logger.addHandler(handler)
	token = token_file.read().strip()
	bot.run(token, log_handler=log_handler)

if __name__ == '__main__':

	main()
