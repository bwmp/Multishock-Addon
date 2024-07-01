import asyncio
import json


class TwitchChatClient:
    server = "irc.chat.twitch.tv"
    port = 6667

    def __init__(self, oauth_token, channel_username, client_id):
        self.client_id = client_id
        self.oauth_token = oauth_token
        self.channel_username = channel_username
        self.channel = f"#{channel_username}"
        self.writer = None
        self.running = False
        self.multishockClient = None

    async def stop(self):
        self.running = False
        await self.close()

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

    async def send_message(self, message):
        message = message.replace("\n", " ")
        try:
            self.writer.write(f"PRIVMSG {self.channel} :{message}\n".encode("utf-8"))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            await self.report_error(f"Twitch chat connection lost: {e}. Reconnecting...")
            await self.reconnect_to_chat()
            try:
                self.writer.write(
                    f"PRIVMSG {self.channel} :{message}\n".encode("utf-8")
                )
                await self.writer.drain()
            except Exception as e:
                await self.report_error(f"Failed to send message after reconnect: {e}")
        except Exception as e:
            await self.report_error(f"Unexpected error when sending message: {e}")

    async def listen_to_chat(self, reader: asyncio.StreamReader):
        while self.running:
            try:
                response = await reader.read(2048)
                response = response.decode("utf-8")

                if response == "":
                    payload = self.construct_payload(
                        "error",
                        {
                            "message": "Connection closed by server",
                        },
                    )
                    await self.multishockClient.send_message(payload)
                    break

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
            except asyncio.IncompleteReadError:
                await self.report_error("Connection closed by server. Reconnecting...")
                break
            except ConnectionResetError:
                await self.report_error(
                    "Connection closed by server. Reconnecting..."
                )
                break
            except Exception as e:
                await self.report_error(f"Unexpected error in listen_to_chat: {e} \n reconnecting...")
                break

        # Instead of calling reconnect_to_chat here, break the loop and reconnect from outside
        self.running = False

    async def report_error(self, error_message):
        payload = self.construct_payload(
            "error",
            {
                "message": error_message,
            },
        )
        await self.multishockClient.send_message(payload)

    def construct_payload(self, command, value):
        return json.dumps({"cmd": command, "value": value})

    async def start(self):
        self.running = True
        while self.running:
            await self.connect_to_chat()
            await asyncio.sleep(1)