"""Loopback proxy-auth relay.

Orbita 146 block direct proxy connections tới private LAN (RFC1918) nhưng cho
phép loopback (127.0.0.1). Module này lên 1 asyncio TCP server phí
127.0.0.1:<random_port>, nhận HTTP/HTTPS proxy traffic từ Orbita, inject
`Proxy-Authorization: Basic <b64>` vào first request, rồi forward
to-upstream-proxy bidirectionally.

Sử dụng asyncio + IOCP trên Windows → throughput ~200-500 MB/s 1 stream.

API:
    relay = ProxyRelay("192.168.1.9", 33706, "user", "pass")
    relay.start()        # blocking until listening
    relay.local_port     # 127.0.0.1:<port>
    relay.local_url      # http://127.0.0.1:<port>
    relay.stop()
"""

import asyncio
import base64
import logging
import socket
import threading

logger = logging.getLogger(__name__)

_BUF = 65536  # 64KB
_FIRST_CHUNK_MAX = 16384  # hơn cả 1 request line + headers


class ProxyRelay:
    def __init__(self, upstream_host: str, upstream_port: int,
                 username: str = "", password: str = "",
                 listen_host: str = "127.0.0.1"):
        self.upstream_host = upstream_host
        self.upstream_port = int(upstream_port)
        self.username = username or ""
        self.password = password or ""
        self.listen_host = listen_host
        self.local_port = 0

        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.AbstractServer | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._auth_header_bytes = self._build_auth_header()

    def _build_auth_header(self) -> bytes:
        if not self.username:
            return b""
        creds = f"{self.username}:{self.password}".encode("utf-8")
        b64 = base64.b64encode(creds).decode("ascii")
        return f"Proxy-Authorization: Basic {b64}\r\n".encode("ascii")

    @property
    def local_url(self) -> str:
        return f"http://{self.listen_host}:{self.local_port}"

    def start(self, timeout: float = 5.0) -> int:
        """Start relay in background thread. Return local_port. Blocks until listening."""
        if self._thread and self._thread.is_alive():
            return self.local_port

        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"ProxyRelay-{self.upstream_host}")
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("ProxyRelay did not start in time")
        return self.local_port

    def stop(self):
        if not self._loop:
            return
        try:
            self._loop.call_soon_threadsafe(self._shutdown)
        except RuntimeError:
            pass
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = None
        self._server = None

    def _shutdown(self):
        if self._server:
            self._server.close()
        # Cancel all running tasks
        for t in asyncio.all_tasks(loop=self._loop):
            t.cancel()

    def _run(self):
        # On Windows, ProactorEventLoop uses IOCP for socket I/O
        if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            loop.run_until_complete(self._serve())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("ProxyRelay loop crashed: %s", e)
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    async def _serve(self):
        self._server = await asyncio.start_server(
            self._handle, host=self.listen_host, port=0,
            backlog=128, reuse_address=True,
        )
        sock = self._server.sockets[0]
        self.local_port = sock.getsockname()[1]
        # Make accepted sockets larger buffer
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)
        except OSError:
            pass
        logger.info("ProxyRelay listening on %s:%d -> %s:%d",
                    self.listen_host, self.local_port,
                    self.upstream_host, self.upstream_port)
        self._ready.set()
        try:
            async with self._server:
                await self._server.serve_forever()
        except (asyncio.CancelledError, Exception):
            pass

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        upstream_reader = upstream_writer = None
        try:
            # Read enough to capture the first HTTP request line + headers
            first = await asyncio.wait_for(reader.read(_FIRST_CHUNK_MAX), timeout=15)
            if not first:
                return
            modded = self._inject_auth(first)

            # Open upstream
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(host=self.upstream_host, port=self.upstream_port),
                timeout=15,
            )
            # Tune upstream socket buffers
            try:
                up_sock = upstream_writer.get_extra_info("socket")
                if up_sock is not None:
                    up_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
                    up_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)
                    up_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            cl_sock = writer.get_extra_info("socket")
            if cl_sock is not None:
                try:
                    cl_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass

            upstream_writer.write(modded)
            await upstream_writer.drain()

            # Bidirectional pump
            await asyncio.gather(
                self._pump(reader, upstream_writer),
                self._pump(upstream_reader, writer),
                return_exceptions=True,
            )
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            logger.debug("relay %s closed: %s", peer, e)
        except Exception as e:
            logger.warning("relay %s error: %s", peer, e)
        finally:
            for w in (upstream_writer, writer):
                if w is not None:
                    try:
                        w.close()
                    except Exception:
                        pass

    @staticmethod
    async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                data = await reader.read(_BUF)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            try:
                writer.write_eof()
            except (OSError, RuntimeError, AttributeError):
                pass

    def _inject_auth(self, first_chunk: bytes) -> bytes:
        """Inject Proxy-Authorization header after first request line."""
        if not self._auth_header_bytes:
            return first_chunk
        # Already has Proxy-Authorization? Skip.
        if b"Proxy-Authorization:" in first_chunk[:_FIRST_CHUNK_MAX]:
            return first_chunk
        # Find end of request line (first CRLF)
        idx = first_chunk.find(b"\r\n")
        if idx < 0:
            # No request line yet, forward as-is (probably TLS or junk)
            return first_chunk
        return first_chunk[:idx + 2] + self._auth_header_bytes + first_chunk[idx + 2:]


def is_private_ipv4(host: str) -> bool:
    """RFC1918 + link-local. 127.0.0.0/8 NOT considered private here."""
    try:
        parts = [int(p) for p in host.split(".")]
        if len(parts) != 4:
            return False
        a, b, *_ = parts
        if a == 10:
            return True
        if a == 192 and b == 168:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 169 and b == 254:
            return True
        return False
    except (ValueError, IndexError):
        return False
