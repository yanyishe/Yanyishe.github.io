# -*- coding: utf-8 -*-
"""按页面实际显示尺寸下采样并转 WebP，控制解码内存与传输体积。"""
import os
from PIL import Image

SRC = r'E:/mygit/Yanyishe.github.io/images'
LOG = []


def prep(path):
    im = Image.open(path)
    # 照片类素材若有全不透明 alpha，丢掉 alpha 通道省内存
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        if im.getchannel('A').getextrema() == (255, 255):
            im = im.convert('RGB')
    elif im.mode not in ('RGB', 'L'):
        im = im.convert('RGB')
    return im


def emit(src_name, out_name, target_w, quality=82, label=''):
    src = os.path.join(SRC, src_name)
    im = prep(src)
    ow, oh = im.size
    if target_w and target_w < ow:
        th = max(1, round(oh * target_w / ow))
        im = im.resize((target_w, th), Image.LANCZOS)
    else:
        th = oh
    out = os.path.join(SRC, out_name)
    im.save(out, 'WEBP', quality=quality, method=6)
    fs = os.path.getsize(out)
    dw, dh = im.size
    before = os.path.getsize(src)
    LOG.append((label or src_name, ow, oh, before, dw, dh, fs,
                ow * oh * 4 * ch(Image.open(src)), dw * dh * 4 * len(im.getbands())))
    print('  %-18s %5dx%-5d %8.1fKB  ->  %4dx%-4d %7.1fKB  q%d'
          % (out_name, ow, oh, before / 1024, dw, dh, fs / 1024, quality))


def ch(im):
    return len(im.convert('RGBA').getbands())


print('== 主视觉 ==')
emit('persona-30th-banner.png', 'banner.webp', 2560, 80, '顶部横幅')
emit('persona-characters.png', 'persona-hero.webp', 1440, 80, '角色群像')
emit('persona-characters.png', 'persona-bg.webp', 700, 60, '背景水印')
emit('p30-logo.png', 'p30-logo.webp', 240, 86, 'logo')

print('== 塔罗牌 ==')
for i in range(22):
    emit('tarot-%02d.png' % i, 'tarot-%02d.webp' % i, 320, 80, 'tarot-%02d' % i)
emit('tarot-back.png', 'tarot-back.webp', 320, 80, 'tarot-back')

tb = sum(r[3] for r in LOG)
ta = sum(r[6] for r in LOG)
db = sum(r[7] for r in LOG)
da = sum(r[8] for r in LOG)
print('\n== 合计 ==')
print('  传输体积:  %.2f MB  ->  %.0f KB   (降幅 %.1f%%)'
      % (tb / 1048576, ta / 1024, (1 - ta / tb) * 100))
print('  解码内存:  %.0f MB  ->  %.0f MB   (降幅 %.1f%%)'
      % (db / 1048576, da / 1048576, (1 - da / db) * 100))
