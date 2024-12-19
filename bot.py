from discord import Client, DMChannel, Intents, Message

import emoji

class Bot(Client):

	def __init__(self, guild_id: int, vote_channel_id: int, announce_channel_id: int):
		intents = Intents.default()
		intents.message_content = True
		super().__init__(intents = intents)
		self.guild_d = guild_id
		self.vote_channel_id = vote_channel_id
		self.announce_channel_id = announce_channel_id

	async def on_ready(self):
		print('Talking shit...')

	async def on_message(self, message: Message):

		if isinstance(message.channel, DMChannel) and message.author.id == 329839605857910785:
			print(f'A DM from my creator: {message.content}')
		if message.channel.id == self.vote_channel_id:
			print(f'A message in the vote channel: {message.content}')
