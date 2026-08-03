"""Sign in to Telegram once, writing the session file the worker needs.

Interactive by necessity: Telegram asks for your phone number, a code it texts
you, and your 2FA password if you have one. That is why this cannot be part of
the background worker's startup.
"""

import asyncio

from app.config import get_settings
from app.ingest.telegram import build_client

settings = get_settings()


async def main() -> None:
    client = build_client()
    await client.start()

    me = await client.get_me()
    name = " ".join(filter(None, [me.first_name, me.last_name]))
    print(f"\nSigned in as {name} (@{me.username or 'no username'})")

    try:
        entity = await client.get_entity(settings.telegram_chat)
        print(f"Can read: {entity.title}")
    except Exception as exc:
        print(f"Could not open {settings.telegram_chat!r}: {exc}")
        print("Join the group with this account first.")

    print(f"\nSession saved to {settings.telegram_session_path}")
    print("Keep that file private — it is a credential.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
