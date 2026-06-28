import path from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Pin ALL bundler roots to `web/`.
 *
 * Without this, Next walks up the filesystem for lockfiles and often picks
 * `~/package-lock.json` (outside the repo). That mis-resolves modules, corrupts
 * webpack chunks, and triggers vendor-chunks ENOENT + `.call` runtime errors.
 */
const webRoot = path.dirname(fileURLToPath(import.meta.url))

/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: webRoot,
  turbopack: {
    root: webRoot,
  },
  webpack: (config) => {
    config.context = webRoot
    config.resolve = config.resolve ?? {}
    config.resolve.modules = [path.join(webRoot, 'node_modules'), 'node_modules']
    return config
  },
}

export default nextConfig
