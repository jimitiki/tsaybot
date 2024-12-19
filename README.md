# Bot Token

In order to connect the bot to Discord, the bot's token must be stored in `token.txt` at the top level of the project directory.

# Configuration

The bot must be instantiated with a Server ID (the server where events will be created) and two Channel IDs: one for the channel where voting takes place, and the other for the channel where announcements are made. These IDs are specified in the `config.json` file, which is structured as follows:


```
{
	"default": {
		"server_id": <Server ID>,
		"vote_channel_id": <voting Channel ID>,
		"announce_channel_id": <announcement Channel ID>,
	}
}
```

In the future, multiple environments will be supported, but at present, "default" is always used.
