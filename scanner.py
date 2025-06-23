import regex

URL_PATTERN = regex.compile(r'^https://(boxd\.it|letterboxd\.com)[^\s]*$')

def is_url(s: str) -> bool:
	"""
	Detects if the provided string is a URL or not.
	"""

	return bool(URL_PATTERN.match(s))
