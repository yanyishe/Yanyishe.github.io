// 曲目清单 —— 由 tools/gen_music_manifest.py 扫描 music/ 目录生成，请勿手改。
//
// 加歌：把音频丢进 music/，再跑一次这个脚本。
// 配封面：在 music/ 里放一张同名的图片，例如
//         01-夜色低语.mp3  +  01-夜色低语.jpg
//         cover 为 null 时，播放器退回牌背的面具那张图。
//
// 这里用 .js 而不是 .json：json 要靠 fetch 取，而 fetch 在 file:// 下会被
// CORS 拦掉 —— 本地双击打开 index.html 时音乐就消失了。<script src> 没这个问题。
window.YYS_TRACKS = [
  { file: "01-全人类的灵魂之诗.mp3", title: "全人类的灵魂之诗", cover: "./music/01-全人类的灵魂之诗.webp" },
  { file: "02-School Days.mp3", title: "School Days", cover: "./music/02-School Days.webp" },
  { file: "03-ＭＡＰ珠閒瑠市.mp3", title: "ＭＡＰ珠閒瑠市", cover: "./music/03-ＭＡＰ珠閒瑠市.webp" },
  { file: "04-Map I.mp3", title: "Map I", cover: "./music/04-Map I.webp" },
  { file: "05-When The Moon's Reaching Out Stars -Reload.mp3", title: "When The Moon's Reaching Out Stars -Reload", cover: "./music/05-When The Moon's Reaching Out Stars -Reload.webp" },
  { file: "06-A way of Life -Deep inside my mind Remix.mp3", title: "A way of Life -Deep inside my mind Remix", cover: "./music/06-A way of Life -Deep inside my mind Remix.webp" },
  { file: "07-Heartbeat, Heartbreak .mp3", title: "Heartbeat, Heartbreak", cover: "./music/07-Heartbeat, Heartbreak .webp" },
  { file: "08-Beneath the Mask -rain.mp3", title: "Beneath the Mask -rain", cover: "./music/08-Beneath the Mask -rain.webp" },
];
