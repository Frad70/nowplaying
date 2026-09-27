"""Offline checks for profile cleanup; no Telegram session or D-Bus needed."""
from __future__ import annotations

import unittest

from telethon.tl.functions.account import UpdateEmojiStatusRequest, UpdateProfileRequest
from telethon.tl.types import EmojiStatusEmpty

from nowplaying import Publisher, Track


class FakeClient:
    def __init__(self, fail_first: bool = False) -> None:
        self.calls = []
        self.fail_first = fail_first

    async def __call__(self, request):
        self.calls.append(request)
        if self.fail_first:
            self.fail_first = False
            raise RuntimeError("simulated uncertain write")


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore_after_publication(self):
        client = FakeClient()
        publisher = Publisher(client, {"base_bio": "original", "emoji_status": True,
                                       "emoji_document_id": 123})
        await publisher._write(Track("Artist", "Title"))
        await publisher.restore()
        self.assertEqual([call.about for call in client.calls
                          if isinstance(call, UpdateProfileRequest)],
                         ["♪ Artist — Title | original", "original"])
        emoji_calls = [call for call in client.calls
                       if isinstance(call, UpdateEmojiStatusRequest)]
        self.assertEqual(len(emoji_calls), 2)
        self.assertIsInstance(emoji_calls[-1].emoji_status, EmojiStatusEmpty)

    async def test_uncertain_publication_still_attempts_restore(self):
        client = FakeClient(fail_first=True)
        publisher = Publisher(client, {"base_bio": "original", "emoji_status": False})
        await publisher._write(Track("Artist", "Title"))
        await publisher.restore()
        self.assertEqual([call.about for call in client.calls],
                         ["♪ Artist — Title | original", "original"])

    async def test_no_publication_needs_no_restore(self):
        client = FakeClient()
        await Publisher(client, {"base_bio": "original"}).restore()
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
