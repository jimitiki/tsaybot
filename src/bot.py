from collections import defaultdict
from collections.abc import Callable
from types import CoroutineType
from zoneinfo import ZoneInfo
import aiohttp
import asyncio
import dataclasses
import datetime
import logging
import pathlib
import os
import sys

from bs4 import BeautifulSoup
from discord import (
	app_commands,
	Client,
	EventStatus,
	Guild,
	Intents,
	Message,
	NotFound,
	PrivacyLevel,
	Role,
	TextChannel,
	VoiceChannel,
)

from . import scanner


logger = logging.getLogger('bot')

NY_TZ = ZoneInfo('America/New_York')

class MovieInfo:

	def __init__(self, title: str, year: str|None, url: str, img: bytes|None = None):

		self.title = title
		self.year  = year
		self.url   = url
		self.img   = img

	def __str__(self) -> str:
		if not self.year:
			return self.title
		else:
			return f'{self.title} ({self.year})'

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
			year = doc.find(class_="releasedate").string
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
		return cls(title, year, url, img)

class Timer:

	def __init__(self, wait: Callable[[], CoroutineType] | None, callback: Callable[[], CoroutineType], repeat: bool = True):
		self.wait = wait
		self.callback = callback
		self.repeat = repeat
		self.delay = -1

	async def start(self):

		ten_am_tomorrow = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(10), tzinfo = NY_TZ)
		self.delay = (ten_am_tomorrow - datetime.datetime.now(NY_TZ)).total_seconds()
		asyncio.create_task(self.execute())
		logger.info('Timer started.')

	async def execute(self):
		logger.info(f'Waiting for {self.delay} seconds')
		await asyncio.sleep(self.delay)
		logger.info('Finished waiting')
		if self.wait:
			await self.wait()
		await self.callback()
		if self.repeat:
			asyncio.create_task(self.execute())

@dataclasses.dataclass
class Domain:
	"""
	Contains all of the Discord objects needed for one instance of the bot to function.
	"""

	name: str
	guild: Guild
	control_channel: TextChannel
	vote_channel: TextChannel
	announce_channel: TextChannel
	event_channel: VoiceChannel
	member_role: Role
	data_dir: pathlib.Path

	def __post_init__(self):
		self.data_dir = self.data_dir / self.name
		os.makedirs(self.data_dir, mode=0o755, exist_ok=True)
		try:
			open(self.events_path, 'x').close()
		except FileExistsError:
			pass

	@property
	def events_path(self):
		return self.data_dir / f'events.txt'

	async def handle_command(self, message: Message):
		"""Processes a command in the control channel"""

		if message.channel != self.control_channel:
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
			'channel': self.event_channel,
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

		await self.announce_channel.send(
			f'<@&{self.member_role.id}> You are all cordially invited to [a club meeting]({event.url}) on {event.start_time.strftime('%A, %B %e')} to discuss {info.title}. As always, attendance is optional.'
		)

		with open(self.events_path, 'a') as events_file:
			print(f'{event.id},{info.title},2', file=events_file)

	async def send_reminders(self):
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
		if not event.channel or event.channel != self.event_channel:
			logger.debug(f'Skipping event with ID {event_id} that is not for the voice channel')
			return event_id, film_title, number

		start_time = event.start_time.astimezone(NY_TZ)
		time_remaining = start_time - datetime.datetime.now(NY_TZ)
		logger.info(f'Event with ID {event_id} at {start_time.isoformat()} in {time_remaining.days} days')

		# Reminder on the day of the event
		if time_remaining.days == 0:
			logger.info(f'Announcing day-of reminder for event with ID {event_id} at {start_time.isoformat()}')
			await self.announce_channel.send(f'<@&{self.member_role.id}> We are meeting tonight at 10:00 Eastern (7:00 Pacific) to discuss {film_title}.')
			return None

		# Reminder 2 (or 1) day(s) before the event
		if number == '2' and time_remaining.days <= 2:
			logger.info(f'Announcing 2-day reminder for event with ID {event_id} at {start_time.isoformat()}')
			await self.announce_channel.send(f'<@&{self.member_role.id}> We will be meeting on {start_time.strftime('%A')} to discuss {film_title}.')
			return event_id, film_title, '1'

		else:
			logger.debug(f'Skipping event at {start_time.isoformat()}')
			return event_id, film_title, number

class Bot(Client):

	def __init__(
		self,
		domains_cfg: dict[str,dict],
		data_dir: pathlib.Path,
	):
		intents = Intents.default()
		intents.message_content = True
		super().__init__(intents = intents)

		self.__domains_cfg = domains_cfg
		self.__data_dir = data_dir

		self.domains: list[Domain] = []
		self.__domain_by_vote_channel_id: dict[int,Domain] = {}
		self.__domain_by_control_channel_id: dict[int,Domain] = {}

		self.reminder_timer: Timer | None = None

		self.tree = app_commands.CommandTree(self)

	async def on_ready(self):

		if not self.domains:
			self.load_domains()
		print('Talking shit...')

		# If the reminder task is already defined, don't bother creating a new one or doing reminders right now; they will happen at the designated time.
		if self.reminder_timer:
			return

		self.reminder_timer = Timer(self.wait_until_ready, self.send_reminders)
		await self.reminder_timer.start()

		if self.reminder_timer.delay > 4 * 60 * 60:
			logger.info('Sending immediate reminders')
			asyncio.create_task(self.send_reminders())
		else:
			logger.info('Skipping immediate reminders')

	def load_domains(self):

		self.domains = [
			self.load_domain(name, cfg)
			for name, cfg in self.__domains_cfg.items()
		]

		domains_by_channel = defaultdict(set)
		for domain in self.domains:
			domains_by_channel[domain.vote_channel].add(domain.name)
			domains_by_channel[domain.control_channel].add(domain.name)
		for channel_id, domains in domains_by_channel.items():
			if len(domains) > 1:
				raise RuntimeError(f"The following domains use the same channel ({channel_id}) as a voting and/or control channel: {', '.join(domains)}")

		self.__domain_by_control_channel_id = {
			domain.control_channel.id: domain
			for domain in self.domains
		}
		self.__domain_by_vote_channel_id = {
			domain.vote_channel.id: domain
			for domain in self.domains
		}

	def load_domain(self, name: str, cfg: dict[str,int]):
		guild = self.get_guild(cfg['guild'])
		if not guild:
			raise RuntimeError(f'Failed to access guild with ID {cfg['guild']}.')

		control_channel = self.get_channel(cfg['control_channel'])
		if not control_channel:
			raise RuntimeError(f'Failed to access channel with ID {cfg['control_channel']}.')
		if not isinstance(control_channel, TextChannel):
			raise RuntimeError(f'Control channel must be a text channel. Got {type(control_channel)} (ID: {cfg['control_channel']})')
		if control_channel.guild != guild:
			raise RuntimeError(f'Specified control channel is not part of the Guild.')

		vote_channel = self.get_channel(cfg['vote_channel'])
		if not vote_channel:
			raise RuntimeError(f'Failed to access channel with ID {cfg['vote_channel']}.')
		if not isinstance(vote_channel, TextChannel):
			raise RuntimeError(f'Vote channel must be a text channel. Got {type(vote_channel)} (ID: {cfg['vote_channel']})')
		if control_channel.guild != guild:
			raise RuntimeError(f'Specified control channel is not part of the Guild.')

		announce_channel = self.get_channel(cfg['announce_channel'])
		if not announce_channel:
			raise RuntimeError(f'Failed to access channel with ID {cfg['announce_channel']}.')
		if not isinstance(announce_channel, TextChannel):
			raise RuntimeError(f'Announcement channel must be a text channel. Got {type(announce_channel)} (ID: {cfg['announce_channel']})')
		if announce_channel.guild != guild:
			raise RuntimeError(f'Specified announcement channel is not part of the Guild.')

		event_channel = self.get_channel(cfg['event_channel'])
		if not event_channel:
			raise RuntimeError(f'Failed to access channel with ID {cfg['event_channel']}.')
		if not isinstance(event_channel, VoiceChannel):
			raise RuntimeError(f'Event channel must be a voice channel. Got {type(event_channel)} (ID: {cfg['event_channel']})')
		if event_channel.guild != guild:
			raise RuntimeError(f'Specified event channel is not part of the Guild.')

		member_role = guild.get_role(cfg['member_role'])
		if not member_role:
			raise RuntimeError(f'Failed to access role with ID {cfg['member_role']}.')
		if member_role.guild != guild:
			raise RuntimeError(f'Specified member role is not part of the Guild.')

		return Domain(name, guild, control_channel, vote_channel, announce_channel, event_channel, member_role, self.__data_dir)

	def resolve_domain(self, channel: TextChannel | int) -> Domain | None:
		if isinstance(channel, int):
			channel_id = channel
		else:
			channel_id = channel.id
		return self.__domain_by_control_channel_id.get(channel_id) or self.__domain_by_vote_channel_id.get(channel_id)

	async def on_message(self, message: Message):

		domain = self.resolve_domain(message.channel.id)
		if not domain:
			return
		if self.user not in message.mentions:
			logger.info('Skipping message that does not @ mention bot')
			return
		await domain.handle_command(message)

	async def send_reminders(self):

		logger.info('Sending reminders')
		async with asyncio.TaskGroup() as tg:
			for domain in self.domains:
				tg.create_task(domain.send_reminders())
