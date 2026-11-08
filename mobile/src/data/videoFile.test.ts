import { describe, expect, it } from 'vitest';
import { phoneCanPlayVideo, swingVideoFile } from './videoFile';

describe('swing video files', () => {
  it('keeps an iPhone camera recording as quicktime', () => {
    expect(swingVideoFile('file:///cache/Camera/swing.mov', 'video/webm')).toEqual({
      ext: 'mov',
      type: 'video/quicktime',
    });
  });

  it('keeps a browser recording as webm when the uri has no extension', () => {
    expect(swingVideoFile('blob:http://localhost/1', 'video/webm;codecs=vp8')).toEqual({
      ext: 'webm',
      type: 'video/webm',
    });
  });

  it('treats webm as unplayable on iPhone', () => {
    expect(phoneCanPlayVideo('https://cdn.example/swing.webm?token=1', 'ios')).toBe(false);
    expect(phoneCanPlayVideo('file:///cache/Camera/swing.mov', 'ios')).toBe(true);
  });
});
