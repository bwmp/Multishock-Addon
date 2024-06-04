import asyncio
import json
import threading
import aiohttp

class TwitchChatClient:
    server = "irc.chat.twitch.tv"
    port = 6667

    def __init__(self, oauth_token, channel_username, event_loop):
        self.client_id = "2usq7xnhsujju3ezja2nzb5j7vtd84"
        self.oauth_token = oauth_token
        self.channel_username = channel_username
        self.channel = f"#{channel_username}"
        self.writer = None
        self.running = False
        self.loop = event_loop
        self.multishockClient = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run_loop)
        self.thread.start()

    def run_loop(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        asyncio.get_event_loop().run_until_complete(self.connect_to_chat())

    async def stop(self):
        self.running = False
        await self.close()

    def update_credentials(self, oauth_token, channel_username):
        self.oauth_token = oauth_token
        self.channel_username = channel_username
        self.channel = f"#{channel_username}"
        if self.running:
            self.loop.create_task(self.reconnect_to_chat())

    async def connect_to_chat(self):
        reader, writer = await asyncio.open_connection(self.server, self.port)
        self.writer = writer
        await self.send_pass_and_nick()
        await self.join_channel()
        await self.listen_to_chat(reader)

    async def reconnect_to_chat(self):
        await self.close()
        await self.connect_to_chat()

    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    async def send_pass_and_nick(self):
        self.writer.write(f"PASS oauth:{self.oauth_token}\n".encode("utf-8"))
        self.writer.write(f"NICK {self.channel_username}\n".encode("utf-8"))
        await self.writer.drain()

    async def join_channel(self):
        self.writer.write(f"JOIN {self.channel}\n".encode("utf-8"))
        await self.writer.drain()
        print(f"Joined channel {self.channel}")

    async def send_message(self, message):
        self.writer.write(f"PRIVMSG {self.channel} :{message}\n".encode("utf-8"))
        await self.writer.drain()
        print(f"Sent message: {message}")

    async def listen_to_chat(self, reader: asyncio.StreamReader):
        while self.running:
            response = await reader.read(2048)
            response = response.decode("utf-8")

            if "PING" in response and "PRIVMSG" not in response:
                self.writer.write("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
                await self.writer.drain()
            elif response != "":
                parts = response.split(":", 2)
                if len(parts) < 3:
                    continue
                payload = self.construct_payload(
                    "chat_message",
                    {
                        "username": parts[1].split("!", 2)[0].strip(),
                        "message": parts[2].strip(),
                    },
                )
                await self.multishockClient.send_message(payload)

    def construct_payload(self, command, value):
        return json.dumps({"cmd": command, "value": value})

    async def is_token_valid(self):
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"Bearer {self.oauth_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    response_json = await resp.json()
                    if (
                        "scopes" in response_json
                        and "chat:read" in response_json["scopes"]
                        and "chat:edit" in response_json["scopes"]
                    ):
                        return True
                    else:
                        print("Missing required scopes: 'chat:read' and 'chat:edit'")
                        return False
                else:
                    print(f"Token validation failed: {resp.status}")
                    return False
