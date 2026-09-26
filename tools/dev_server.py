# -*- coding: utf-8 -*-
"""带 Range 支持的本机静态服务器 —— 只用于验证，不用来发布。

用法（在项目根目录）：
    python tools/dev_server.py [端口]        # 默认 8899

为什么不能用 `python -m http.server`：
    http.server **不实现 Range 请求** —— 它永远回 200，不带 `Accept-Ranges`。
    浏览器的 <audio>/<video> 在服务器不支持按字节跳读时**无法定位播放点**：
    只能在已经下载好的那一段里走，seek 出去会被弹回原处。
    于是「点进度条跳转」这类功能在本机验证时必然失败，
    而线上（GitHub Pages 会回 206）其实是好的 —— 一个纯粹由测试环境制造的假故障。

已经踩过一次：进度条点 60% 只跳到 0.6 秒，查了半天播放器的代码，
最后发现是 `curl -D -` 一看，本机服务器回的是 200 且没有 Accept-Ranges。
所以：**凡是要验媒体播放，就用这个脚本起服务。**
"""

import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class _Limited:
    """把文件包一层，只吐指定字节数 —— 直接返回文件对象的话，
    SimpleHTTPRequestHandler 的 copyfile 会把整个文件都倒出去。"""

    def __init__(self, f, n):
        self.f = f
        self.n = n

    def read(self, size=-1):
        if self.n <= 0:
            return b""
        if size < 0 or size > self.n:
            size = self.n
        data = self.f.read(size)
        self.n -= len(data)
        return data

    def close(self):
        self.f.close()


class RangeHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # 无条件声明支持按字节跳读 —— <audio> 靠它判断能不能 seek。
        # 放在这里而不是各分支里，是为了避免 206 时重复发一次。
        self.send_header("Accept-Ranges", "bytes")
        SimpleHTTPRequestHandler.end_headers(self)

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or os.path.isdir(path):
            return SimpleHTTPRequestHandler.send_head(self)

        m = RANGE_RE.match(rng.strip())
        if not m:
            return SimpleHTTPRequestHandler.send_head(self)
        try:
            size = os.path.getsize(path)
        except OSError:
            return SimpleHTTPRequestHandler.send_head(self)

        first, last = m.group(1), m.group(2)
        if first == "":
            # bytes=-N：最后 N 个字节
            n = int(last or 0)
            start, end = max(0, size - n), size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(os.path.getmtime(path)))
        self.end_headers()
        return _Limited(f, end - start + 1)

    def log_message(self, fmt, *args):
        # 默认实现每个请求打一行，验证时刷屏；只保留出错的那些
        if str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            sys.stderr.write("  %s %s\n" % (self.address_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    os.chdir(ROOT)
    srv = ThreadingHTTPServer(("127.0.0.1", port), RangeHandler)
    print("验证服务器: http://127.0.0.1:%d/   (根目录 %s)" % (port, ROOT))
    print("支持 Range 请求，和 GitHub Pages 行为一致。Ctrl+C 退出。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
