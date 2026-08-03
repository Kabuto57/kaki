"""Print the group's forum topics so you can pick the games one.

Put the id into TELEGRAM_TOPIC_ID. Without it the worker reads the entire group
and most of what it stores is conversation rather than game offers.
"""

import asyncio

from telethon.tl.functions.channels import GetForumTopicsRequest

from app.config import get_settings
from app.ingest.telegram import build_client

settings = get_settings()


async def main() -> None:
    client = build_client()
    await client.start()
    entity = await client.get_entity(settings.telegram_chat)

    try:
        result = await client(
            GetForumTopicsRequest(
                channel=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100
            )
        )
    except Exception as exc:
        print(f"No topics ({type(exc).__name__}). This group is not a forum — leave TELEGRAM_TOPIC_ID blank.")
        await client.disconnect()
        return

    print(f"\nTopics in {entity.title}:\n")
    print(f"{'ID':>10}   TITLE")
    print("-" * 50)
    for topic in result.topics:
        print(f"{topic.id:>10}   {getattr(topic, 'title', '(unnamed)')}")
    print("\nPut the games topic id into TELEGRAM_TOPIC_ID in .env")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
