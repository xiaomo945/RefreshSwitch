// Cloudflare Worker：全局点赞计数器（经典 Service Worker 格式，KV 绑定变量名 LIKES）
// GET  -> 返回当前总数
// POST -> 总数 +1 并返回新值
// 部署：wrangler deploy，或在控制台粘贴本文件并把 KV 命名空间绑定为 LIKES。免费、无需信用卡。

addEventListener('fetch', (event) => {
  event.respondWith(handle(event.request));
});

async function handle(request) {
  let n = parseInt(await LIKES.get('count')) || 0;
  if (request.method === 'POST') {
    n += 1;
    await LIKES.put('count', n.toString());
    return new Response(n.toString());
  }
  return new Response(n.toString());
}
