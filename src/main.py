import io
import logging
import os
import pathlib
import tomllib

import click

from .bot import Bot, logger as bot_logger
from .commands import SlashBallot, BookSession

@click.command()
@click.option('--config', 'config_file', envvar='TSAYBOT_CONFIG_PATH', default='config.toml', type=click.File(mode='rb'))
@click.option('--token', 'token_file', envvar='TSAYBOT_DISCORD_TOKEN_PATH', type=click.File())
@click.option('--logdir', 'logs_dir', envvar='TSAYBOT_LOGS_DIR', type=click.Path(
	file_okay=False, writable=True, executable=True, resolve_path=True, path_type=pathlib.Path
))
@click.option('--eventdir', 'data_dir', envvar='TSAYBOT_DATA_DIR', type=click.Path(
	file_okay=False, writable=True, executable=True, resolve_path=True, path_type=pathlib.Path
))
def main(
	config_file: io.BufferedReader,
	token_file: io.TextIOWrapper|None,
	logs_dir: pathlib.Path|None,
	data_dir: pathlib.Path|None
):

	config = tomllib.load(config_file)
	paths_cfg = config.get('paths', {})
	data_dir = data_dir or pathlib.Path(paths_cfg.get('data_dir') or './data')
	logs_dir = logs_dir or pathlib.Path(paths_cfg.get('logs_dir') or './logs')
	os.makedirs(data_dir, mode=0o755, exist_ok=True)
	os.makedirs(logs_dir, mode=0o755, exist_ok=True)

	bot = Bot(
		config.get('domains', {}),
		data_dir,
	)

	log_handler = logging.FileHandler(logs_dir / 'discord.log')	# Logs exclusively emitted by the discord.py library
	bot_logger.setLevel(logging.DEBUG)
	handler = logging.FileHandler(logs_dir / 'bot.log')
	formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {message} (task: {taskName})', style = '{')
	handler.setFormatter(formatter)
	bot_logger.addHandler(handler)

	if not token_file:
		token_file = open(paths_cfg.get('token', './token.txt'), 'r')
	token = token_file.read().strip()
	token_file.close()

	for cmd_type in (BookSession, SlashBallot):
		bot.tree.add_command(cmd_type(bot).command)
	bot.run(token, log_handler=log_handler)

if __name__ == '__main__':

	main()
