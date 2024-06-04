import asyncio
import json
import threading
import websockets
import websockets.server
import sys


class WebSocketServer:
    def __init__(self, username, oauth_token, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self.clients: dict = {}
        self.special_clients = {}
        self.loop = None
        self.username = username
        self.oauth_token = oauth_token

    async def new_client(self, websocket, path):
        client_id = id(websocket)
        self.clients[client_id] = websocket
        await self.broadcast("Hey all, a new client has joined us")
        print("New client joined")

    async def client_left(self, websocket):
        client_id = id(websocket)
        del self.clients[client_id]
        if client_id in self.special_clients:
            self.special_clients.pop(client_id)
        print(f"Client Disconnected")

    async def message_command(self, websocket, message):
        client_id = id(websocket)
        print(f"Received message: {message}")
        try:
            command = json.loads(message)
        except json.decoder.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

        command_name = command.get("cmd")
        command_args = command.get("value")

        if command_name == "identify":
            self.special_clients[client_id] = command_args
            print(f"Added {client_id} to special clients with app_id {command_args}")

            await self.send_to_client(client_id, "You are now a special client!")
            if command_args == "Twitch":
                payload = self.construct_payload(
                    "update_credentials",
                    {
                        "username": self.username,
                        "oauth_token": self.oauth_token,
                    },
                )
                await self.send_to_client(client_id, payload)
            return

        if command_name == "channel.cheer":
            print(f"Cheer received from {client_id}: {command_args}")
        if not command_name or not command_args:
            print("Invalid command format")
            return

    def update_twitch_creds(self, username, oauth_token):
        print("Updating Twitch credentials")
        payload = self.construct_payload(
            "update_credentials", {"username": username, "oauth_token": oauth_token}
        )
        asyncio.run(self.send_to_special_client("Twitch", payload))

    def send_chat_message(self, message):
        asyncio.run(self.send_chat_message_async(message))

    async def send_chat_message_async(self, message):
        payload = self.construct_payload("send_message", {"message": message})
        await self.send_to_special_client("Twitch", payload)

    def construct_payload(self, command, value):
        return json.dumps({"cmd": command, "value": value})

    async def handler(self, websocket, path):
        await self.new_client(websocket, path)
        try:
            async for message in websocket:
                await self.message_command(websocket, message)
        except websockets.ConnectionClosed:
            await self.client_left(websocket)

    async def broadcast(self, message):
        if self.clients:
            await asyncio.wait(
                [client.send(message) for client in self.clients.values()]
            )

    async def send_to_client(self, client_id, message):
        if client_id in self.clients:
            print(f"Sending message to client {client_id}.")
            try:
                await self.clients[client_id].send(message)
            except websockets.ConnectionClosedOK:
                print(f"Client {client_id} disconnected.")
            except Exception as e:
                print(f"Error sending message to client {client_id}: {e}")
            print(f"Message sent to client {client_id}.")
        else:
            print(f"Client {client_id} not found in clients.")

    async def send_to_special_client(self, client_name, message):
        client_id = next(
            (id for id, name in self.special_clients.items() if name == client_name),
            None,
        )
        if client_id in self.special_clients:
            await self.send_to_client(client_id, message)
        else:
            print(f"Client {client_name} not found in special clients.")

    def start_server(self):
        print("Starting WebSocket server...")

        def run_event_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.server = websockets.serve(self.handler, self.host, self.port)
            self.loop.run_until_complete(self.server)
            print(f"WebSocket server started on {self.host}:{self.port}.")
            self.loop.run_forever()

        self.thread = threading.Thread(target=run_event_loop, daemon=True)
        self.thread.start()

    def stop_server(self):
        if self.server and self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
            if self.thread.is_alive():
                self.thread.join()
                print("WebSocket server stopped.")
            else:
                print("WebSocket server thread is not running.")

    def send_message(self, message):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)


if __name__ == "__main__":
    # your twitch username
    username = "buwump"
    # oauth token can be obtained from https://twitchapps.com/tmi/
    oauth_token = "token here"
    server = WebSocketServer(username, oauth_token)
    server.start_server()

    def listen_for_console():
        print("Listening for console input...")
        while True:
            command = sys.stdin.readline().strip()
            if command.lower() == "update_twitch_creds":
                print("Console command received: update_twitch_creds")
                server.update_twitch_creds(username, oauth_token)
            else:
                server.send_message(json.dumps({"cmd": "Test", "value": "Meow"}))

    console_thread = threading.Thread(target=listen_for_console, daemon=True)
    console_thread.start()

    try:
        while True:
            pass  # Keep the main thread alive to allow other threads to run
    except KeyboardInterrupt:
        server.stop_server()
        print("Server stopped.")
