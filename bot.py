from zoneinfo import ZoneInfo
import aiohttp
import asyncio
import datetime
import logging
import pathlib
import sys

from bs4 import BeautifulSoup
from discord import Client, EventStatus, Guild, Intents, Message, PrivacyLevel, NotFound
from discord.abc import Messageable

import scanner


logger = logging.getLogger('bot')

NY_TZ = ZoneInfo('America/New_York')

class MovieInfo:

	def __init__(self, title: str|None, year: str|None, img: bytes|None = None):

		self.title = title
		self.year  = year
		self.img   = img

	@classmethod
	async def from_url(cls, url: str, fetch_image: bool = False):
		try:
			async with aiohttp.request('get', url) as resp:
				html = await resp.text()
		except Exception:
			logger.exception('Failed to retrieve webpage', exc_info=sys.exc_info())
			raise

		# Scrape HTML to find film title, release year, and backdrop image (if it exists)
		doc = BeautifulSoup(html, 'html.parser')
		try:
			title = doc.find(class_='js-widont').string
		except Exception:
			logger.exception('Failed to read film title', exc_info=sys.exc_info())
			raise
		try:
			year = doc.find(class_="metablock").find("div", class_="releaseyear").string
		except Exception:
			logger.warning('Failed to read release year', exc_info=sys.exc_info())
			year = None
		if fetch_image:
			backdrop = doc.find(id='backdrop')
			if not backdrop:
				logger.debug('Letterboxd page missing backdrop')
				img = None
			else:
				try:
					async with aiohttp.request('get', backdrop['data-backdrop']) as resp:
						img = await resp.read()
				except Exception:
					logger.debug('Failed to retrieve backdrop image', exc_info=sys.exc_info())
					img = None
		else:
			img = None
		logger.info('Finished scraping Letterboxd page')
		return cls(title, year, img)

class Bot(Client):

	def __init__(
		self,
		guild_id: int,
		vote_channel_id: int,
		announce_channel_id: int,
		event_channel_id: int,
		control_channel_id: int,
		member_role_id: int,
		events_dir: pathlib.Path
	):
		intents = Intents.default()
		intents.message_content = True
		super().__init__(intents = intents)

		if not guild_id:
			raise ValueError('No Guild ID provided.')
		if not control_channel_id:
			raise ValueError('No control Channel ID provided.')
		if not vote_channel_id:
			raise ValueError('No vote Channel ID provided.')
		if not announce_channel_id:
			raise ValueError('No announce Channel ID provided.')
		if not event_channel_id:
			raise ValueError('No voice Channel ID provided.')
		if not member_role_id:
			raise ValueError('No role ID provided.')

		self.guild_id = guild_id
		self.control_channel_id = control_channel_id
		self.vote_channel_id = vote_channel_id
		self.announce_channel_id = announce_channel_id
		self.event_channel_id = event_channel_id
		self.reminder_task = None
		self.member_role_id = member_role_id
		self.events_path = events_dir / f'events-{guild_id}.txt'

		try:
			with open(self.events_path, 'x'):
				pass
		except FileExistsError:
			pass

	@property
	def guild(self) -> Guild:
		guild = self.get_guild(self.guild_id)
		if guild is None:
			raise RuntimeError('Failed to access Guild. Either the Guild does not exist or the Client is not completely ready.')
		return guild

	def get_channel(self, channel_id: int, /):

		channel = super().get_channel(channel_id)
		if channel is None:
			raise RuntimeError(f'Failed to access Channel with ID {channel_id}. Either the Channel does not exist or the Client is not completely ready.')
		if not isinstance(channel, Messageable):
			raise RuntimeError(f'Channel with ID {channel_id} does not support messages.')
		return channel

	async def on_ready(self):

		print('Talking shit...')

		# If the reminder task is already defined, don't bother creating a new one or doing reminders right now; they will happen at the designated time.
		if self.reminder_task:
			return
		self.reminder_task = asyncio.create_task(self.run_reminders())
		await asyncio.create_task(self.send_reminders())

	async def run_reminders(self):

		ten_am_tomorrow = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(10), tzinfo = NY_TZ)
		delay = (ten_am_tomorrow - datetime.datetime.now(NY_TZ)).total_seconds()
		logger.info(f'Waiting for {delay} seconds')
		await asyncio.sleep(delay)
		logger.info('Finished waiting')
		await self.wait_until_ready()
		await self.send_reminders()
		self.reminder_task = asyncio.create_task(self.run_reminders())

	async def on_message(self, message: Message):

		if message.channel.id == self.control_channel_id:
			await self.handle_command(message)
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

	async def handle_command(self, message: Message):
		"""Processes a command in the control channel"""

		if self.user not in message.mentions:
			logger.info('Skipping message that does not @ mention bot')
			return

		logger.debug(f'Control message: «{message.content}»')
		content = message.content.strip().partition(' ')[2].strip()
		if not scanner.is_url(content):
			logger.warning('Control message did not contain a URL')
			await message.channel.send('Invalid URL')
			return
		await self.schedule_event(await MovieInfo.from_url(content, fetch_image=True))

	async def schedule_event(self, info: MovieInfo):
		"""
		Creates a scheduled event in the configured server based on the provided parameters. Announces the event in the announcement channel.

		This function assumes that the event will be on the Wednesday of the week after next from the current date at 7:00 PM Eastern.

		:param film_title: Title of the selected film. Used in the title of the event
		:param release_year: Year the film was released. Used in the title of the event. Optional.
		:param img: Raw binary data representing the image. Must be a PNG or JPEG format. Optional.
		"""

		date = datetime.date.today() + datetime.timedelta(days=14 - (datetime.date.today().weekday() - 2))
		kwargs = {
			'name': f'TSAY: {info.title}{(" (" + info.year + ")") if info.year else ""}',
			'start_time': datetime.datetime.combine(date, datetime.time(22), NY_TZ),
			'channel': self.get_channel(self.event_channel_id),
			'privacy_level': PrivacyLevel.guild_only,
		}
		if info.img:
			kwargs['image'] = info.img

		try:
			event = await self.guild.create_scheduled_event( **kwargs )
		except Exception:
			logger.exception('Failed to create event', exc_info=sys.exc_info())
			return
		logger.info(f'Created event (ID={event.id})')

		await self.get_channel(self.announce_channel_id).send(
			f'<@&{self.member_role_id}> You are all cordially invited to [a club meeting]({event.url}) on {event.start_time.strftime('%A, %B %e')} to discuss {info.title}. As always, attendance is optional.'
		)

		with open(self.events_path, 'a') as events_file:
			print(f'{event.id},{info.title},2', file=events_file)

	async def send_reminders(self):

		logger.info('Sending reminders')
		with open(self.events_path) as events_file:
			events = [
				line.strip().split(',')
				for line in events_file.readlines()
			]
		async with asyncio.TaskGroup() as tg:
			tasks = [
				tg.create_task(self.remind_event(event_id, film_title, number))
				for event_id, film_title, number in events
			]

		results = await asyncio.gather(*tasks)
		with open(self.events_path, 'w') as events_file:
			for result in results:
				if result:
					print(','.join(result), file=events_file)
		logger.info('Reminders completed')

	async def remind_event(self, event_id: str, film_title: str, number: str) -> tuple[str,str,str] | None:

		try:
			event = await self.guild.fetch_scheduled_event(int(event_id))
		except NotFound:
			logger.warning(f'Failed to find scheduled event with id {event_id} ({film_title})')
			return None
		if event.status is not EventStatus.scheduled:
			logger.debug(f'Skipping event with ID {event_id} due to its status: {event.status}')
			return None
		if not event.channel or event.channel.id != self.event_channel_id:
			logger.debug(f'Skipping event with ID {event_id} that is not for the voice channel')
			return event_id, film_title, number

		start_time = event.start_time.astimezone(NY_TZ)
		time_remaining = start_time - datetime.datetime.now(NY_TZ)
		logger.info(f'Event with ID {event_id} at {start_time.isoformat()} in {time_remaining.days} days')

		# Reminder on the day of the event
		if time_remaining.days == 0:
			logger.info(f'Announcing day-of reminder for event with ID {event_id} at {start_time.isoformat()}')
			await self.get_channel(self.announce_channel_id).send(f'<@&{self.member_role_id}> We are meeting tonight at 10:00 Eastern (7:00 Pacific) to discuss {film_title}.')
			return None

		# Reminder 2 (or 1) day(s) before the event
		if number == '2' and time_remaining.days <= 2:
			logger.info(f'Announcing 2-day reminder for event with ID {event_id} at {start_time.isoformat()}')
			await self.get_channel(self.announce_channel_id).send(f'<@&{self.member_role_id}> We will be meeting on {start_time.strftime('%A')} to discuss {film_title}.')
			return event_id, film_title, '1'

		else:
			logger.debug(f'Skipping event at {start_time.isoformat()}')
			return event_id, film_title, number
