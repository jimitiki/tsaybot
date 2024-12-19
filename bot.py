import asyncio
import logging

from discord import Client, DMChannel, Intents, Message

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
			logger.info(f'DM from my creator: «{message.content}»')
		if message.channel.id == self.vote_channel_id:
			logger.info(f'New message in the vote channel: «{message.content}»')
			emoji = list(scanner.find_emoji(message.content))
			logger.debug(f'Extracted emoji: [{", ".join(str(e) for e in emoji)}]')
			asyncio.gather(*(
				asyncio.create_task(message.add_reaction(e), name = f'add reaction: {e!s}')
				for e in emoji
			))


