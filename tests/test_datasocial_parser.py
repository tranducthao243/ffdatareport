import unittest

from datasocial.display import render_posts
from datasocial.parser import parse_list_post_response


class DatasocialParserTests(unittest.TestCase):
    def test_parse_list_post_response_normalizes_posts(self):
        payload = {
            "data": {
                "listPost": {
                    "total": 1,
                    "results": [
                        {
                            "id": "post-1",
                            "name": "Sample post",
                            "alias": "sample-alias",
                            "url": "https://example.com/post-1",
                            "createdAt": "2026-04-12T09:00:00Z",
                            "metrics": {"view": 1200, "like": 12},
                        }
                    ],
                }
            }
        }
        page = parse_list_post_response(payload)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.results[0].title, "Sample post")
        self.assertEqual(page.results[0].metrics, {"view": 1200, "like": 12})

    def test_render_posts_outputs_required_fields(self):
        payload = {
            "data": {
                "listPost": {
                    "total": 1,
                    "results": [
                        {
                            "id": "post-2",
                            "name": "Another post",
                            "url": "https://example.com/post-2",
                            "createdAt": "2026-04-12T10:00:00Z",
                            "metrics": {"view": 200, "share": 3},
                        }
                    ],
                }
            }
        }
        page = parse_list_post_response(payload)
        output = render_posts(page)
        self.assertIn("Another post", output)
        self.assertIn("https://example.com/post-2", output)
        self.assertIn("2026-04-12T10:00:00Z", output)
        self.assertIn('"view": 200', output)


if __name__ == "__main__":
    unittest.main()
