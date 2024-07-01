import argparse
import asyncio
import time

import aiohttp
from multishock_client import MultiShockClient
from twitch_client import TwitchClient
from twitch_chat_client import TwitchChatClient
import sys

def parse_args():
    parser = argparse.ArgumentParser(
        description="Start the Twitch and MultiShock clients."
    )
    parser.add_argument(
        "--oauth_token",
        type=str,
        required=True,
        help="The OAuth token for the Twitch client.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="The port to use for the WebSocket server.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode.")

    return parser.parse_args()


async def main(oauth_token, port, debug):
    client_id = "2usq7xnhsujju3ezja2nzb5j7vtd84"
    async def is_token_valid():
        url = f"https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"Bearer {oauth_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    response_json = await resp.json()
                    if "expires_in" in response_json:
                        expiration_timestamp = time.time() + response_json["expires_in"]
                        return True, expiration_timestamp
                    else:
                        return False, None
                else:
                    return False, None

    async def get_channel_id():
        token_valid, expiration_timestamp = await is_token_valid()
        if not token_valid:
            return None
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {oauth_token}",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.twitch.tv/helix/users", headers=headers
            ) as resp:
                data = await resp.json()
                channel_id = data["data"][0]["id"]
                username = data["data"][0]["login"]
                return channel_id, username
    
    channel_id, username = await get_channel_id()
    
    multishockClient = MultiShockClient(port)

    twitchClient = TwitchClient(oauth_token, username, client_id, channel_id, debug)
    twitchClient.multishockClient = multishockClient

    twitchChatClient = TwitchChatClient(oauth_token, username, client_id)
    twitchChatClient.multishockClient = multishockClient

    multishockClient.twitchClient = twitchClient
    multishockClient.twitchChatClient = twitchChatClient
    await asyncio.gather(
        twitchClient.connect_to_wss(),
        twitchChatClient.connect_to_chat(),
        multishockClient.connect_to_wss(),
    )


if __name__ == "__main__":
    print(sys.argv)
    args = parse_args()
    asyncio.run(main(args.oauth_token, args.port, args.debug))
