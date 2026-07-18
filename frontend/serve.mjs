import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, normalize, resolve, sep } from "node:path";
import { Readable } from "node:stream";

import app from "./dist/server/server.js";

const host = process.env.HOST || "127.0.0.1";
const port = Number(process.env.PORT || 3016);
const root = resolve(process.cwd(), "dist/client");

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function assetPath(url) {
  const pathname = decodeURIComponent(new URL(url, "http://localhost").pathname);
  const cleaned = normalize(pathname.replace(/^\/+/, ""));
  const file = resolve(root, cleaned);
  return file === root || file.startsWith(`${root}${sep}`) ? file : null;
}

async function serveAsset(req, res) {
  const file = assetPath(req.url || "/");
  if (!file || !existsSync(file)) return false;

  const info = await stat(file);
  if (!info.isFile()) return false;

  res.writeHead(200, {
    "content-length": info.size,
    "content-type": mimeTypes[extname(file)] || "application/octet-stream",
    "cache-control": file.includes(`${sep}assets${sep}`)
      ? "public, max-age=31536000, immutable"
      : "public, max-age=300",
  });
  createReadStream(file).pipe(res);
  return true;
}

function requestUrl(req) {
  const protocol = req.headers["x-forwarded-proto"] || "http";
  const hostHeader = req.headers.host || `${host}:${port}`;
  return `${protocol}://${hostHeader}${req.url || "/"}`;
}

function toRequest(req) {
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) {
    if (Array.isArray(value)) {
      for (const item of value) headers.append(key, item);
    } else if (value !== undefined) {
      headers.set(key, value);
    }
  }

  return new Request(requestUrl(req), {
    method: req.method,
    headers,
    body: req.method === "GET" || req.method === "HEAD" ? undefined : Readable.toWeb(req),
    duplex: req.method === "GET" || req.method === "HEAD" ? undefined : "half",
  });
}

async function writeResponse(res, response) {
  res.writeHead(response.status, Object.fromEntries(response.headers.entries()));
  if (!response.body) {
    res.end();
    return;
  }
  Readable.fromWeb(response.body).pipe(res);
}

createServer(async (req, res) => {
  try {
    if (req.method === "GET" || req.method === "HEAD") {
      if (await serveAsset(req, res)) return;
    }
    const response = await app.fetch(toRequest(req), {}, {});
    await writeResponse(res, response);
  } catch (error) {
    console.error(error);
    res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    res.end("frontend server error\n");
  }
}).listen(port, host, () => {
  console.log(`finance frontend listening on http://${host}:${port}`);
});
