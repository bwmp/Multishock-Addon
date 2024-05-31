import asyncio
import json
import threading
import websockets

from twitch_chat_client import TwitchChatClient
from twitch_client import TwitchClient

class MultiShockClient:
    def __init__(self):
        self.twitchClient: TwitchClient = None
        self.twitchChatClient: TwitchChatClient = None
        self.websocket = None
        self.stop_event = threading.Event()
        self.loop = asyncio.get_event_loop()

    async def on_message(self, message: str):
        print(f"Received message: {message}")
        try:
            data = json.loads(message)
        except json.decoder.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return
        cmd = data.get("cmd")
        args = data.get("value")
        print(f"Received command: {cmd} with args: {args}")
        if cmd == "update_credentials":
            username = args.get("username")
            token = args.get("oauth_token")
            await self.update_tokens_and_channels(token, username)
        elif cmd == "send_message":
            message = args.get("message")
            print(f"Sending message: {message}")
            await self.twitchChatClient.send_message(message)

    async def on_disconnect(self):
        print("Disconnected from WebSocket")

    def update_tokens_and_channels_threadsafe(self, new_token, new_channel):
        future = asyncio.run_coroutine_threadsafe(self.update_tokens_and_channels(new_token, new_channel), self.loop)
        future.result()  # Wait for the coroutine to complete

    async def update_tokens_and_channels(self, new_token, new_channel):
        if self.twitchClient is not None:
            if self.twitchClient.websocket is not None:
                await self.twitchClient.websocket.close()
                print("Closed TwitchClient WebSocket")
        
        if self.twitchChatClient is not None:
            if self.twitchChatClient.writer is not None:
                self.twitchChatClient.writer.close()
                await self.twitchChatClient.writer.wait_closed()
                print("Closed TwitchChatClient Writer")
        
        self.twitchClient = TwitchClient(new_token, new_channel, debug=True)
        self.twitchChatClient = TwitchChatClient(new_token, new_channel)
        self.twitchClient.multishockClient = self
        self.twitchChatClient.multishockClient = self
        
        twitch_client_thread = threading.Thread(target=self.run_twitch_client)
        twitch_chat_client_thread = threading.Thread(target=self.run_twitch_chat_client)

        twitch_client_thread.start()
        twitch_chat_client_thread.start()

    def run_twitch_client(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.twitchClient.connect_to_wss())
        loop.run_forever()

    def run_twitch_chat_client(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.twitchChatClient.connect_to_chat())
        loop.run_forever()

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