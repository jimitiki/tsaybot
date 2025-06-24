import regex

URL_PATTERN = regex.compile(r'^https://(boxd\.it|letterboxd\.com)[^\s]*$')
BALLOT_URL_PATTERN = regex.compile(r'\[\.\]\((https://[^\)]*)\)')

def is_url(s: str) -> bool:
	"""
	Detects if the provided string is a URL or not.
	"""

	return bool(URL_PATTERN.match(s))

def extract_urls_from_ballot(ballot: str) -> list[str]:
	"""
	Finds all embeded URLs in the text.
	"""

	return BALLOT_URL_PATTERN.findall(ballot)
