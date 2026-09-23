#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""整页截图 —— 一次拍完整个页面（含滚动才能看到的部分）。

为什么需要它：
  headless 的 --screenshot 只拍当前视口，而 #hash 锚点滚动在这个环境里
  是坏的（简单长页面也拍不到内容）。所以改用「把 vh 钉死成固定 px」的办法：
  用 1960px 高的窗口渲染，但横幅仍是 291px（= 758 视口下的 38vh），
  比例和真实浏览器完全一致，于是整页一次入镜。

坑：
  · 变体 HTML 必须写在项目根目录。放到子目录里 ./images/ 相对路径就失效，
    图会全部裂成灰块，但布局照旧 —— 极易误判成"图没加载"。
  · 静态改动时若旧版写死了 200vh 的层高，也要一并钉成 px，否则超高窗口下
    200vh 会变成 3920px，牌会被摊得面目全非。

用法: python tools/fullshot.py <源html> <输出png> [视口宽=1440] [视口高=758]
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    src_path = sys.argv[1]
    out_png = sys.argv[2]
    vw = sys.argv[3] if len(sys.argv) > 3 else '1440'
    vh = int(sys.argv[4]) if len(sys.argv) > 4 else 758

    s = io.open(src_path, encoding='utf-8').read()
    # vh -> 等价 px，这样超高窗口不会改变任何比例
    s = s.replace('200vh', '%dpx' % (vh * 2))
    s = s.replace('100vh', '%dpx' % vh)
    for pct in (38, 30, 50, 62, 70):
        s = s.replace('%dvh' % pct, '%dpx' % round(vh * pct / 100.0))

    variant = os.path.join(ROOT, '_fullpage_preview.html')
    io.open(variant, 'w', encoding='utf-8').write(s)
    try:
        subprocess.check_call(['bash', os.path.join(ROOT, 'tools', 'shot.sh'),
                               variant, out_png, vw, '1960', '16'])
    finally:
        if os.path.exists(variant):
            os.remove(variant)


if __name__ == '__main__':
    main()
