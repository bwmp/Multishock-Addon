import asyncio
from multishock_client import MultiShockClient
from twitch_client import TwitchClient
from twitch_chat_client import TwitchChatClient

async def connect_to_servers(multishockClient: MultiShockClient, twitchClient: TwitchClient, twitchChatClient: TwitchChatClient):
    await asyncio.gather(
        multishockClient.connect_to_wss(), 
        twitchClient.connect_to_wss(), 
        twitchChatClient.connect_to_chat()
    )

if __name__ == "__main__":
    oauth_token = ""
    channel_username = ""
    
    twitchClient = TwitchClient(oauth_token, channel_username, debug=False)
    twitchChatClient = TwitchChatClient(oauth_token, channel_username)
    
    multishockClient = MultiShockClient(twitchClient, twitchChatClient)
    twitchClient.multishockClient = multishockClient
    twitchChatClient.multishockClient = multishockClient
    
    asyncio.run(connect_to_servers(multishockClient, twitchClient, twitchChatClient))
