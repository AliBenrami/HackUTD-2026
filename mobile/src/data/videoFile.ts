export function swingVideoFile(uri: string, contentType: string | null): { ext: string; type: string } {
  const path = uri.split('?')[0].toLowerCase();
  if (path.endsWith('.mov')) return { ext: 'mov', type: 'video/quicktime' };
  if (path.endsWith('.webm')) return { ext: 'webm', type: 'video/webm' };
  if (path.endsWith('.mp4') || path.endsWith('.m4v')) return { ext: 'mp4', type: 'video/mp4' };
  const header = (contentType ?? '').split(';')[0].trim().toLowerCase();
  if (header.includes('webm')) return { ext: 'webm', type: 'video/webm' };
  if (header.includes('quicktime')) return { ext: 'mov', type: 'video/quicktime' };
  return { ext: 'mp4', type: 'video/mp4' };
}

export function phoneCanPlayVideo(uri: string | null, platform: string): boolean {
  if (!uri || platform === 'web' || platform === 'android') return true;
  return !uri.split('?')[0].toLowerCase().endsWith('.webm');
}
