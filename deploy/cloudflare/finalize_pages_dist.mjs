#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from 'node:fs';
import { extname, join, relative, resolve, sep } from 'node:path';

const rootArg = process.argv[2];
const commit = process.argv[3];
if (!rootArg || !commit || !/^[0-9a-f]{40}$/.test(commit)) {
  console.error('usage: finalize_pages_dist.mjs <dist-root> <40-hex-commit>');
  process.exit(2);
}

const root = realpathSync(resolve(rootArg));
const manifestName = 'site_release_manifest.json';
const maxFileBytes = 25 * 1024 * 1024;
const maxFiles = 20_000;
const allowedExtensions = new Set(['.css', '.csv', '.html', '.ico', '.js', '.json', '.png', '.svg', '.webp', '.woff2']);
const textExtensions = new Set(['.css', '.csv', '.html', '.js', '.json', '.svg']);
const forbiddenText = [
  /(^|[^A-Za-z0-9])\/Users\//m,
  /(^|[^A-Za-z0-9])\/home\//m,
  /\/mnt\//,
  /\/private\/tmp\//,
  /\.spot-runs/,
  /\b(?:tcedirector|tcefold)\b/,
  /(?:sk-|ghp_|xoxb-)[A-Za-z0-9_-]{16,}/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
];

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function walk(dir, output = []) {
  for (const name of readdirSync(dir).sort()) {
    const absolute = join(dir, name);
    const stat = lstatSync(absolute);
    const rel = relative(root, absolute).split(sep).join('/');
    if (stat.isSymbolicLink()) throw new Error(`symlink refused: ${rel}`);
    if (stat.isDirectory()) {
      if (name.startsWith('.')) throw new Error(`dot-directory refused: ${rel}`);
      walk(absolute, output);
    } else if (stat.isFile()) {
      output.push({ absolute, path: rel, size: stat.size });
    } else {
      throw new Error(`non-regular path refused: ${rel}`);
    }
  }
  return output;
}

function validate(files) {
  if (files.length > maxFiles) throw new Error(`Pages file count ${files.length} exceeds ${maxFiles}`);
  for (const file of files) {
    if (file.path === manifestName) continue;
    if (file.path.split('/').some((part) => part.startsWith('.'))) throw new Error(`dot-path refused: ${file.path}`);
    if (file.size > maxFileBytes) throw new Error(`Pages 25 MiB limit exceeded: ${file.path} (${file.size} bytes)`);
    const extension = extname(file.path).toLowerCase();
    if (file.path !== '_headers' && !allowedExtensions.has(extension)) {
      throw new Error(`unapproved served extension: ${file.path}`);
    }
    if (textExtensions.has(extension) || file.path === '_headers') {
      const content = readFileSync(file.absolute, 'utf8');
      for (const pattern of forbiddenText) {
        if (pattern.test(content)) throw new Error(`private/local token refused in served bytes: ${file.path}`);
      }
    }
  }
}

mkdirSync(root, { recursive: true });
let files = walk(root).filter((file) => file.path !== manifestName);
validate(files);
const inventory = files.map((file) => ({ path: file.path, sha256: sha256(file.absolute), bytes: file.size }));
const manifest = {
  schema: 'spot.pages_release.v1',
  source_commit: commit,
  accounting: 'site_release_manifest.json is self-excluded; Cloudflare deployment binds the complete output directory',
  files: inventory,
};
writeFileSync(join(root, manifestName), `${JSON.stringify(manifest, null, 2)}\n`);
files = walk(root);
validate(files);
const largest = files.reduce((current, file) => file.size > current.size ? file : current, { path: '', size: 0 });
const total = files.reduce((sum, file) => sum + file.size, 0);
console.log(`Pages distribution verified: ${files.length} files, ${total} bytes; largest ${largest.path} (${largest.size} bytes)`);
