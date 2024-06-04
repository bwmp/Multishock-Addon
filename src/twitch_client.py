import asyncio
import json
import threading
import time
import aiohttp
import websockets

class TwitchClient:
    subscription_url = "https://api.twitch.tv/helix/eventsub/subscriptions"
    websocket_url = "wss://eventsub.wss.twitch.tv/ws"
    debug_subscription_url = "http://localhost:8080/eventsub/subscriptions"
    debug_websocket_url = "ws://localhost:8080/ws"

    def __init__(self, oauth_token, channel_username, event_loop, debug=False):
        self.client_id = "2usq7xnhsujju3ezja2nzb5j7vtd84"
        self.oauth_token = oauth_token
        self.channel_username = channel_username
        self.channel_id = None
        self.session_id = None
        self.debug = debug
        self.reconnection = False
        self.websocket_url = (
            self.debug and self.debug_websocket_url or self.websocket_url
        )
        self.expires_at = None
        self.multishockClient = None
        self.running = False
        self.websocket = None
        self.event_loop: asyncio.AbstractEventLoop = event_loop

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run_loop)
        self.thread.start()

    def run_loop(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        asyncio.get_event_loop().run_until_complete(self.connect_to_wss())

    async def stop(self):
        self.running = False
        await self.close()

    async def update_credentials(self, oauth_token, channel_username):
        self.oauth_token = oauth_token
        self.channel_username = channel_username
        if self.running:
            await self.reconnect_to_wss()

    async def connect_to_wss(self):
        uri = self.websocket_url
        self.channel_id = await self.get_channel_id()
        valid_token, expiration_timestamp = await self.is_token_valid()
        if not valid_token:
            return
        try:
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                print("connected to websocket")
                await self.listen_to_websocket()
        except websockets.ConnectionClosed:
            await self.on_disconnect()

    async def close(self):
        if self.websocket:
            await self.event_loop.run_in_executor(None, self.websocket.close)

    async def reconnect_to_wss(self):
        await self.close()
        await self.connect_to_wss()
        print("reconnected to websocket")

    async def listen_to_websocket(self):
        while self.running:
            message = await self.websocket.recv()
            await self.on_message(message)

    async def on_message(self, message: str):
        parsed_message = json.loads(message)
        message_type = parsed_message.get("metadata", {}).get("message_type")
        payload = parsed_message.get("payload", {})
        if message_type == "session_keepalive":
            return
        if message_type == "session_welcome":
            self.session_id = payload.get("session", {}).get("id")
            await self.subscribe_to_eventsub(
                "channel.channel_points_custom_reward_redemption.add"
            )
            await self.subscribe_to_eventsub("channel.cheer")
            await self.subscribe_to_eventsub("channel.subscribe")
            await self.subscribe_to_eventsub("channel.subscription.gift")
        elif message_type == "session_reconnect":
            print("reconnecting...")
            self.websocket_url = payload.get("session", {}).get("reconnect_url")
            self.reconnection = True
            await self.reconnect_to_wss()
        elif message_type == "notification":
            multishock_payload = {
                "cmd": payload.get("subscription").get("type"),
                "value": payload.get("event"),
            }
            await self.multishockClient.send_message(json.dumps(multishock_payload))

    async def close_websocket(self):
        if self.websocket:
            await self.websocket.close()

    async def on_disconnect(self):
        print("Disconnected from Twitch WebSocket")
        await self.close_websocket()

    async def subscribe_to_eventsub(self, event_type):
        if self.reconnection:
            return
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.oauth_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "type": event_type,
            "version": "1",
            "condition": {
                "broadcaster_user_id": self.channel_id,
            },
            "transport": {
                "method": "websocket",
                "session_id": self.session_id,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.debug and self.debug_subscription_url or self.subscription_url,
                headers=headers,
                json=payload,
            ) as resp:
                print("got response", resp.status)

    async def is_token_valid(self):
        url = f"https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"Bearer {self.oauth_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    response_json = await resp.json()
                    if "expires_in" in response_json:
                        expiration_timestamp = time.time() + response_json["expires_in"]
                        self.expires_at = expiration_timestamp
                        return True, expiration_timestamp
                    else:
                        return False, None
                else:
                    return False, None

    async def get_channel_id(self):
        token_valid, expiration_timestamp = await self.is_token_valid()
        if not token_valid:
            return None
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.oauth_token}",
        }
        params = {"login": self.channel_username}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.twitch.tv/helix/users", headers=headers, params=params
            ) as resp:
                data = await resp.json()
                self.channel_id = data["data"][0]["id"]
                return self.channel_id
