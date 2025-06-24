import io
import logging
import os
import pathlib
import tomllib

import click

from bot import Bot, logger as bot_logger

@click.command()
@click.option('--config', 'config_file', envvar='TSAYBOT_CONFIG_PATH', default='config.toml', type=click.File(mode='rb'))
@click.option('--token', 'token_file', envvar='TSAYBOT_DISCORD_TOKEN_PATH', type=click.File())
@click.option('--logdir', 'logs_dir', envvar='TSAYBOT_LOGS_DIR', type=click.Path(
	file_okay=False, writable=True, executable=True, resolve_path=True, path_type=pathlib.Path
))
@click.option('--eventdir', 'events_dir', envvar='TSAYBOT_EVENTS_DIR', type=click.Path(
	file_okay=False, writable=True, executable=True, resolve_path=True, path_type=pathlib.Path
))
def main(
	config_file: io.BufferedReader,
	token_file: io.TextIOWrapper|None,
	logs_dir: pathlib.Path|None,
	events_dir: pathlib.Path|None
):

	config = tomllib.load(config_file)
	paths_cfg = config.get('paths', {})
	events_dir = events_dir or pathlib.Path(paths_cfg.get('events_dir') or './events')
	logs_dir = logs_dir or pathlib.Path(paths_cfg.get('logs_dir') or './logs')
	os.makedirs(events_dir, mode=0o755, exist_ok=True)
	os.makedirs(logs_dir, mode=0o755, exist_ok=True)

	discord_cfg = config.get('discord', {})
	bot = Bot(
		discord_cfg.get('guild'),
		discord_cfg.get('control_channel'),
		discord_cfg.get('vote_channel'),
		discord_cfg.get('announce_channel'),
		discord_cfg.get('event_channel'),
		discord_cfg.get('member_role'),
		events_dir,
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

	bot.run(token, log_handler=log_handler)

if __name__ == '__main__':

	main()
