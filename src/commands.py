from collections.abc import Callable, Coroutine
import asyncio
import datetime
import random

from discord import app_commands, AppCommandType, Interaction, Message, Poll
from discord.abc import Messageable
from discord.ui import Modal, TextInput

from . import scanner
from .bot import Bot, MovieInfo, logger
from .emojis import EMOJIS

class VotingError(Exception):
	def __init__(self, msg: str, response: str, *args):
		super().__init__(msg, *args)
		self.response = response

class Command:

	def __init__(self, client: Bot):
		self.client = client
		self.command = self.make_command()

	def make_command(self) -> app_commands.Command | app_commands.ContextMenu:
		raise NotImplemented

class SlashBallot(Command):

	class MovieForm(Modal):
		title = 'Nominations'
		movie1 = TextInput(label="1:", required=True)
		movie2 = TextInput(label="2:", required=True)
		movie3 = TextInput(label="3:", required=True)
		movie4 = TextInput(label="4:", required=True)

		def __init__(self, callback: Callable[...,Coroutine]):
			super().__init__()
			self.callback = callback

		async def on_submit(self, interaction: Interaction):
			logger.info(f"Nominations submitted: {', '.join((str(self.movie1), str(self.movie2), str(self.movie3), str(self.movie4)))}")
			await self.callback(interaction, self.movie1.value, self.movie2.value, self.movie3.value, self.movie4.value)

	def make_command(self):
		return app_commands.Command(
			name='ballot',
			description='Nominate movies for club members to vote on',
			callback=self.create_ballot,
		)

	async def create_ballot(self, interaction: Interaction):
		logger.info(f'Recieved /ballot command. User: {interaction.user.id}; Channel: {interaction.channel_id}')
		if not interaction.channel_id or not self.client.resolve_domain(interaction.channel_id):
			logger.info(f'/ballot command is not in voting channel')
			await interaction.response.send_message("/ballot cannot be used in this channel.", ephemeral=True)
		else:
			await interaction.response.send_modal(self.MovieForm(self.send_poll))

	async def send_poll(self, interaction: Interaction, *urls: str):
		if not isinstance(interaction.channel, Messageable):
			await interaction.response.send_message("This is not a valid channel.", ephemeral=True)
			return

		async with asyncio.TaskGroup() as tg:
			tasks = [
				tg.create_task(MovieInfo.from_url(url))
				for url in urls
			]
		choices = list(zip(random.sample(list(EMOJIS), 4), [task.result() for task in tasks]))

		await interaction.response.send_message(
f"""
{interaction.user.display_name} presents, for your consideration, the following films:

{'\n'.join(f"{emoji} [{str(movie)}]({movie.url})" for i, (emoji, movie) in enumerate(choices))}
"""
		)

		poll = Poll("Which movie do you want to watch for the next session?", duration=datetime.timedelta(hours=24))
		for emoji, movie in choices:
			poll.add_answer(text=movie.title, emoji=emoji)
		await interaction.channel.send(content="".join(f"[.]({movie.url})" for _, movie in choices), poll=poll, suppress_embeds=True)
		logger.info('Sent poll')

class BookSession(Command):

	def make_command(self):
		return app_commands.ContextMenu(
			name="End Voting",
			callback=self.close_poll,
			type=AppCommandType.message,
		)

	async def close_poll(self, interaction: Interaction, message: Message):

		logger.info(f"Recieved 'End Voting' context menu command. Message: {message.id}; Channel: {message.channel.id}")
		domain = self.client.resolve_domain(message.channel.id)
		if not domain:
			asyncio.create_task(interaction.response.send_message("This is not a valid channel for this interaction.", ephemeral=True))
			return
		message = await domain.vote_channel.fetch_message(message.id)		# Unfortunately, the message that Discord sends does not include the poll results.
		try:
			url, title = self.get_winner(ballot_text=message.content, poll=message.poll)
		except VotingError as exc:
			asyncio.create_task(interaction.response.send_message(exc.response, ephemeral=True))
			logger.warning("Couldn't determine the URL of the vote winner", exc_info=True)
			return
		except Exception:
			logger.exception("Unexpected exception caught while finalizing the vote.", exc_info=True)
			asyncio.create_task(interaction.response.send_message("An error occurred while finalizing the vote. You'll have to do it manually.", ephemeral=True))
			raise
		asyncio.create_task(interaction.response.send_message(
			f"And the winner is... ~~La La Land~~ {title}! I'll proceed to make the club event now.", ephemeral=True
		))
		if not message.poll.is_finalized():				# type: ignore # get_winner() has already verified that `poll` is defined.
			asyncio.create_task(message.poll.end())		# type: ignore # get_winner() has already verified that `poll` is defined.
		await domain.schedule_event(await MovieInfo.from_url(url, fetch_image=True))

	def get_winner(self, ballot_text: str, poll: Poll|None) -> tuple[str, str]:
		"""
		Determines the Letterboxd URL of the poll winner.

		:param ballot_text: The text sent with the "ballot". This is expected to contain
			markdown-embedded URLs for each candidate movie.
		:param poll: The poll itself. It will be closed if all conditions are met to conclude
			voting
		:returns: A tuple of the URL and the title of the winning movie.
		:raises: `VotingError` if the URL of the winner cannot be detected. This includes the
			condition where the URLs cannot be read, or if there are multiple winners.
		"""

		urls = scanner.extract_urls_from_ballot(ballot_text)
		if not urls:
			raise VotingError("The target message did not have markdown-embedded URLs", "This is not a valid ballot.")
		if not poll:
			raise VotingError("The target message did not contain a poll.", "This message does not contain a poll.")
		if len(urls) != len(poll.answers):
			raise VotingError("The number of markdown-embedded URLs does not match the number of poll answers", "This is not a valid ballot.")
		highest_vote_count = max([answer.vote_count for answer in poll.answers])
		winners = [
			entry for entry in zip(urls, poll.answers)
			if entry[1].vote_count == highest_vote_count
		]
		if len(winners) > 1:
			raise VotingError("The target poll had multiple winners", "There is a tie. Please break the tie and try again.")
		return winners[0][0], winners[0][1].text
