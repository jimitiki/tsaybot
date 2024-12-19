from typing import Generator

from discord import PartialEmoji
import regex
import emoji

PATTERN = regex.compile(r'<a?:[^:]+:\d*>|\X')

def find_emoji(s: str) -> Generator[PartialEmoji,None,None]:
	"""
	Yields all unicode and custom Discord emojis in the string.

	Emojis are yielded in the same order which they occur.
	"""

	for grapheme in PATTERN.findall(s):
		if (
			grapheme.startswith('<') and grapheme.endswith('>')		# Custom emoji in the form of "<a:name:id>" where "a" is present if animated and absent if not.
			or emoji.is_emoji(grapheme)								# Standard unicode emoji
			or ord(grapheme) in range(0x0001F1E6, 0x0001F200)		# Regional indicators (🇦-🇿)
		):
			yield PartialEmoji.from_str(grapheme)

if __name__ == '__main__':

	print(list(find_emoji("<:shyguy:1319335606878470164> 😀 🇨🇨 🇺🇾 ⚡ 🇦 🇺 🇿 😈 👩‍⚖️ ✍️ 🧎🏻‍➡️ 🧑🏼‍🎓 🙆🏾‍♀️ 🧑🏿‍🎨")))
