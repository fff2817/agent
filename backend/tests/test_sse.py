"""SSE 桥接层单元测试。"""

import asyncio
import unittest

from core.sse import bridge_sync_iterator_to_sse, format_sse_event


class TestSSE(unittest.TestCase):
    def test_format_sse_event(self):
        line = format_sse_event({"type": "token", "content": "hi"})
        self.assertTrue(line.startswith("data: "))
        self.assertTrue(line.endswith("\n\n"))
        self.assertIn('"type": "token"', line)

    def test_bridge_sync_iterator_to_sse(self):
        def producer():
            yield {"type": "token", "content": "a"}
            yield {"type": "done", "response": "a"}

        async def collect():
            gen = bridge_sync_iterator_to_sse(producer)
            return [chunk async for chunk in gen]

        chunks = asyncio.run(collect())
        self.assertEqual(len(chunks), 2)
        self.assertIn('"content": "a"', chunks[0])
        self.assertIn('"type": "done"', chunks[1])


if __name__ == "__main__":
    unittest.main()
