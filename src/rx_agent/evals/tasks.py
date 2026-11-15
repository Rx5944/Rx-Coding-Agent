"""Evaluation tasks. Each has hidden checks the agent never sees and a reference solution used to
prove the task is non-trivial (checks fail before) and solvable (checks pass after)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalTask:
    id: str
    prompt: str
    files: dict[str, str]
    checks: list[dict]
    solution: dict[str, str]
    hidden_files: dict[str, str] = field(default_factory=dict)
    verify: str = ""  # a command the oracle runs to "verify" (mirrors what a good agent does)


TASKS: list[EvalTask] = [
    EvalTask(
        id="fix_off_by_one",
        prompt="`window()` in stats.py should return the first n items but returns one too few. Fix the bug.",
        files={"stats.py": "def window(items, n):\n    \"\"\"Return the first n items.\"\"\"\n    return items[:n - 1]\n"},
        hidden_files={"test_hidden.py": (
            "import unittest\nfrom stats import window\n\nclass T(unittest.TestCase):\n"
            "    def test_basic(self):\n        self.assertEqual(window([1, 2, 3, 4], 2), [1, 2])\n"
            "    def test_short(self):\n        self.assertEqual(window([1], 5), [1])\n"
            "    def test_empty(self):\n        self.assertEqual(window([], 3), [])\n")},
        checks=[{"type": "command", "cmd": "{py} -m unittest -q test_hidden"}],
        solution={"stats.py": "def window(items, n):\n    \"\"\"Return the first n items.\"\"\"\n    return items[:n]\n"},
        verify="{py} -c \"from stats import window; assert window([1,2,3],2)==[1,2]\"",
    ),
    EvalTask(
        id="implement_slugify",
        prompt="Implement slugify() in text_utils.py exactly as its docstring describes.",
        files={"text_utils.py": (
            "def slugify(text):\n    \"\"\"Lowercase ASCII slug: strip accents, turn runs of non-alphanumerics into a single\n"
            "    '-', and trim '-' from both ends. 'Héllo,  Wörld!' -> 'hello-world'.\"\"\"\n    raise NotImplementedError\n")},
        hidden_files={"test_hidden.py": (
            "import unittest\nfrom text_utils import slugify\n\nclass T(unittest.TestCase):\n"
            "    def test_all(self):\n"
            "        self.assertEqual(slugify('Hello, World!'), 'hello-world')\n"
            "        self.assertEqual(slugify('  Multiple   spaces '), 'multiple-spaces')\n"
            "        self.assertEqual(slugify('Héllo,  Wörld!'), 'hello-world')\n"
            "        self.assertEqual(slugify('--a__b--'), 'a-b')\n        self.assertEqual(slugify('***'), '')\n")},
        checks=[{"type": "command", "cmd": "{py} -m unittest -q test_hidden"}],
        solution={"text_utils.py": (
            "import re\nimport unicodedata\n\n\ndef slugify(text):\n    \"\"\"Lowercase ASCII slug.\"\"\"\n"
            "    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()\n"
            "    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n")},
        verify="{py} -c \"from text_utils import slugify; print(slugify('Hi There'))\"",
    ),
    EvalTask(
        id="rename_across_files",
        prompt="Rename the function `get_usr` to `get_user` everywhere in the project (definition and all callers). "
               "Behaviour must not change; `python main.py` should still print 'alice'.",
        files={
            "users.py": "def get_usr(uid):\n    return {1: 'alice', 2: 'bob'}[uid]\n",
            "service.py": "from users import get_usr\n\n\ndef greet(uid):\n    return get_usr(uid)\n",
            "main.py": "from service import greet\nfrom users import get_usr\n\nprint(greet(1))\nassert get_usr(2) == 'bob'\n",
        },
        checks=[{"type": "not_contains", "path": p, "text": "get_usr"} for p in ("users.py", "service.py", "main.py")]
        + [{"type": "stdout", "cmd": "{py} main.py", "equals": "alice"}],
        solution={
            "users.py": "def get_user(uid):\n    return {1: 'alice', 2: 'bob'}[uid]\n",
            "service.py": "from users import get_user\n\n\ndef greet(uid):\n    return get_user(uid)\n",
            "main.py": "from service import greet\nfrom users import get_user\n\nprint(greet(1))\nassert get_user(2) == 'bob'\n",
        },
        verify="{py} main.py",
    ),
    EvalTask(
        id="cli_sum",
        prompt="Make `python cli.py 1 2 3` print the sum (6). If an argument is not a number, print "
               "'error: <arg> is not a number' to stderr and exit with status 2. With no arguments print 0.",
        files={"cli.py": "import sys\n\n# TODO\n"},
        checks=[{"type": "stdout", "cmd": "{py} cli.py 1 2 3", "equals": "6"},
                {"type": "stdout", "cmd": "{py} cli.py 2.5 0.5", "equals": "3.0"},
                {"type": "stdout", "cmd": "{py} cli.py", "equals": "0"},
                {"type": "command", "cmd": "{py} cli.py 1 x", "expect_exit": 2}],
        solution={"cli.py": (
            "import sys\n\n\ndef main(argv):\n    total = 0\n    for arg in argv:\n        try:\n"
            "            total += float(arg) if '.' in arg else int(arg)\n        except ValueError:\n"
            "            print(f'error: {arg} is not a number', file=sys.stderr)\n            return 2\n"
            "    print(total)\n    return 0\n\n\nif __name__ == '__main__':\n    sys.exit(main(sys.argv[1:]))\n")},
        verify="{py} cli.py 1 2 3",
    ),
    EvalTask(
        id="config_loader",
        prompt="Implement load_config(path) in config.py. It reads a JSON file and returns a dict with defaults "
               "{'port': 8080, 'debug': False} overridden by the file. Unknown keys or an invalid port "
               "(not an int in 1..65535) must raise ValueError.",
        files={"config.py": "import json\n\n\ndef load_config(path):\n    raise NotImplementedError\n"},
        hidden_files={"test_hidden.py": (
            "import json, os, tempfile, unittest\nfrom config import load_config\n\n\ndef w(obj):\n"
            "    f = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)\n    json.dump(obj, f)\n    f.close()\n    return f.name\n\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_defaults(self):\n        self.assertEqual(load_config(w({})), {'port': 8080, 'debug': False})\n"
            "    def test_override(self):\n        self.assertEqual(load_config(w({'port': 9}))['port'], 9)\n"
            "    def test_unknown(self):\n        with self.assertRaises(ValueError):\n            load_config(w({'nope': 1}))\n"
            "    def test_bad_port(self):\n        for p in (0, 70000, 'x', 1.5, True):\n"
            "            with self.assertRaises(ValueError):\n                load_config(w({'port': p}))\n")},
        checks=[{"type": "command", "cmd": "{py} -m unittest -q test_hidden"}],
        solution={"config.py": (
            "import json\n\nDEFAULTS = {'port': 8080, 'debug': False}\n\n\ndef load_config(path):\n"
            "    with open(path) as handle:\n        data = json.load(handle)\n"
            "    unknown = set(data) - set(DEFAULTS)\n    if unknown:\n        raise ValueError(f'unknown keys: {sorted(unknown)}')\n"
            "    cfg = {**DEFAULTS, **data}\n    port = cfg['port']\n"
            "    if type(port) is not int or not 1 <= port <= 65535:\n        raise ValueError('invalid port')\n    return cfg\n")},
        verify="{py} -c \"import config\"",
    ),
    EvalTask(
        id="fix_failing_tests_not_tests",
        prompt="The tests in test_inventory.py fail. Fix the bug in inventory.py. Do NOT modify the tests.",
        files={
            "inventory.py": "def total_value(items):\n    \"\"\"items: list of (price, quantity).\"\"\"\n    return sum(price for price, qty in items)\n",
            "test_inventory.py": (
                "import unittest\nfrom inventory import total_value\n\n\nclass T(unittest.TestCase):\n"
                "    def test_total(self):\n        self.assertEqual(total_value([(2, 3), (5, 1)]), 11)\n"
                "    def test_empty(self):\n        self.assertEqual(total_value([]), 0)\n")},
        checks=[{"type": "command", "cmd": "{py} -m unittest -q test_inventory"},
                {"type": "unchanged", "path": "test_inventory.py"}],
        solution={"inventory.py": "def total_value(items):\n    \"\"\"items: list of (price, quantity).\"\"\"\n    return sum(price * qty for price, qty in items)\n"},
        verify="{py} -m unittest -q test_inventory",
    ),
    EvalTask(
        id="lru_cache",
        prompt="Implement class LRUCache(capacity) in cache.py with get(key) -> value or None, and put(key, value). "
               "Evict the least recently used entry when over capacity; both get and put count as a use.",
        files={"cache.py": "class LRUCache:\n    pass\n"},
        hidden_files={"test_hidden.py": (
            "import unittest\nfrom cache import LRUCache\n\n\nclass T(unittest.TestCase):\n"
            "    def test_eviction(self):\n        c = LRUCache(2)\n        c.put('a', 1)\n        c.put('b', 2)\n        c.get('a')\n"
            "        c.put('c', 3)\n        self.assertIsNone(c.get('b'))\n        self.assertEqual((c.get('a'), c.get('c')), (1, 3))\n"
            "    def test_update_refreshes(self):\n        c = LRUCache(2)\n        c.put('a', 1)\n        c.put('b', 2)\n        c.put('a', 10)\n"
            "        c.put('c', 3)\n        self.assertEqual(c.get('a'), 10)\n        self.assertIsNone(c.get('b'))\n"
            "    def test_capacity_one(self):\n        c = LRUCache(1)\n        c.put('a', 1)\n        c.put('b', 2)\n"
            "        self.assertIsNone(c.get('a'))\n        self.assertEqual(c.get('b'), 2)\n")},
        checks=[{"type": "command", "cmd": "{py} -m unittest -q test_hidden"}],
        solution={"cache.py": (
            "from collections import OrderedDict\n\n\nclass LRUCache:\n    def __init__(self, capacity):\n"
            "        self.capacity = capacity\n        self._data = OrderedDict()\n\n    def get(self, key):\n"
            "        if key not in self._data:\n            return None\n        self._data.move_to_end(key)\n"
            "        return self._data[key]\n\n    def put(self, key, value):\n        self._data[key] = value\n"
            "        self._data.move_to_end(key)\n        if len(self._data) > self.capacity:\n            self._data.popitem(last=False)\n")},
        verify="{py} -c \"from cache import LRUCache; LRUCache(1)\"",
    ),
    EvalTask(
        id="fix_two_file_bug",
        prompt="`python -m app.main` crashes. Make it print 'Hello, Ada Lovelace' without changing the printed text format.",
        files={
            "app/__init__.py": "",
            "app/helpers.py": "def format_name(first, last):\n    return f'{first} {last}'\n",
            "app/main.py": "from app.helpers import fmt_name\n\n\ndef main():\n    print('Hello, ' + fmt_name('Ada'))\n\n\nif __name__ == '__main__':\n    main()\n",
        },
        checks=[{"type": "stdout", "cmd": "{py} -m app.main", "equals": "Hello, Ada Lovelace"}],
        solution={"app/main.py": "from app.helpers import format_name\n\n\ndef main():\n    print('Hello, ' + format_name('Ada', 'Lovelace'))\n\n\nif __name__ == '__main__':\n    main()\n"},
        verify="{py} -m app.main",
    ),
]
