import asyncio
import json
import threading
import websockets

from twitch_chat_client import TwitchChatClient
from twitch_client import TwitchClient


class MultiShockClient:
    def __init__(self, twitchClient, twitchChatClient):
        self.twitchClient: TwitchClient = twitchClient
        self.twitchChatClient: TwitchChatClient = twitchChatClient
        self.websocket = None
        self.stop_event = threading.Event()

    async def on_message(self, message: str):
        print(f"MultiShockClient received: {message}")
        try:
            data = json.loads(message)
        except json.decoder.JSONDecodeError as e:
            return
        cmd = data.get("cmd")
        args = data.get("value")
        if cmd == "update_credentials":
            username = args.get("username")
            token = args.get("oauth_token")
            print(f"Updating token and channel for {username}")
            await self.update_tokens_and_channels(self.twitchClient, self.twitchChatClient, token, username)
        elif cmd == "send_message":
            message = args.get("message")
            await self.twitchChatClient.send_message(message)
    async def on_disconnect(self):
        print("disconnected from websocket")

    async def update_tokens_and_channels(self, client1, client2, new_token, new_channel):
        task1 = asyncio.create_task(client1.update_token_and_channel(new_token, new_channel))
        task2 = asyncio.create_task(client2.update_token_and_channel(new_token, new_channel))
        await asyncio.gather(task1, task2)

    def construct_payload(self, command, value):
        return json.dumps({"cmd": command, "value": value})

    async def connect_to_wss(self):
        uri = "ws://localhost:8765"
        try:
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                await self.send_message(self.construct_payload("identify", "Twitch"))
                while not self.stop_event.is_set():
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                        await self.on_message(message)
                    except asyncio.TimeoutError:
                        continue
        except websockets.ConnectionClosed:
            await self.on_disconnect()

    async def send_message(self, message: str):
        await self.websocket.send(message)

    def start(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.connect_to_wss())

    def run(self):
        self.thread = threading.Thread(target=self.start, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()