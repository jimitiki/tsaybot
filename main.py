# import logging

from bot import Bot

with open( './token.txt' ) as token_file:
	token = token_file.read().strip()

guild_id = 329842858909499392
vote_channel_id = 660970005248344085
announce_channel_id = 1298875448133943348

bot = Bot(guild_id, vote_channel_id, announce_channel_id)
bot.run(token)
