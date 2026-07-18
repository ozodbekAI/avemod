import React, { useState, useEffect, useRef } from 'react';

const NGROK_RE = /\.ngrok-free\.dev\//i;

const blobCache = new Map<string, string>();

/**
 * Drop-in <img> replacement that fetches images through `fetch()`
 * with the `ngrok-skip-browser-warning` header so that ngrok free
 * tier doesn't return its interstitial HTML page.
 *
 * For non-ngrok URLs it renders a plain <img>.
 */
const ProxiedImg = React.forwardRef<
  HTMLImageElement,
  React.ImgHTMLAttributes<HTMLImageElement>
>(({ src, alt, ...rest }, ref) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(() => {
    if (src && NGROK_RE.test(src)) return blobCache.get(src) || null;
    return null;
  });
  const [error, setError] = useState(false);

  const needsProxy = !!src && NGROK_RE.test(src);

  useEffect(() => {
    if (!needsProxy || !src) return;

    // Already cached
    if (blobCache.has(src)) {
      setBlobUrl(blobCache.get(src)!);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(src, {
          headers: { 'ngrok-skip-browser-warning': '1' },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('text/html')) throw new Error('Got HTML instead of image');
        const blob = await res.blob();
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob);
        blobCache.set(src, objectUrl);
        setBlobUrl(objectUrl);
        setError(false);
      } catch (e) {
        console.warn('[ProxiedImg] fetch failed:', src, e);
        if (!cancelled) setError(true);
      }
    })();

    return () => { cancelled = true; };
  }, [src, needsProxy]);

  if (!needsProxy) {
    return <img ref={ref} src={src} alt={alt ?? ''} {...rest} />;
  }

  if (error) {
    // Fallback to direct src
    return <img ref={ref} src={src} alt={alt ?? ''} {...rest} />;
  }

  // Show blob URL or nothing while loading
  return <img ref={ref} src={blobUrl || undefined} alt={alt ?? ''} {...rest} />;
});

ProxiedImg.displayName = 'ProxiedImg';
export default ProxiedImg;
