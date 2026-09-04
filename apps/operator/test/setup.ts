import 'fake-indexeddb/auto';

// Node 20+ expone WebCrypto en globalThis.crypto; navigator.onLine no existe en node.
if (typeof (globalThis as { navigator?: unknown }).navigator === 'undefined') {
  Object.defineProperty(globalThis, 'navigator', { value: { onLine: true }, configurable: true });
}
