#!/usr/bin/env node
/**
 * binx - CLI to look up BIN info & reviews from binx.vip
 *
 * Usage:
 *   node binx.js 400895
 *   node binx.js 400895 402018 403306
 *   node binx.js --file bins.txt
 *   node binx.js 400895 --json output.json
 *
 * How it works:
 *   Opens Google Chrome (already installed) with a temporary remote debugging port,
 *   navigates to each BIN page, and extracts reviews. Chrome opens briefly so
 *   Cloudflare sees a real browser from your machine's IP.
 */

const { chromium } = require('playwright');
const Table = require('cli-table3');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execSync, spawn } = require('child_process');

// ─── Argument Parsing ──────────────────────────────────────────────────────

function parseArgs(args) {
    const bins = [];
    let jsonOut = null;
    let filePath = null;

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--json' && args[i + 1]) {
            jsonOut = args[++i];
        } else if (args[i] === '--file' && args[i + 1]) {
            filePath = args[++i];
        } else if (/^\d{4,8}$/.test(args[i])) {
            bins.push(args[i]);
        }
    }

    if (filePath) {
        const lines = fs.readFileSync(filePath, 'utf-8')
            .split('\n').map(l => l.trim()).filter(l => /^\d{4,8}$/.test(l));
        bins.push(...lines);
    }

    return { bins: [...new Set(bins)], jsonOut };
}

// ─── Scraping ──────────────────────────────────────────────────────────────

async function scrapeBIN(page, bin) {
    try {
        await page.goto(`https://binx.vip/bin/${bin}`, {
            waitUntil: 'domcontentloaded',
            timeout: 30000
        });

        // Wait out Cloudflare challenge if present
        for (let i = 0; i < 6; i++) {
            const title = await page.title();
            if (!title.includes('Just a moment') && !title.includes('Cloudflare')) break;
            await page.waitForTimeout(2000);
        }

        // 1. Scrape the metadata Info from the DOM (only need to do once)
        const info = await page.evaluate(() => {
            const result = {};
            document.querySelectorAll('dt').forEach(dt => {
                const dd = dt.nextElementSibling;
                if (dd && dd.tagName === 'DD') result[dt.innerText.trim()] = dd.innerText.trim();
            });
            return result;
        });

        // 2. Loop to scrape reviews across all pages
        const reviews = [];
        let hasNextPage = true;
        while (hasNextPage) {
            const pageReviews = await page.evaluate(() => {
                const results = [];
                document.querySelectorAll('.group\\/card').forEach(card => {
                    const user = card.querySelector('a.font-medium, [class*="font-medium"]')?.innerText?.trim() || 'Anonymous';
                    const rating = card.querySelector('[class*="tabular-nums"]')?.innerText?.trim() || '';
                    const text = card.querySelector('p')?.innerText?.trim() || '';
                    const timeEl = [...card.querySelectorAll('[class*="text-xs"]')].pop();
                    const time = timeEl?.innerText?.trim() || '';
                    if (text) results.push({ user, rating, text, time });
                });
                return results;
            });

            // Append unique reviews
            for (const r of pageReviews) {
                if (!reviews.some(x => x.text === r.text && x.user === r.user && x.time === r.time)) {
                    reviews.push(r);
                }
            }

            // Look for next page button
            const nextButton = page.locator('button[aria-label="Next page"]');
            if (await nextButton.count() > 0 && await nextButton.isVisible() && !(await nextButton.isDisabled())) {
                await nextButton.click();
                await page.waitForTimeout(1000); // Wait for the transition
            } else {
                hasNextPage = false;
            }
        }

        return { bin, info, reviews };
    } catch (err) {
        return { bin, info: {}, reviews: [], error: err.message.split('\n')[0] };
    }
}

// ─── Display ───────────────────────────────────────────────────────────────

function printBIN(result) {
    const { bin, info, reviews, error } = result;

    console.log('\n' + '═'.repeat(62));
    console.log(`  BIN: ${bin}  —  ${info.Bank || '(unknown bank)'}`);
    console.log('═'.repeat(62));

    if (error) {
        console.log(`  ⚠  ${error}`);
        return;
    }

    // Info row
    const parts = [info.Network, info.Type, info.Category, info.Country].filter(Boolean);
    if (parts.length) console.log('  ' + parts.join(' | '));

    // Reviews
    if (!reviews.length) {
        console.log('  (no reviews)\n');
        return;
    }

    const reviewTable = new Table({
        head: ['User', 'Rating', 'Review'],
        colWidths: [16, 8, 48],
        wordWrap: true,
        style: { head: ['yellow'] }
    });

    reviews.forEach(r => reviewTable.push([r.user, r.rating, r.text]));
    console.log(`\n  Reviews (${reviews.length}):`);
    console.log(reviewTable.toString());
}

// ─── Chrome Launcher ───────────────────────────────────────────────────────

const CDP_PORT = 9333;
const TEMP_PROFILE = path.join(os.tmpdir(), 'binx-chrome-session');

function launchChrome() {
    // Create temp profile dir
    fs.mkdirSync(TEMP_PROFILE, { recursive: true });

    const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
    const chromeArgs = [
        `--remote-debugging-port=${CDP_PORT}`,
        `--user-data-dir=${TEMP_PROFILE}`,
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-default-apps',
        '--window-size=1280,800',
    ];

    const proc = spawn(chromePath, chromeArgs, {
        detached: false,
        stdio: 'ignore',
    });

    return proc;
}

async function waitForCDP(retries = 20) {
    const http = require('http');
    for (let i = 0; i < retries; i++) {
        await new Promise(r => setTimeout(r, 500));
        try {
            await new Promise((resolve, reject) => {
                const req = http.get(`http://localhost:${CDP_PORT}/json/version`, res => {
                    res.resume();
                    resolve();
                });
                req.on('error', reject);
                req.setTimeout(500, () => { req.destroy(); reject(new Error('timeout')); });
            });
            return true;
        } catch {
            // not ready yet
        }
    }
    return false;
}

// ─── Main ──────────────────────────────────────────────────────────────────

async function main() {
    const { bins, jsonOut } = parseArgs(process.argv.slice(2));

    if (!bins.length) {
        console.log('\nUsage:');
        console.log('  node binx.js <BIN> [BIN2 BIN3 ...]');
        console.log('  node binx.js --file bins.txt');
        console.log('  node binx.js 400895 --json output.json\n');
        process.exit(0);
    }

    console.log(`\n🔍 Looking up ${bins.length} BIN(s) on binx.vip...\n`);

    // 1. Launch Chrome with remote debugging
    process.stdout.write('  Starting Chrome... ');
    const chromeProc = launchChrome();
    const ready = await waitForCDP();
    if (!ready) {
        console.error('✗ Could not connect to Chrome. Is Google Chrome installed at /Applications/?');
        chromeProc.kill();
        process.exit(1);
    }
    console.log('✓');

    // 2. Connect Playwright to that Chrome via CDP
    const browser = await chromium.connectOverCDP(`http://localhost:${CDP_PORT}`);
    const contexts = browser.contexts();
    const context = contexts.length ? contexts[0] : await browser.newContext();
    const page = await context.newPage();

    // 3. Scrape each BIN
    const results = [];
    for (const bin of bins) {
        process.stdout.write(`  Fetching ${bin}... `);
        const result = await scrapeBIN(page, bin);
        const count = result.reviews?.length ?? 0;
        console.log(result.error ? `✗ ${result.error}` : `✓ ${count} review(s)`);
        results.push(result);
    }

    // 4. Disconnect and kill Chrome
    await browser.close();
    chromeProc.kill('SIGTERM');
    // Clean up temp profile
    try { fs.rmSync(TEMP_PROFILE, { recursive: true, force: true }); } catch { }

    // 5. Print results
    results.forEach(printBIN);

    // 6. Optional JSON export
    if (jsonOut) {
        const out = {};
        results.forEach(r => { out[r.bin] = { info: r.info, reviews: r.reviews }; });
        fs.writeFileSync(jsonOut, JSON.stringify(out, null, 2));
        console.log(`\n✅ JSON saved to ${jsonOut}`);
    }

    console.log(`\n✅ Done — ${results.length} BIN(s) checked.\n`);
}

main().catch(err => {
    console.error('\nFatal:', err.message);
    process.exit(1);
});
