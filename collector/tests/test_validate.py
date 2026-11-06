import os, sys, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import validate_data as V


def mk(events, extra=None):
    d = tempfile.mkdtemp()
    json.dump({"events": events}, open(os.path.join(d, "events.json"), "w", encoding="utf-8"))
    json.dump([], open(os.path.join(d, "ir_index.json"), "w"))
    json.dump(extra or {"complete": True}, open(os.path.join(d, "status.json"), "w"))
    return d


def ev(i, kind="earnings", **kw):
    x = {"id": i, "kind": kind, "code": "1111", "url": "u"}
    x.update(kw)
    return x


class T(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(V.check(mk([ev("a"), ev("b")])), [])

    def test_duplicate_id(self):
        self.assertTrue(V.check(mk([ev("a"), ev("a")])))

    def test_undated_confirmed_alliance_rejected(self):
        self.assertTrue(V.check(mk([ev("a", "alliance", confirmed=True)])))

    def test_shrink(self):
        prev = mk([ev(str(i)) for i in range(100)])
        self.assertTrue(V.check(mk([ev(str(i)) for i in range(50)]), prev))

    def test_hold_alliance(self):
        d = mk([ev("a", "alliance"), ev("b", "alliance", confirmed=True, target={"start": "2026-01-01"}), ev("c")])
        self.assertEqual(V.hold(d), 1)
        kept = json.load(open(os.path.join(d, "events.json"), encoding="utf-8"))["events"]
        self.assertEqual([x["id"] for x in kept], ["b", "c"])
        self.assertEqual(len(json.load(open(os.path.join(d, "held.json"), encoding="utf-8"))["events"]), 1)


if __name__ == "__main__":
    unittest.main()
