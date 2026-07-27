import "@testing-library/jest-dom/vitest";

// jsdom no implementa estas dos y Radix las usa al abrir una hoja
if (!globalThis.matchMedia) {
  globalThis.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof globalThis.matchMedia;
}
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

import { beforeEach } from "vitest";

// cada prueba arranca como usuario nuevo: el onboarding persiste en localStorage
beforeEach(() => {
  globalThis.localStorage?.clear();
});
