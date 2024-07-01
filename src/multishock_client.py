import asyncio
import json
import websockets

from twitch_chat_client import TwitchChatClient
from twitch_client import TwitchClient

class MultiShockClient:
    def __init__(self, port=8765):
        self.twitchClient: TwitchClient = None
        self.twitchChatClient: TwitchChatClient = None
        self.websocket = None
        self.stop_event = asyncio.Event()
        self.port = port

    async def on_message(self, message: str):
        try:
            data = json.loads(message)
        except json.decoder.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return
        cmd = data.get("cmd")
        args = data.get("value")
        if cmd == "send_message":
            message = args.get("message")
            await self.twitchChatClient.send_message(message)

    async def on_disconnect(self):
        print("Disconnected from MultiShock WebSocket")

    async def connect_to_wss(self):
        uri = f"ws://localhost:{self.port}"
        try:
            print(f"Connecting to {uri}")
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                await self.send_message(self.construct_payload("identify", "Twitch"))
                while not self.stop_event.is_set():
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                        await self.on_message(message)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.ConnectionClosed as e:
                        print(f"Connection closed: {e}")
                        await self.on_disconnect()
                        break
                    except Exception as e:
                        print(f"Unexpected error in message handling: {e}")
                        await self.on_disconnect()
                        break
        except ConnectionRefusedError:
            print("Cannot connect to Multishock WebSocket")
        except websockets.ConnectionClosed as e:
            print(f"WebSocket connection closed: {e}")
            await self.on_disconnect()
        except Exception as e:
            print(f"Unexpected error in connect_to_wss: {e}")

    async def send_message(self, message: str):
        try:
            await self.websocket.send(message)
        except websockets.ConnectionClosed as e:
            print(f"Failed to send message, connection closed: {e}")
        except Exception as e:
            print(f"Unexpected error when sending message: {e}")

    def construct_payload(self, command, value):
        return json.dumps({"cmd": command, "value": value})