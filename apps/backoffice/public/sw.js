/* Service worker del backoffice: sólo notificaciones push (no cachea la app). */
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'PEPITO OS', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'PEPITO OS';
  const options = {
    body: data.body || '',
    icon: '/mark.png',
    badge: '/mark.png',
    tag: data.case_id || undefined,
    renotify: !!data.case_id,
    requireInteraction: data.severity === 'urgent',
    data: { url: data.url || '/excepciones' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if ('focus' in c) {
          c.navigate(url);
          return c.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
