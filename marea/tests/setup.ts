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

import { afterEach, beforeEach } from "vitest";
import { FLAGS } from "../src/lib/flags";

const DEFAULT_ENGINE = FLAGS.market_engine;

// cada prueba arranca como usuario nuevo: el onboarding persiste en localStorage
beforeEach(() => {
  globalThis.localStorage?.clear();
});

// y ninguna prueba se lleva el motor cambiado a la siguiente
afterEach(() => {
  FLAGS.market_engine = DEFAULT_ENGINE;
});
