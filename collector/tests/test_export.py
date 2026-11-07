import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import export_public as E


class T(unittest.TestCase):
    def test_filter(self):
        base = {"id": "a", "kind": "earnings", "code": "1", "url": "u"}
        self.assertFalse(E.publishable(dict(base)))                       # 未確認
        self.assertTrue(E.publishable(dict(base, confirmed=True)))
        self.assertFalse(E.publishable(dict(base, confirmed=True, needs_review=True)))
        self.assertFalse(E.publishable(dict(base, kind="alliance", confirmed=True)))
        self.assertTrue(E.publishable(dict(base, extractor="xbrl")))

    def test_no_text_or_unknown_fields(self):
        x = {"id": "a", "kind": "buyback", "code": "1", "url": "u", "quote": "本文", "summary": "要約",
             "note": "n", "memo": "m", "token": "t", "secret_new_field": 1, "confirmed": True,
             "target": {"start": "2026-01-01", "end": None, "precision": "day", "raw": "原文"}}
        o = E.convert(x)
        self.assertFalse(set(o) & E.FORBIDDEN)
        self.assertNotIn("secret_new_field", o)
        self.assertEqual(set(o["target"]), {"start", "end", "precision"})


if __name__ == "__main__":
    unittest.main()
