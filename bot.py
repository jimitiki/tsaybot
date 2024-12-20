from zoneinfo import ZoneInfo
import asyncio
import datetime
import logging
import sys

from bs4 import BeautifulSoup
from discord import Client, DMChannel, Guild, Intents, Message, PrivacyLevel
import requests

import scanner


logger = logging.getLogger('bot')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('bot.log')
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {message} (task: {taskName})', style = '{')
handler.setFormatter(formatter)
logger.addHandler(handler)

NY_TZ = ZoneInfo('America/New_York')

class Bot(Client):

	def __init__(self, guild_id: int, vote_channel_id: int, announce_channel_id: int, voice_channel_id: int):
		intents = Intents.default()
		intents.message_content = True
		super().__init__(intents = intents)
		self.guild_id = guild_id
		self.vote_channel_id = vote_channel_id
		self.announce_channel_id = announce_channel_id
		self.voice_channel_id = voice_channel_id
		self.bg_tasks = set()

	@property
	def guild(self) -> Guild | None:
		return self.get_guild(self.guild_id)

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
		"""
		Creates a scheduled event in the configured server based on the provided parameters. Announces the event in the announcement channel.

		This function assumes that the event will be on the Wednesday of the week after next from the current date at 7:00 PM Eastern.

		:param film_title: Title of the selected film. Used in the title of the event
		:param release_year: Year the film was released. Used in the title of the event. Optional.
		:param img: Raw binary data representing the image. Must be a PNG or JPEG format. Optional.
		"""

		date = datetime.date.today() + datetime.timedelta(days=14 - (datetime.date.today().weekday() - 2))
		kwargs = {
			'name': f'TSAY: {film_title}{(" (" + release_year + ")") if release_year else ""}',
			'start_time': datetime.datetime.combine(date, datetime.time(10), NY_TZ),
			'channel': self.get_channel(self.voice_channel_id),
			'privacy_level': PrivacyLevel.guild_only,
		}
		if img:
			kwargs['image'] = img

		try:
			event = await self.guild.create_scheduled_event( **kwargs )
		except Exception:
			logger.exception('Failed to create event', exc_info=sys.exc_info())
			return
		logger.info(f'Created event (ID={event.id})')

		await self.launch_task(
			self.get_channel(self.announce_channel_id).send(
				f'<@&1298872652366221312> You are all cordially invited to [a club meeting]({event.url}) on {event.start_time.strftime('%A, %B %e')}'
				f' to discuss {film_title}. As always, attendance is optional.'
			)
		)

		with open('events.txt', 'a') as events_file:
			print(f'{event.id},{film_title},2', file=events_file)

	async def launch_task(self, coro):
		"""Starts the task and ensures that it will not be garbarge collected until it finishes."""

		task = asyncio.create_task(coro)
		self.bg_tasks.add(task)
		task.add_done_callback(self.bg_tasks.discard)
