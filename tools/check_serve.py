#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
以「被 HTTP 服务器发布」的方式校验页面 —— 模拟 GitHub Pages 的真实处境。

本地 file:// 打开永远看不出问题（路径解析、相对根、大小写都由 Windows 兜住了），
而 .io 上是 Linux 服务器按 URL 取文件。所以发布前必须用 http 跑一遍。

用法：
    python tools/check_serve.py [base_url]
    # 默认 http://127.0.0.1:8765
"""
import io
import re
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765').rstrip('/')


def probe(url):
    """返回 (状态码, Content-Type, 字节数)；异常时状态码为 None。"""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read()
            return resp.status, resp.headers.get('Content-Type'), len(body)
    except urllib.error.HTTPError as e:
        return e.code, None, 0
    except Exception as e:  # 连接失败等
        return None, type(e).__name__, 0


def main():
    html = io.open('index.html', encoding='utf-8').read()

    # 页面里所有 ./images/xxx 形式的引用（区分大小写）
    refs = sorted(set(re.findall(r'\./(images/[A-Za-z0-9._-]+)', html)))

    # 顺带扫一遍绝对路径引用：在 .io 的子路径部署下会全部失效
    absolute = sorted(set(re.findall(r'["\'(](/(?!/)[A-Za-z0-9._/-]+)', html)))

    st, ct, n = probe(BASE + '/')
    print('%-46s %-5s %-26s %s' % ('请求', '状态', 'Content-Type', '大小'))
    print('-' * 92)
    print('%-46s %-5s %-26s %d B' % ('/            (index.html)', st, ct, n))

    failed = []
    for r in refs:
        st, ct, n = probe('%s/%s' % (BASE, r))
        if st != 200:
            failed.append((r, st))
        print('%-46s %-5s %-26s %d B' % (r, st, ct, n))

    print()
    print('被引用的图片        :', len(refs))
    print('取不到的引用        :', failed or '无')
    print('绝对路径引用(危险)  :', absolute or '无')
    print()
    if failed or absolute:
        print('结论: 不适合直接发布，先修上面的条目')
        return 1
    print('结论: 所有引用都能按 URL 取到，可以发布')
    return 0


if __name__ == '__main__':
    sys.exit(main())
