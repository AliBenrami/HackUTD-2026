import { afterEach, describe, expect, it } from 'vitest';
import { randomUUID } from './id';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('randomUUID', () => {
  const original = globalThis.crypto;

  afterEach(() => {
    Object.defineProperty(globalThis, 'crypto', { value: original, configurable: true });
  });

  it('returns a uuid when the runtime has no crypto.randomUUID', () => {
    Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
    expect(randomUUID()).toMatch(uuid);
  });
});
