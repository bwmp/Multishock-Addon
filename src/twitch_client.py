import json
import aiohttp
import websockets

class TwitchClient:
    subscription_url = "https://api.twitch.tv/helix/eventsub/subscriptions"
    websocket_url = "wss://eventsub.wss.twitch.tv/ws"
    debug_subscription_url = "http://localhost:8080/eventsub/subscriptions"
    debug_websocket_url = "ws://localhost:8080/ws"

    def __init__(
        self, oauth_token, channel_username, client_id, channel_id, debug=False
    ):
        self.client_id = client_id
        self.oauth_token = oauth_token
        self.channel_username = channel_username
        self.channel_id = channel_id
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
        self.running = True
        try:
            async with websockets.connect(uri) as websocket:
                self.websocket = websocket
                print("Connected to Twitch WebSocket")
                await self.listen_to_websocket()
        except websockets.ConnectionClosed as e:
            await self.on_disconnect()
            await self.report_error(f"WebSocket connection closed: {e}")
        except ConnectionRefusedError as e:
            await self.report_error(f"Cannot connect to Twitch WebSocket: {e}")

    async def close(self):
        if self.websocket:
            await self.websocket.close()

    async def reconnect_to_wss(self):
        await self.close()
        await self.connect_to_wss()
        print("Reconnected to Twitch WebSocket")

    async def listen_to_websocket(self):
        while self.running:
            try:
                message = await self.websocket.recv()
                await self.on_message(message)
            except websockets.ConnectionClosed as e:
                await self.on_disconnect()
                await self.report_error(f"WebSocket connection closed: {e}")
                break
            except Exception as e:
                await self.report_error(f"Unexpected error in listen_to_websocket: {e}")
                break

    async def on_message(self, message: str):
        try:
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
                await self.subscribe_to_eventsub("channel.follow")
                await self.subscribe_to_eventsub("channel.raid")
                await self.subscribe_to_eventsub("channel.hype_train.begin")
                await self.subscribe_to_eventsub("channel.hype_train.progress")
                await self.subscribe_to_eventsub("channel.hype_train.end")
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
        except Exception as e:
            await self.report_error(f"Error processing message: {e}")

    async def close_websocket(self):
        if self.websocket:
            await self.websocket.close()

    async def on_disconnect(self):
        print("Disconnected from Twitch WebSocket")
        await self.close_websocket()
        await self.report_error("Disconnected from Twitch WebSocket")

    async def subscribe_to_eventsub(self, event_type):
        if self.reconnection:
            return
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.oauth_token}",
            "Content-Type": "application/json",
        }

        event_conditions = {
            "channel.cheer": {"broadcaster_user_id": self.channel_id},
            "channel.subscribe": {"broadcaster_user_id": self.channel_id},
            "channel.subscription.gift": {"broadcaster_user_id": self.channel_id},
            "channel.follow": {"broadcaster_user_id": self.channel_id, "moderator_user_id": self.channel_id},
            "channel.hype_train.begin": {"broadcaster_user_id": self.channel_id},
            "channel.hype_train.progress": {"broadcaster_user_id": self.channel_id},
            "channel.hype_train.end": {"broadcaster_user_id": self.channel_id},
            "channel.raid": {"to_broadcaster_user_id": self.channel_id},
        }
        
        versions = {
            "channel.cheer": "1",
            "channel.subscribe": "1",
            "channel.subscription.gift": "1",
            "channel.follow": "2",
            "channel.raid": "1",
            "channel.hype_train.begin": "1",
            "channel.hype_train.progress": "1",
            "channel.hype_train.end": "1",
        }

        condition = event_conditions.get(
            event_type, {"broadcaster_user_id": self.channel_id}
        )
        
        version = versions.get(event_type, "1")

        payload = {
            "type": event_type,
            "version": version,
            "condition": condition,
            "transport": {
                "method": "websocket",
                "session_id": self.session_id,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.debug and self.debug_subscription_url or self.subscription_url,
                    headers=headers,
                    json=payload,
                ) as resp:
                    multishock_payload = {
                        "cmd": "notification",
                        "value": {
                            "type": event_type,
                            "response_status": resp.status,
                            "response_text": await resp.text(),
                        },
                    }
                    await self.multishockClient.send_message(json.dumps(multishock_payload))
        except Exception as e:
            await self.report_error(f"Error subscribing to event {event_type}: {e}")

    async def report_error(self, error_message: str):
        payload = self.construct_payload(
            "error",
            {
                "message": error_message,
            },
        )
        await self.multishockClient.send_message(payload)

    def construct_payload(self, command, value):
        return json.dumps({"cmd": command, "value": value})
