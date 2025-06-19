import io
import logging
import os
import pathlib
import tomllib

import click

from bot import Bot, logger as bot_logger

@click.command()
@click.option('--config', 'config_file', envvar='TSAYBOT_CONFIG_PATH', default='config.toml', type=click.File(mode='rb'))
@click.option('--token', 'token_file', envvar='TSAYBOT_DISCORD_TOKEN_PATH', default='token.txt', type=click.File())
@click.option('--logdir', 'logs_dir', envvar='TSAYBOT_LOGS_DIR', default='./logs', type=click.Path(
	file_okay=False, writable=True, executable=True, resolve_path=True, path_type=pathlib.Path
))
def main(config_file: io.BufferedReader, token_file: io.TextIOWrapper, logs_dir: pathlib.Path):

	config = tomllib.load(config_file)
	discord_cfg = config['discord']
	bot = Bot(discord_cfg['server'], discord_cfg['vote_channel'], discord_cfg['announce_channel'], discord_cfg['voice_channel'], discord_cfg['role'])

	os.makedirs(logs_dir, mode=0o755, exist_ok=True)
	log_handler = logging.FileHandler(logs_dir / 'discord.log')	# Logs exclusively emitted by the discord.py library
	bot_logger.setLevel(logging.DEBUG)
	handler = logging.FileHandler(logs_dir / 'bot.log')
	formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {message} (task: {taskName})', style = '{')
	handler.setFormatter(formatter)
	bot_logger.addHandler(handler)
	token = token_file.read().strip()
	bot.run(token, log_handler=log_handler)

if __name__ == '__main__':

	main()
