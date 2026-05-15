"""
kvstore_client 验证脚本
对运行中的 kvstore 执行全量功能测试
"""
import sys
import os
import importlib.util

# 直接加载模块，避免触发 __init__.py 的 pandas 等依赖链
spec = importlib.util.spec_from_file_location(
    'kvstore_client',
    os.path.join(os.path.dirname(__file__), '..', 'src', 'memory', 'kvstore_client.py')
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
KvstoreClient = mod.KvstoreClient
KvstoreError = mod.KvstoreError


def test(label: str, condition: bool):
    status = "✓" if condition else "✗"
    print(f"  {status} {label}")
    if not condition:
        print(f"    FAILED at test: {label}")
    return condition


def main():
    passed = 0
    failed = 0

    print("=" * 60)
    print("kvstore_client.py 验证测试")
    print("=" * 60)

    client = KvstoreClient(host="127.0.0.1", port=2000, timeout=3)
    try:
        client.connect()
        print("[连接] 成功\n")
    except KvstoreError as e:
        print(f"[连接] 失败: {e}")
        print("请确保 kvstore 在 127.0.0.1:2000 运行")
        sys.exit(1)

    # ─── PING ─────────────────────────────────
    print("─── PING ───")
    ok = test("PING 返回 True", client.ping())
    if ok: passed += 1
    else: failed += 1

    # ─── Array Engine ─────────────────────────
    print("\n─── Array: SET/GET/DEL/MOD/EXIST ───")

    # 清理
    client.delete("test_arr")

    ok = test("SET 新 key → +OK", client.set("test_arr", "hello"))
    if ok: passed += 1
    else: failed += 1

    ok = test("GET 存在 key → 'hello'", client.get("test_arr") == "hello")
    if ok: passed += 1
    else: failed += 1

    ok = test("SET 重复 key → False (拒绝覆盖)", not client.set("test_arr", "world"))
    if ok: passed += 1
    else: failed += 1

    ok = test("MOD 修改 → True", client.mod("test_arr", "world"))
    if ok: passed += 1
    else: failed += 1

    ok = test("GET 修改后 → 'world'", client.get("test_arr") == "world")
    if ok: passed += 1
    else: failed += 1

    ok = test("MOD 不存在 key → False", not client.mod("test_nonexist", "x"))
    if ok: passed += 1
    else: failed += 1

    ok = test("EXIST 存在 → True", client.exists("test_arr"))
    if ok: passed += 1
    else: failed += 1

    ok = test("EXIST 不存在 → False", not client.exists("test_nonexist"))
    if ok: passed += 1
    else: failed += 1

    ok = test("DEL → True", client.delete("test_arr"))
    if ok: passed += 1
    else: failed += 1

    ok = test("GET 已删除 → None", client.get("test_arr") is None)
    if ok: passed += 1
    else: failed += 1

    # ─── Upsert ────────────────────────────────
    print("\n─── Array: upsert ───")

    # 先确保不存在
    client.delete("test_up")

    ok = test("upsert 不存在 → SET → True", client.upsert("test_up", "v1"))
    if ok: passed += 1
    else: failed += 1

    ok = test("upsert 后 GET → 'v1'", client.get("test_up") == "v1")
    if ok: passed += 1
    else: failed += 1

    ok = test("upsert 已存在 → MOD → True", client.upsert("test_up", "v2"))
    if ok: passed += 1
    else: failed += 1

    ok = test("upsert 后 GET → 'v2'", client.get("test_up") == "v2")
    if ok: passed += 1
    else: failed += 1

    client.delete("test_up")

    # ─── Hash Engine ───────────────────────────
    print("\n─── Hash: HSET/HGET/HDEL/HMOD/HEXIST ───")

    client.hdel("test_hash")

    ok = test("HSET → True", client.hset("test_hash", "val1"))
    if ok: passed += 1
    else: failed += 1

    ok = test("HGET → 'val1'", client.hget("test_hash") == "val1")
    if ok: passed += 1
    else: failed += 1

    ok = test("HSET 重复 → False", not client.hset("test_hash", "val2"))
    if ok: passed += 1
    else: failed += 1

    ok = test("HMOD 修改 → True", client.hmod("test_hash", "val2"))
    if ok: passed += 1
    else: failed += 1

    ok = test("HGET 修改后 → 'val2'", client.hget("test_hash") == "val2")
    if ok: passed += 1
    else: failed += 1

    ok = test("HMOD 不存在 → False", not client.hmod("test_h_nonexist", "x"))
    if ok: passed += 1
    else: failed += 1

    ok = test("HEXIST 存在 → True", client.hexists("test_hash"))
    if ok: passed += 1
    else: failed += 1

    ok = test("HEXIST 不存在 → False", not client.hexists("test_h_nonexist"))
    if ok: passed += 1
    else: failed += 1

    ok = test("HDEL → True", client.hdel("test_hash"))
    if ok: passed += 1
    else: failed += 1

    ok = test("HGET 已删除 → None", client.hget("test_hash") is None)
    if ok: passed += 1
    else: failed += 1

    # ─── Hash upsert ──────────────────────────
    print("\n─── Hash: hupsert ───")

    ok = test("hupsert 不存在 → True", client.hupsert("test_hu", "a"))
    if ok: passed += 1
    else: failed += 1

    ok = test("hupsert 已存在 → True", client.hupsert("test_hu", "b"))
    if ok: passed += 1
    else: failed += 1

    ok = test("hupsert 后 HGET → 'b'", client.hget("test_hu") == "b")
    if ok: passed += 1
    else: failed += 1

    client.hdel("test_hu")

    # ─── Hash Pipeline ─────────────────────────
    print("\n─── Hash: hset_multi / hget_multi ───")

    mapping = {
        "user:t:name": "测试用户",
        "user:t:style": "价值投资",
        "user:t:risk": "中高",
    }
    count = client.hset_multi(mapping)
    ok = test("hset_multi 3 keys → 3", count == 3)
    if ok: passed += 1
    else: failed += 1

    result = client.hget_multi(list(mapping.keys()))
    ok = test("hget_multi 全部命中", all(
        result.get(k) == v for k, v in mapping.items()
    ))
    if ok: passed += 1
    else: failed += 1

    del_count = client.hdel_multi(list(mapping.keys()))
    ok = test("hdel_multi → 3", del_count == 3)
    if ok: passed += 1
    else: failed += 1

    # ─── SkipList Engine ───────────────────────
    print("\n─── SkipList: SSET/SGET/SDEL/SMOD/SEXIST ───")

    client.sdel("test_sk")

    ok = test("SSET → True", client.sset("test_sk", "sv1"))
    if ok: passed += 1
    else: failed += 1

    ok = test("SGET → 'sv1'", client.sget("test_sk") == "sv1")
    if ok: passed += 1
    else: failed += 1

    ok = test("SSET 重复 → False", not client.sset("test_sk", "sv2"))
    if ok: passed += 1
    else: failed += 1

    ok = test("SMOD 修改 → True", client.smod("test_sk", "sv2"))
    if ok: passed += 1
    else: failed += 1

    ok = test("SGET 修改后 → 'sv2'", client.sget("test_sk") == "sv2")
    if ok: passed += 1
    else: failed += 1

    ok = test("SMOD 不存在 → False", not client.smod("test_sk_nonexist", "x"))
    if ok: passed += 1
    else: failed += 1

    ok = test("SEXIST 存在 → True", client.sexists("test_sk"))
    if ok: passed += 1
    else: failed += 1

    ok = test("SEXIST 不存在 → False", not client.sexists("test_sk_nonexist"))
    if ok: passed += 1
    else: failed += 1

    ok = test("SDEL → True", client.sdel("test_sk"))
    if ok: passed += 1
    else: failed += 1

    ok = test("SGET 已删除 → None", client.sget("test_sk") is None)
    if ok: passed += 1
    else: failed += 1

    # ─── SkipList upsert ──────────────────────
    print("\n─── SkipList: supsert ───")

    ok = test("supsert 不存在 → True", client.supsert("test_su", "a"))
    if ok: passed += 1
    else: failed += 1

    ok = test("supsert 已存在 → True", client.supsert("test_su", "b"))
    if ok: passed += 1
    else: failed += 1

    ok = test("supsert 后 SGET → 'b'", client.sget("test_su") == "b")
    if ok: passed += 1
    else: failed += 1

    client.sdel("test_su")

    # ─── Pipeline 批量 ─────────────────────────
    print("\n─── Pipeline 批量 ───")

    commands = [
        ["SET", "pipe_1", "a"],
        ["SET", "pipe_2", "b"],
        ["HSET", "pipe_h1", "c"],
        ["SSET", "pipe_s1", "d"],
    ]
    results = client.pipeline(commands)
    ok = test("pipeline 4 条 → 全部成功",
              all(t == "simple" for t, _ in results))
    if ok: passed += 1
    else: failed += 1

    # 清理
    for key in ["pipe_1", "pipe_2", "pipe_h1", "pipe_s1"]:
        client.delete(key)

    # ─── 连接断开重连 ──────────────────────────
    print("\n─── 断连重连 ───")
    client.close()
    ok = test("close 后 is_connected=False", not client.is_connected)
    if ok: passed += 1
    else: failed += 1

    ok = test("自动重连后 PING 成功", client.ping())
    if ok: passed += 1
    else: failed += 1

    # ─── 结果 ──────────────────────────────────
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    if failed == 0:
        print("  全部通过！")
    else:
        print(f"  {failed} 项失败，请检查。")
    print("=" * 60)

    client.close()
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
