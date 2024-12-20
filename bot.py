import asyncio
import logging
import sys

from bs4 import BeautifulSoup
from discord import Client, DMChannel, Intents, Message
import requests

import scanner


logger = logging.getLogger('bot')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('bot.log')
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {message} (task: {taskName})', style = '{')
handler.setFormatter(formatter)
logger.addHandler(handler)

class Bot(Client):

	def __init__(self, guild_id: int, vote_channel_id: int, announce_channel_id: int):
		intents = Intents.default()
		intents.message_content = True
		super().__init__(intents = intents)
		self.guild_id = guild_id
		self.vote_channel_id = vote_channel_id
		self.announce_channel_id = announce_channel_id

	async def on_ready(self):
		print('Talking shit...')

	async def on_message(self, message: Message):

		if isinstance(message.channel, DMChannel) and message.author.id == 329839605857910785:
			await self.handle_dm(message)
		if message.channel.id == self.vote_channel_id:
			await self.handle_ballot(message)

	async def handle_ballot(self, message: Message):
		"""Processes a message in the voting channel"""

		logger.info(f'New message in the vote channel: «{message.content}»')
		emoji = list(scanner.find_emoji(message.content))
		logger.debug(f'Extracted emoji: [{", ".join(str(e) for e in emoji)}]')
		async with asyncio.TaskGroup() as tg:
			for e in emoji:
				tg.create_task(message.add_reaction(e), name = f'add reaction: {emoji!s}')

	async def handle_dm(self, message: Message):
		"""Processes a direct message"""

		logger.debug(f'DM from my creator: «{message.content}»')
		content = message.content.strip()
		if not scanner.is_url(content):
			logger.warning('DM did not contain a URL')
			await message.channel.send('Invalid URL')
			return

		try:
			html = requests.get(content).content
		except Exception:
			logger.exception('Failed to retrieve webpage', exc_info=sys.exc_info())
			return

		# Scrape HTML to find film title, release year, and backdrop image (if it exists)
		doc = BeautifulSoup(html, 'html.parser')
		try:
			title = doc.find(class_='js-widont').string
		except Exception:
			logger.exception('Failed to read film title', exc_info=sys.exc_info())
			return
		try:
			year = doc.find(class_="metablock").find("div", class_="releaseyear").string
		except Exception:
			logger.warning('Failed to read release year', exc_info=sys.exc_info())
			year = None
		backdrop = doc.find(id='backdrop')
		if not backdrop:
			logger.debug('Letterboxd page missing backdrop')
			img = None
		else:
			try:
				img = requests.get(backdrop['data-backdrop']).content
			except Exception:
				logger.debug('Failed to retrieve backdrop image', exc_info=sys.exc_info())
				img = None
		logger.info('Finished scraping Letterboxd page')
		await self.schedule_event(title, year, img)

	async def schedule_event(self, film_title: str, release_year: str | None, img: bytes | None):

		print(film_title, release_year, type(img))

