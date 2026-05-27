/* Service worker simples — habilita instalação como PWA + cache do shell de login.
   Estratégia:
   - login.html, manifest.json, icons     → cache-first (precache no install)
   - dashboard.html e dados                → network-first (sempre tenta a rede;
                                            só cai pro cache se estiver offline)
*/
const CACHE_VERSION = "v294";   // bump quando precisar invalidar o cache do shell
const SHELL_CACHE   = `shell-${CACHE_VERSION}`;
const RUNTIME_CACHE = `runtime-${CACHE_VERSION}`;

const SHELL_ASSETS = [
  "login.html",
  "manifest.json",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-maskable-512.png",
  "fonts/aptos-regular.woff2",
  "fonts/aptos-semibold.woff2",
  "fonts/aptos-bold.woff2",
  "fonts/aptos-italic.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      cache.addAll(SHELL_ASSETS).catch(() => {
        // Se algum ícone faltar (deploy parcial), não derruba o SW.
      })
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
        .map((k) => caches.delete(k))
    );
    await self.clients.claim();
    // Avisa todos os clientes (abas/PWA abertos) que o SW atualizou,
    // pra eles recarregarem e pegarem o shell novo (fontes, CSS, etc.)
    const clients = await self.clients.matchAll({ type: "window" });
    for (const c of clients) c.postMessage({ type: "SW_UPDATED" });
  })());
});

function isShellAsset(url) {
  return SHELL_ASSETS.some((p) => url.pathname.endsWith("/" + p) || url.pathname === "/" + p);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Não cacheia chamadas de Firebase/Firestore/Auth/Google APIs.
  if (
    url.hostname.endsWith("googleapis.com") ||
    url.hostname.endsWith("gstatic.com") ||
    url.hostname.endsWith("firebaseio.com") ||
    url.hostname.endsWith("firebaseapp.com")
  ) {
    return; // browser default
  }

  // Mesma origem: shell vai pra cache-first; resto, network-first.
  if (url.origin === self.location.origin) {
    if (isShellAsset(url)) {
      event.respondWith(
        caches.match(req).then((cached) => cached || fetch(req))
      );
      return;
    }
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(RUNTIME_CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return resp;
        })
        .catch(() => caches.match(req))
    );
  }
});
