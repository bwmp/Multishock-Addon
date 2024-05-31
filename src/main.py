import asyncio
from multishock_client import MultiShockClient

if __name__ == "__main__":
    multishockClient = MultiShockClient()

    asyncio.run(multishockClient.connect_to_wss())
