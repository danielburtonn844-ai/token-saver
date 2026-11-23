"""可复现的测试语料。固定种子，重复运行结果一致。"""
from __future__ import annotations

import json
import random

SEED = 20261123


def build_log(n=120000):
    rnd = random.Random(SEED)
    out = []
    for i in range(n):
        r = rnd.random()
        if r < 0.002:
            out.append(f"2026-01-01 12:00:{i % 60:02d} ERROR build/src/mod{i % 400}.go:{i % 900} "
                       f"undefined: symbol S{i % 50} (code E{i % 37})")
        elif r < 0.02:
            out.append(f"npm WARN deprecated pkg-{i % 60}@{i % 9}.0.0: use pkg-new instead")
        elif r < 0.10:
            out.append(f"    at frame{i % 80} (/srv/app/src/mod{i % 200}.js:{i % 1000}:{i % 30})")
        elif r < 0.14:
            out.append(f"[{'#' * ((i // 500) % 20):<20}] {min(99, i // 1200)}%")
        elif r < 0.18:
            out.append(f"    {i % 200} passing ({(i % 900) + 100}ms)")
        else:
            out.append(f"2026-01-01 12:00:{i % 60:02d} INFO req={i} status=200 "
                       f"path=/api/v1/items/{i % 5000} dur={i % 300}ms")
    return out


def test_output(n=8000):
    rnd = random.Random(SEED + 1)
    out = ["============================= test session starts ============================="]
    for i in range(n):
        if rnd.random() < 0.03:
            out.append(f"FAILED tests/test_mod{i % 300}.py::test_case_{i} - AssertionError: "
                       f"assert {i} == {i + 1}")
            out.append(f"E       AssertionError: expected {i} but got {i + 1}")
            out.append(f"tests/test_mod{i % 300}.py:{i % 400}: in test_case_{i}")
        else:
            out.append(f"tests/test_mod{i % 300}.py::test_case_{i} PASSED [{i % 90:.2f}s]")
    out.append("=========== 3 failed, 7997 passed, 12 warnings in 421.33s ============")
    return out


def json_dump(n=60000):
    rnd = random.Random(SEED + 2)
    out = []
    for i in range(n):
        out.append(json.dumps({
            "id": i, "name": f"item-{i}", "price": round(rnd.random() * 1000, 2),
            "tags": ["a", "b", "c"][: i % 4], "active": i % 3 != 0,
            "meta": {"created": "2026-01-01T00:00:00Z", "owner": f"user{i % 500}"},
        }, ensure_ascii=False))
    return out


def traversal(n=80000):
    out = ["/srv/app:"]
    for i in range(n):
        if i % 7 == 0:
            out.append(f"drwxr-xr-x {2 + i % 9} root root {4096 + i % 1000} Jan 1 00:00 dir{i}")
        else:
            out.append(f"-rw-r--r-- 1 root root {100 + i % 900000} Jan 1 00:00 file{i}.ext")
    return out


def access_log(n=150000):
    rnd = random.Random(SEED + 3)
    out = []
    for i in range(n):
        status = 200 if rnd.random() > 0.02 else rnd.choice([301, 400, 401, 403, 404, 500, 502])
        out.append(f'10.{i % 255}.{(i // 255) % 255}.{i % 200} - - [01/Jan/2026:00:00:{i % 60:02d} +0800] '
                   f'"GET /api/v1/resource/{i % 9000} HTTP/1.1" {status} {100 + i % 9000} "-" '
                   f'"Mozilla/5.0" rt={rnd.random() * 2:.3f}')
    return out


def stacktrace(n=3000):
    body = [
        "Traceback (most recent call last):",
        '  File "/srv/app/main.py", line 42, in <module>',
        "    run()",
        '  File "/srv/app/core/runner.py", line 88, in run',
        "    task.execute()",
        '  File "/srv/app/core/task.py", line 17, in execute',
        "    raise ValueError('bad payload: field amount missing')",
        "ValueError: bad payload: field amount missing",
    ]
    return body * (n // len(body))


def chinese_log(n=12000):
    rnd = random.Random(SEED + 4)
    out = []
    for i in range(n):
        if rnd.random() < 0.01:
            out.append(f"2026-01-01 12:00:{i % 60:02d} 错误 订单 {i} 支付失败：余额不足，用户 {i % 900}")
        elif rnd.random() < 0.1:
            out.append(f"2026-01-01 12:00:{i % 60:02d} 警告 库存 {i % 300} 低于阈值，请补货")
        else:
            out.append(f"2026-01-01 12:00:{i % 60:02d} 信息 收到请求 编号={i} 路径=/接口/订单/{i % 500} 耗时={i % 200}毫秒")
    return out


CORPORA = {
    "build_log": build_log,
    "test_output": test_output,
    "json_dump": json_dump,
    "traversal": traversal,
    "access_log": access_log,
    "stacktrace": stacktrace,
    "chinese_log": chinese_log,
}


def get(name: str) -> list[str]:
    return CORPORA[name]()
