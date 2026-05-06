import unittest
from unittest.mock import patch

import niche_agent


class RetryableTrendFetchTests(unittest.TestCase):
    def test_retries_on_429_then_succeeds(self) -> None:
        class FakeTrendReq:
            attempts = 0

            def __init__(self, *args, **kwargs):
                pass

            def build_payload(self, *args, **kwargs):
                FakeTrendReq.attempts += 1
                if FakeTrendReq.attempts == 1:
                    raise Exception("Google returned a response with code 429")

            def interest_over_time(self):
                return {"ok": True}

        with patch.object(niche_agent, "TrendReq", FakeTrendReq):
            with patch.object(niche_agent.time, "sleep"):
                data, attempts = niche_agent._fetch_interest_over_time(
                    "cursor ide", "today 12-m"
                )

        self.assertEqual(data, {"ok": True})
        self.assertEqual(attempts, 2)

    def test_extract_http_status_code_from_exception_message(self) -> None:
        code = niche_agent._extract_http_status_code(
            Exception("Google returned a response with code 403")
        )
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
