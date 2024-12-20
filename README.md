# Bot Token

In order to connect the bot to Discord, the bot's token must be stored in `token.txt` at the top level of the project directory.

# Configuration

The bot must be instantiated with a Server ID (the server where events will be created) and three Channel IDs: one for the channel where voting takes place, one for the channel where announcements are made, and one for the voice channel where events will be scheduled. These IDs are specified in the `config.json` file, which is structured as follows:


```
{
	"default": {
		"server": <Server ID>,
		"vote_channel": <voting Channel ID>,
		"announce_channel": <announcement Channel ID>,
		"voice_channel": <voice Channel ID>
	}
}
```

In the future, multiple environments will be supported, but at present, "default" is always used.
