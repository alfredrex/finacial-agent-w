"""
Python RESP 客户端 for kvstore (C 语言高性能键值存储)

支持: Array SET/GET/DEL/MOD/EXIST, Hash HSET/HGET/HDEL/HMOD/HEXIST,
      SkipList SSET/SGET/SDEL/SMOD/SEXIST

RESP 协议格式:
  请求: *N\r\n$L1\r\nCMD\r\n$L2\r\nARG1\r\n...
  响应: +OK\r\n | -ERR\r\n | :N\r\n | $L\r\nDATA\r\n | $-1\r\n

注意事项:
  - SET 已存在 key → 返回 :0 或 1 (拒绝覆盖)；新建 → +OK
  - MOD 不存在 key → 返回 :0 或 1 (拒绝新建)；修改成功 → +OK
  - upsert() 封装了"有则 MOD 无则 SET"的自动回退逻辑
  - 心跳: 连接池会定期 PING 检查连接健康
"""

import socket
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# ─── RESP Protocol Helpers ──────────────────────────────────────

def _encode_command(*args: str) -> bytes:
    """将命令参数编码为 RESP 协议格式。
    
    Example:
        _encode_command("HSET", "user:1:name", "Alice")
        → b'*3\r\n$4\r\nHSET\r\n$12\r\nuser:1:name\r\n$5\r\nAlice\r\n'
    """
    parts = [f"*{len(args)}\r\n"]
    for arg in args:
        arg_bytes = arg.encode("utf-8")
        parts.append(f"${len(arg_bytes)}\r\n")
        parts.append(arg_bytes.decode("latin-1"))  # 保留原始字节
        parts.append("\r\n")
    return "".join(parts).encode("latin-1")


def _decode_response(data: bytes) -> Tuple[str, Optional[str], int]:
    """解码 RESP 响应。
    
    Returns:
        (resp_type, value, bytes_consumed)
        resp_type: 'simple' | 'error' | 'integer' | 'bulk' | 'null'
    """
    if not data:
        return ("empty", None, 0)

    first_byte = data[0:1]

    if first_byte == b"+":  # +OK\r\n
        end = data.find(b"\r\n")
        if end == -1:
            return ("incomplete", None, 0)
        return ("simple", data[1:end].decode("utf-8", errors="replace"), end + 2)

    elif first_byte == b"-":  # -ERR\r\n
        end = data.find(b"\r\n")
        if end == -1:
            return ("incomplete", None, 0)
        return ("error", data[1:end].decode("utf-8", errors="replace"), end + 2)

    elif first_byte == b":":  # :N\r\n
        end = data.find(b"\r\n")
        if end == -1:
            return ("incomplete", None, 0)
        return ("integer", data[1:end].decode("utf-8"), end + 2)

    elif first_byte == b"$":  # $L\r\nDATA\r\n or $-1\r\n
        first_end = data.find(b"\r\n")
        if first_end == -1:
            return ("incomplete", None, 0)
        length_str = data[1:first_end].decode("utf-8")
        try:
            length = int(length_str)
        except ValueError:
            return ("error", f"bad bulk length: {length_str}", first_end + 2)

        if length == -1:
            return ("null", None, first_end + 2)

        data_start = first_end + 2
        data_end = data_start + length
        if len(data) < data_end + 2:
            return ("incomplete", None, 0)

        value = data[data_start:data_end].decode("utf-8", errors="replace")
        return ("bulk", value, data_end + 2)

    elif first_byte.isdigit() or first_byte == b"\x00":
        # kvstore 有些响应没有 RESP 类型前缀 (如 SSET 重复 key 返回 "1\r\n")
        end = data.find(b"\r\n")
        if end == -1:
            return ("incomplete", None, 0)
        raw = data[0:end].decode("utf-8")
        try:
            int(raw)
            return ("integer", raw, end + 2)
        except ValueError:
            return ("unknown", raw, end + 2)

    else:
        return ("unknown", data[:50].decode("utf-8", errors="replace"), 0)


def _parse_response(data: bytes) -> Tuple[str, Optional[str]]:
    """解析完整 RESP 响应，处理可能的粘包。"""
    resp_type, value, consumed = _decode_response(data)
    if resp_type == "incomplete":
        return ("incomplete", None)
    return (resp_type, value)


# ─── KvstoreClient ─────────────────────────────────────────────

class KvstoreError(Exception):
    """kvstore 操作异常"""
    pass


class KvstoreClient:
    """kvstore RESP 协议 TCP 客户端。

    Usage:
        client = KvstoreClient(host="127.0.0.1", port=2000)
        client.connect()
        client.set("mykey", "myvalue")
        value = client.get("mykey")
        client.close()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 2000,
                 timeout: float = 5.0, auto_reconnect: bool = True):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.auto_reconnect = auto_reconnect
        self._sock: Optional[socket.socket] = None
        self._recv_buf = b""
        self._connect_time = 0.0

    # ── Connection ─────────────────────────────────────────

    def connect(self) -> bool:
        """建立 TCP 连接。已连接时先关闭旧连接。"""
        self.close()
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._connect_time = time.time()
            self._recv_buf = b""
            logger.debug(f"Connected to kvstore {self.host}:{self.port}")
            return True
        except (socket.error, OSError) as e:
            logger.error(f"Failed to connect: {e}")
            self._sock = None
            return False

    def close(self):
        """关闭连接。"""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._recv_buf = b""

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    def _ensure_connected(self):
        """确保连接可用，否则自动重连。"""
        if self._sock is None:
            if self.auto_reconnect:
                if not self.connect():
                    raise KvstoreError(
                        f"Cannot connect to kvstore {self.host}:{self.port}"
                    )
            else:
                raise KvstoreError("Not connected to kvstore")

    # ── Core I/O ───────────────────────────────────────────

    def _send(self, data: bytes):
        """发送原始字节。"""
        self._ensure_connected()
        try:
            self._sock.sendall(data)
        except (socket.error, OSError) as e:
            self.close()
            raise KvstoreError(f"Send failed: {e}")

    def _recv_until_complete(self) -> bytes:
        """接收直到至少有一个完整 RESP 响应。"""
        self._ensure_connected()
        try:
            while True:
                # 先检查缓冲区是否已有完整响应
                resp_type, _, consumed = _decode_response(self._recv_buf)
                if resp_type not in ("incomplete", "empty"):
                    return self._recv_buf

                # 不够，继续读
                self._sock.settimeout(self.timeout)
                chunk = self._sock.recv(65536)
                if not chunk:
                    self.close()
                    raise KvstoreError("Connection closed by server")
                self._recv_buf += chunk
        except socket.timeout:
            raise KvstoreError("Receive timeout")
        except (socket.error, OSError) as e:
            self.close()
            raise KvstoreError(f"Receive failed: {e}")

    def execute(self, *args: str) -> Tuple[str, Optional[str]]:
        """执行一条命令，返回 (resp_type, value)。

        Args:
            *args: 命令及参数，如 "HSET", "key", "value"

        Returns:
            (resp_type, value):
                - ("simple", "OK")
                - ("bulk", "value_data")
                - ("integer", "1")
                - ("null", None)
                - ("error", "ERR message")

        Raises:
            KvstoreError: 连接/发送失败
        """
        data = _encode_command(*args)
        self._send(data)
        self._recv_until_complete()

        resp_type, value, consumed = _decode_response(self._recv_buf)
        if resp_type == "incomplete":
            raise KvstoreError("Incomplete response (protocol error)")

        self._recv_buf = self._recv_buf[consumed:]
        return (resp_type, value)

    def pipeline(self, commands: List[List[str]]) -> List[Tuple[str, Optional[str]]]:
        """批量执行多条命令，一次发送统一接收。

        Args:
            commands: 命令列表，每条是参数列表
                      [["SET", "k1", "v1"], ["SET", "k2", "v2"]]

        Returns:
            [(resp_type, value), ...] 与 commands 顺序对应
        """
        # 拼接所有命令到一个发送缓冲区
        all_data = b"".join(_encode_command(*cmd) for cmd in commands)
        self._send(all_data)

        results = []
        for _ in commands:
            self._recv_until_complete()
            resp_type, value, consumed = _decode_response(self._recv_buf)
            self._recv_buf = self._recv_buf[consumed:]
            results.append((resp_type, value))

        return results

    # ── Basic Commands (Array Engine) ───────────────────────

    def ping(self) -> bool:
        """PING 检查连通性。"""
        try:
            resp_type, _ = self.execute("PING")
            return resp_type == "simple"
        except KvstoreError:
            return False

    def set(self, key: str, value: str) -> bool:
        """SET: 新建 key。已存在返回 False。"""
        resp_type, _ = self.execute("SET", key, value)
        return resp_type == "simple"  # +OK

    def get(self, key: str) -> Optional[str]:
        """GET: 获取值。不存在返回 None。"""
        resp_type, value = self.execute("GET", key)
        if resp_type == "null":
            return None
        if resp_type == "bulk":
            return value
        return None

    def delete(self, key: str) -> bool:
        """DEL: 删除 key。"""
        resp_type, _ = self.execute("DEL", key)
        return resp_type == "simple"

    def mod(self, key: str, value: str) -> bool:
        """MOD: 修改已存在的 key。不存在返回 False。"""
        resp_type, _ = self.execute("MOD", key, value)
        return resp_type == "simple"

    def exists(self, key: str) -> bool:
        """EXIST: 判断 key 是否存在。"""
        resp_type, value = self.execute("EXIST", key)
        if resp_type == "integer":
            return value == "1"  # RESP :1 = exists
        return False

    def upsert(self, key: str, value: str) -> bool:
        """有则 MOD，无则 SET。总是成功（除非存储满）。"""
        resp_type, _ = self.execute("MOD", key, value)
        if resp_type == "simple":
            return True
        # MOD 失败（key 不存在），尝试 SET
        return self.set(key, value)

    # ── Hash Commands ──────────────────────────────────────

    def hset(self, key: str, value: str) -> bool:
        """HSET: 哈希表存储 key-value。key 已存在返回 False。"""
        resp_type, _ = self.execute("HSET", key, value)
        return resp_type == "simple"

    def hget(self, key: str) -> Optional[str]:
        """HGET: 哈希表获取。不存在返回 None。"""
        resp_type, value = self.execute("HGET", key)
        if resp_type == "null":
            return None
        if resp_type == "bulk":
            return value
        return None

    def hdel(self, key: str) -> bool:
        """HDEL: 哈希表删除。"""
        resp_type, _ = self.execute("HDEL", key)
        return resp_type == "simple"

    def hmod(self, key: str, value: str) -> bool:
        """HMOD: 修改已存在的哈希 key。不存在返回 False。"""
        resp_type, _ = self.execute("HMOD", key, value)
        return resp_type == "simple"

    def hexists(self, key: str) -> bool:
        """HEXIST: 判断哈希 key 是否存在。"""
        resp_type, value = self.execute("HEXIST", key)
        if resp_type == "integer":
            return value == "1"  # RESP :1 = exists
        return False

    def hupsert(self, key: str, value: str) -> bool:
        """哈希 upsert: 有则 HMOD，无则 HSET。"""
        resp_type, _ = self.execute("HMOD", key, value)
        if resp_type == "simple":
            return True
        return self.hset(key, value)

    def hset_multi(self, mapping: Dict[str, str]) -> int:
        """批量 HSET，返回成功数。每个 key-value 对作为独立 key 存储。"""
        commands = [["HSET", k, v] for k, v in mapping.items()]
        results = self.pipeline(commands)
        return sum(1 for t, _ in results if t == "simple")

    def hupsert_multi(self, mapping: Dict[str, str]) -> int:
        """批量 hupsert (有则 HMOD，无则 HSET)，返回成功数。

        优化: 第一轮 pipeline 全部 MOD → 对失败项 pipeline SET。
        """
        items = list(mapping.items())
        # Round 1: 全部 MOD
        mod_cmds = [["HMOD", k, v] for k, v in items]
        mod_results = self.pipeline(mod_cmds)
        # Round 2: MOD 失败的 → SET
        set_cmds = []
        set_indices = []
        for i, (k, v) in enumerate(items):
            if mod_results[i][0] != "simple":
                set_cmds.append(["HSET", k, v])
                set_indices.append(i)
        ok = sum(1 for t, _ in mod_results if t == "simple")
        if set_cmds:
            set_results = self.pipeline(set_cmds)
            ok += sum(1 for t, _ in set_results if t == "simple")
        return ok

    def hget_multi(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """批量 HGET。"""
        commands = [["HGET", k] for k in keys]
        results = self.pipeline(commands)
        return {
            k: v if t == "bulk" else None
            for k, (t, v) in zip(keys, results)
        }

    def hget_prefix(self, prefix: str) -> Dict[str, str]:
        """按前缀获取所有匹配的 key-value。

        注意: kvstore 不支持 SCAN/KEYS，此方法需要调用者维护 key 列表。
        调用者应先通过 HSET 时将 key 追加到一个索引列表中。
        """
        raise NotImplementedError(
            "kvstore does not support SCAN/KEYS. "
            "Use hget_multi() with known keys, or maintain a key index."
        )

    def hdel_multi(self, keys: List[str]) -> int:
        """批量 HDEL，返回成功数。"""
        commands = [["HDEL", k] for k in keys]
        results = self.pipeline(commands)
        return sum(1 for t, _ in results if t == "simple")

    # ── SkipList Commands ──────────────────────────────────

    def sset(self, key: str, value: str) -> bool:
        """SSET: 跳表存储。key 已存在返回 False。"""
        resp_type, _ = self.execute("SSET", key, value)
        return resp_type == "simple"

    def sget(self, key: str) -> Optional[str]:
        """SGET: 跳表获取。"""
        resp_type, value = self.execute("SGET", key)
        if resp_type == "null":
            return None
        if resp_type == "bulk":
            return value
        return None

    def sdel(self, key: str) -> bool:
        """SDEL: 跳表删除。"""
        resp_type, _ = self.execute("SDEL", key)
        return resp_type == "simple"

    def smod(self, key: str, value: str) -> bool:
        """SMOD: 修改已存在的跳表 key。"""
        resp_type, _ = self.execute("SMOD", key, value)
        return resp_type == "simple"

    def sexists(self, key: str) -> bool:
        """SEXIST: 判断跳表 key 是否存在。"""
        resp_type, value = self.execute("SEXIST", key)
        if resp_type == "integer":
            return value == "1"  # RESP :1 = exists (修复后统一语义)
        return False

    def supsert(self, key: str, value: str) -> bool:
        """跳表 upsert: 有则 SMOD，无则 SSET。"""
        resp_type, _ = self.execute("SMOD", key, value)
        if resp_type == "simple":
            return True
        return self.sset(key, value)

    # ── Utility ────────────────────────────────────────────

    def flush_all(self):
        """清空所有数据（慎用！）。

        由于 kvstore 没有 FLUSHALL 命令，需要通过重启 kvstore 进程来清空。
        或者使用已知 key 列表逐个 DEL。
        """
        logger.warning("kvstore does not support FLUSHALL. Close and restart the server.")

    def stats(self) -> Dict[str, Any]:
        """获取客户端连接信息（不涉及服务端状态）。"""
        return {
            "host": self.host,
            "port": self.port,
            "connected": self.is_connected,
            "uptime_seconds": time.time() - self._connect_time if self._sock else 0,
        }

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()
