import asyncio
from multishock_client import MultiShockClient

async def main():
    multishock_client = MultiShockClient()
    await multishock_client.connect_to_wss()

if __name__ == "__main__":
    asyncio.run(main())
