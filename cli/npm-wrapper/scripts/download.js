#!/usr/bin/env node
// postinstall: downloads the platform-specific clite binary from
// gaev-tech/clite GitHub Releases at the version pinned in package.json,
// verifies SHA256, drops it next to ./bin/clite so the npm `bin` shim works.
//
// Spec: architecture.md §15.9.6, implementation-plan.md §6.3.5.

'use strict';

const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');

const pkg = require('../package.json');
const REPO = 'gaev-tech/clite';
const VERSION = pkg.version; // bumped by release-workflow

const platformAssetMap = {
  'darwin-arm64': 'clite-darwin-arm64',
  'darwin-x64': 'clite-darwin-amd64',
  'linux-x64': 'clite-linux-amd64',
  'win32-x64': 'clite-windows-amd64.exe',
};

function detectAssetName() {
  const key = `${process.platform}-${process.arch}`;
  const asset = platformAssetMap[key];
  if (!asset) {
    throw new Error(
      `Unsupported platform: ${key}. ` +
      `Supported: ${Object.keys(platformAssetMap).join(', ')}.`,
    );
  }
  return asset;
}

function ghReleaseUrl(asset) {
  return `https://github.com/${REPO}/releases/download/v${VERSION}/${asset}`;
}

// Follows redirects (GitHub Releases → S3) up to 5 hops.
function httpsGet(url, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    const tryGet = (currentUrl, hop) => {
      https
        .get(currentUrl, (res) => {
          if (
            res.statusCode >= 300 &&
            res.statusCode < 400 &&
            res.headers.location
          ) {
            if (hop >= maxRedirects) {
              reject(new Error(`Too many redirects fetching ${url}`));
              return;
            }
            res.resume();
            tryGet(res.headers.location, hop + 1);
            return;
          }
          if (res.statusCode !== 200) {
            reject(
              new Error(
                `GET ${currentUrl} -> HTTP ${res.statusCode}`,
              ),
            );
            return;
          }
          resolve(res);
        })
        .on('error', reject);
    };
    tryGet(url, 0);
  });
}

async function streamToFile(res, dest) {
  await fs.promises.mkdir(path.dirname(dest), { recursive: true });
  await new Promise((resolve, reject) => {
    const out = fs.createWriteStream(dest, { mode: 0o755 });
    res.pipe(out);
    out.on('finish', resolve);
    out.on('error', reject);
    res.on('error', reject);
  });
}

async function sha256OfFile(file) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256');
    fs.createReadStream(file)
      .on('data', (chunk) => h.update(chunk))
      .on('end', () => resolve(h.digest('hex')))
      .on('error', reject);
  });
}

async function fetchExpectedSha(assetName) {
  const url = `${ghReleaseUrl(assetName)}.sha256`;
  const res = await httpsGet(url);
  let body = '';
  for await (const chunk of res) body += chunk.toString('utf8');
  // .sha256 file format from release-workflow:  "<hex>  <filename>\n"
  const match = body.trim().match(/^([0-9a-fA-F]{64})\b/);
  if (!match) {
    throw new Error(`Could not parse .sha256 from ${url}: ${body}`);
  }
  return match[1].toLowerCase();
}

async function main() {
  // Skip in CI for the wrapper repo itself (NPM uses postinstall = production).
  if (process.env.CLITE_SKIP_POSTINSTALL === '1') {
    console.log('[clite] CLITE_SKIP_POSTINSTALL=1 — skipping download.');
    return;
  }

  if (VERSION === '0.0.0') {
    console.log(
      '[clite] package version is 0.0.0 (dev) — skipping binary download.',
    );
    return;
  }

  const asset = detectAssetName();
  const url = ghReleaseUrl(asset);
  const binDir = path.join(__dirname, '..', 'bin');
  const isWindows = process.platform === 'win32';
  const finalName = isWindows ? 'clite.exe' : 'clite';
  const dest = path.join(binDir, finalName);

  console.log(`[clite] downloading ${url}`);
  const res = await httpsGet(url);
  await streamToFile(res, dest);

  console.log(`[clite] verifying SHA256`);
  const [expected, actual] = await Promise.all([
    fetchExpectedSha(asset),
    sha256OfFile(dest),
  ]);
  if (expected !== actual) {
    fs.unlinkSync(dest);
    throw new Error(
      `SHA256 mismatch for ${asset}: expected ${expected}, got ${actual}`,
    );
  }

  // On unix, ensure executable; npm preserves mode 0o755 above, but be defensive.
  if (!isWindows) {
    fs.chmodSync(dest, 0o755);
  }

  console.log(`[clite] installed v${VERSION} at ${dest}`);
}

main().catch((err) => {
  console.error(`[clite] postinstall failed: ${err.message}`);
  console.error(
    `[clite] you can still install via pipx/Homebrew/APT/GitHub Releases; ` +
    `see https://apitracker.ru/installation`,
  );
  process.exit(1);
});
