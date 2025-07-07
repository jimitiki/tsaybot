from collections import defaultdict
from collections.abc import Callable, Iterable
from types import CoroutineType
from typing import Self
from zoneinfo import ZoneInfo
import aiohttp
import asyncio
import dataclasses
import datetime
import json
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
	PrivacyLevel,
	Role,
	ScheduledEvent,
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

@dataclasses.dataclass
class Session:

	id: int
	title: str
	reminder_count: int

	def todict(self) -> dict:
		return {'id': self.id, 'film_title': self.title, 'reminder_count': self.reminder_count}

	@classmethod
	def fromdict(cls, d: dict) -> Self:
		return cls(d['id'], d['film_title'], d['reminder_count'])

	def replace(self, **changes):
		return dataclasses.replace(self, **changes)

@dataclasses.dataclass
class ClubMember:

	id: int
	given_name: str
	surname: str
	dob: datetime.date | None

	@classmethod
	def fromdict(cls, d: dict) -> Self:
		dob_iso = d.get('dob')
		dob = None if not dob_iso else datetime.date.fromisoformat(dob_iso)
		return cls(
			id = d['id'],
			given_name = d['given_name'],
			surname = d['surname'],
			dob = dob,
		)

	def todict(self) -> dict:
		return {
			'id': self.id,
			'given_name': self.given_name,
			'surname': self.surname,
			'dob': self.dob,
		}

	def is_birthday(self, tz: datetime._TzInfo) -> bool:
		if not self.dob:
			return False
		today = datetime.datetime.now(tz).date()
		return (today.month, today.day) == (self.dob.month, self.dob.day)

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
			events_file = open(self.events_path, 'x')
		except FileExistsError:
			pass
		else:
			json.dump([], events_file)
			events_file.close()

		try:
			members_file = open(self.members_path, 'x')
		except FileExistsError:
			pass
		else:
			json.dump([], members_file)
			members_file.close()

	@property
	def events_path(self):
		return self.data_dir / 'events.json'

	@property
	def members_path(self):
		return self.data_dir / 'members.json'

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

		events = self.read_sessions() + [Session(event.id, info.title, 2)]
		self.write_sessions(events)

	async def announce(self):
		async with asyncio.TaskGroup() as tg:
			event_task = tg.create_task(self.announce_events())
		announcements = event_task.result()
		if len(announcements) == 1:
			await self.announce_channel.send(
				f'<@&{self.member_role.id}> {announcements[0]}'
			)
		elif announcements:
			await self.announce_channel.send(
				f'<@&{self.member_role.id}> I have some announcements to make:\n'
				+ '\n'.join(f"- {announcement}" for announcement in announcements)
			)
		logger.info(f'Finished making {len(announcements)} announcements')

	async def announce_events(self) -> list[str]:
		sessions = self.read_sessions()
		async with asyncio.TaskGroup() as tg:
			tasks = [
				tg.create_task(self.announce_event(event))
				for event in sessions
			]

		results = await asyncio.gather(*tasks)
		self.write_sessions([result[0] for result in results if result[0]])
		logger.info('Reminders completed')
		return [result[1] for result in results if result[1]]

	async def announce_event(self, session: Session) -> tuple[Session|None,str|None]:

		event = self.guild.get_scheduled_event(int(session.id))
		if event is None:
			logger.warning(f'Failed to find scheduled event with id {session.id} ({session.title})')
			return None, None
		if event.status is not EventStatus.scheduled:
			logger.debug(f'Skipping event with ID {session.id} due to its status: {event.status}')
			return None, None
		if not event.channel or event.channel != self.event_channel:
			logger.debug(f'Skipping event with ID {session.id} that is not for the voice channel')
			return None, None

		start_time = event.start_time.astimezone(NY_TZ)
		time_remaining = start_time - datetime.datetime.now(NY_TZ)
		logger.info(f'Event with ID {session.id} at {start_time.isoformat()} in {time_remaining.days} days')

		if time_remaining.days < 0:
			logger.info(f'Skipping event with ID {session.id} because it is scheduled for a previous day.')
			return None, None

		elif time_remaining.days == 0:
			logger.info(f'Announcing day-of reminder for event with ID {session.id} at {start_time.isoformat()}')
			return None, f'We are meeting tonight at 10:00 Eastern (7:00 Pacific) to discuss {session.title}.'

		elif time_remaining.days <= 2 and session.reminder_count >= 2:
			logger.info(f'Announcing 2-day reminder for event with ID {session.id} at {start_time.isoformat()}')
			return session.replace(reminder_count=1), f'We will be meeting on {start_time.strftime('%A')} to discuss {session.title}.'

		else:
			logger.debug(f'Skipping event at {start_time.isoformat()}')
			return session, None

	def read_sessions(self) -> list[Session]:
		try:
			events_file = open(self.events_path)
		except FileNotFoundError:
			return []
		events = json.load(events_file)
		events_file.close()
		return [
			Session.fromdict(event)
			for event in events
		]

	def write_sessions(self, sessions: Iterable[Session]):
		with open(self.events_path, 'w') as events_file:
			json.dump([session.todict() for session in sessions if session], events_file)

	def read_members(self) -> list[ClubMember]:
		try:
			members_file = open(self.members_path)
		except FileNotFoundError:
			return []
		members = json.load(members_file)
		members_file.close()
		return [
			ClubMember.fromdict(member)
			for member in members
		]
	
	def write_members(self, members: Iterable[ClubMember | None]):
		with open(self.members_path, 'w') as members_file:
			json.dump([member.todict() for member in members if member], members_file)

	async def handle_updated_event(self, before: ScheduledEvent, after: ScheduledEvent):

		sessions = self.read_sessions()
		session = {
			session.id: session for session in sessions
		}.get(after.id)
		if not session:
			return

		if before.start_time != after.start_time:
			await self.announce_channel.send(f'<@&{self.member_role.id}> The upcoming session to discuss {session.title} has been rescheduled to {after.start_time.strftime('%A, %B %e')}.')		
		session.reminder_count = 2
		self.write_sessions(sessions)

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

		self.domains: dict[int,Domain] = {}

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

		domains = [
			self.load_domain(name, cfg)
			for name, cfg in self.__domains_cfg.items()
		]

		domains_by_guild = defaultdict(set)
		for domain in domains:
			domains_by_guild[domain.guild.id].add(domain.name)
		if any(len(guild_domains) > 1 for guild_domains in domains_by_guild.values()):
			raise RuntimeError(f'''Each Discord server may only have a single domain. The following servers have multiple domains:
{'\n  -'.join(f'{guild}: {", ".join(guild_domains)}' for guild, guild_domains in domains_by_guild if len(domains_by_guild) > 1)}''')
		self.domains = {
			domain.guild.id: domain
			for domain in domains
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

	def resolve_domain(self, guild: int | Guild | None) -> Domain | None:
		if not guild:
			return None
		if isinstance(guild, Guild):
			guild = guild.id
		return self.domains.get(guild)

	async def on_message(self, message: Message):

		domain = self.resolve_domain(message.guild)
		if not domain:
			return
		if self.user not in message.mentions:
			logger.info('Skipping message that does not @ mention bot')
			return
		await domain.handle_command(message)

	async def on_scheduled_event_update(self, before: ScheduledEvent, after: ScheduledEvent):

		domain = self.resolve_domain(after.guild)
		if not domain:
			return
		if before.channel_id != after.channel_id:
			return
		if after.channel_id != domain.event_channel.id:
			return
		await domain.handle_updated_event(before, after)

	async def send_reminders(self):

		logger.info('Sending reminders')
		async with asyncio.TaskGroup() as tg:
			for domain in self.domains.values():
				tg.create_task(domain.announce())
