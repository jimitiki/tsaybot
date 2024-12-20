from typing import Generator

from discord import PartialEmoji
import emoji
import regex

EMOJI_PATTERN = regex.compile(r'<a?:[^:]+:\d*>|\X')
URL_PATTERN = regex.compile(r'^https://(boxd\.it|letterboxd\.com)[^\s]*$')

def find_emoji(s: str) -> Generator[PartialEmoji,None,None]:
	"""
	Yields all unicode and custom Discord emojis in the string.

	Emojis are yielded in the same order which they occur.
	"""

	for grapheme in EMOJI_PATTERN.findall(s):
		if (
			grapheme.startswith('<') and grapheme.endswith('>')		# Custom emoji in the form of "<a:name:id>" where "a" is present if animated and absent if not.
			or emoji.is_emoji(grapheme)								# Standard unicode emoji
			or ord(grapheme) in range(0x0001F1E6, 0x0001F200)		# Regional indicators (🇦-🇿)
		):
			yield PartialEmoji.from_str(grapheme)

def is_url(s: str) -> bool:
	"""
	Detects if the provided string is a URL or not.
	"""

	return bool(URL_PATTERN.match(s))

if __name__ == '__main__':

	print(list(find_emoji("<:shyguy:1319335606878470164> 😀 🇨🇨 🇺🇾 ⚡ 🇦 🇺 🇿 😈 👩‍⚖️ ✍️ 🧎🏻‍➡️ 🧑🏼‍🎓 🙆🏾‍♀️ 🧑🏿‍🎨")))
