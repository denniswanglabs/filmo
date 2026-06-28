#!/usr/bin/env node
/**
 * Responsive audit — capture screenshots at key viewports.
 * Usage: node scripts/responsive-audit.mjs [iteration] [baseUrl]
 */
import { chromium, devices } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const iteration = process.argv[2] || '1'
const baseUrl = process.argv[3] || 'http://localhost:3001'
const outDir = path.join(process.cwd(), '.audit-screenshots', `iter-${iteration}`)

const VIEWPORTS = [
  { name: 'mobile-390', width: 390, height: 844, isMobile: true },
  { name: 'tablet-768', width: 768, height: 1024, isMobile: true },
  { name: 'laptop-1024', width: 1024, height: 768 },
  { name: 'laptop-1440', width: 1440, height: 900 },
]

async function capture(page, name) {
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: false })
}

async function scrollToProgress(page, progress) {
  await page.evaluate((p) => {
    const start = document.getElementById('start')
    if (!start) return
    const runway = Math.max(0, start.offsetHeight - window.innerHeight)
    window.scrollTo({ top: start.offsetTop + runway * p, behavior: 'instant' })
  }, progress)
}

async function scrollToId(page, id) {
  await page.evaluate((targetId) => {
    const el = document.getElementById(targetId)
    if (el) el.scrollIntoView({ behavior: 'instant', block: 'start' })
  }, id)
}

async function checkOverflow(page) {
  return page.evaluate(() => {
    const doc = document.documentElement
    const body = document.body
    const hasHScroll = doc.scrollWidth > doc.clientWidth + 1 || body.scrollWidth > body.clientWidth + 1
    const offenders = []
    document.querySelectorAll('*').forEach((el) => {
      const r = el.getBoundingClientRect()
      if (r.right > window.innerWidth + 2 || r.left < -2) {
        const tag = el.tagName.toLowerCase()
        const cls = (el.className && typeof el.className === 'string') ? el.className.slice(0, 80) : ''
        offenders.push({ tag, cls, right: Math.round(r.right), left: Math.round(r.left), w: window.innerWidth })
      }
    })
    return { hasHScroll, offenderCount: offenders.length, sample: offenders.slice(0, 8) }
  })
}

async function auditViewport(browser, vp) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: vp.isMobile ? 2 : 1,
    isMobile: !!vp.isMobile,
    hasTouch: !!vp.isMobile,
  })
  const page = await context.newPage()
  const prefix = vp.name
  const issues = []

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60000 })
  await page.waitForTimeout(2500)

  // Hero land
  await capture(page, `${prefix}-01-hero-land`)
  let overflow = await checkOverflow(page)
  if (overflow.hasHScroll) issues.push({ shot: 'hero-land', ...overflow })

  // Hero settled (composer visible ~68% progress on desktop; mobile uses flat hero)
  if (vp.width >= 768) {
    await scrollToProgress(page, 0.72)
    await page.waitForTimeout(800)
  }
  await capture(page, `${prefix}-02-hero-settled`)
  overflow = await checkOverflow(page)
  if (overflow.hasHScroll) issues.push({ shot: 'hero-settled', ...overflow })

  // Examples — scroll past hero runway first on desktop
  if (vp.width >= 768) {
    await scrollToProgress(page, 0.96)
    await page.waitForTimeout(400)
  }
  await scrollToId(page, 'examples')
  await page.waitForTimeout(700)
  await capture(page, `${prefix}-03-examples`)
  overflow = await checkOverflow(page)
  if (overflow.hasHScroll) issues.push({ shot: 'examples', ...overflow })

  // Editor demo
  await scrollToId(page, 'editor-demo')
  await page.waitForTimeout(500)
  await capture(page, `${prefix}-04-editor`)
  overflow = await checkOverflow(page)
  if (overflow.hasHScroll) issues.push({ shot: 'editor', ...overflow })

  // Lookbook
  await scrollToId(page, 'lookbook')
  await page.waitForTimeout(500)
  await capture(page, `${prefix}-05-lookbook`)

  // Footer
  await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' }))
  await page.waitForTimeout(400)
  await capture(page, `${prefix}-06-footer`)
  overflow = await checkOverflow(page)
  if (overflow.hasHScroll) issues.push({ shot: 'footer', ...overflow })

  // Mobile / tablet menu
  if (vp.width < 1024) {
    await page.goto(baseUrl, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1500)
    const menuBtn = page.locator('button[aria-label="Open menu"]')
    if (await menuBtn.count()) {
      await menuBtn.click()
      await page.waitForTimeout(400)
      await capture(page, `${prefix}-07-mobile-menu`)
    }
  }

  await context.close()
  return { viewport: vp.name, issues }
}

async function main() {
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch()
  const results = []

  for (const vp of VIEWPORTS) {
    console.log(`Auditing ${vp.name}...`)
    results.push(await auditViewport(browser, vp))
  }

  await browser.close()
  const report = { iteration, baseUrl, timestamp: new Date().toISOString(), results }
  await writeFile(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
