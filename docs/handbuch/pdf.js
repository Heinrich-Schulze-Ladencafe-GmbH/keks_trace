const { chromium } = require('playwright');
(async () => {
  const [, , ein, aus] = process.argv;
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + ein); await p.waitForTimeout(800);
  await p.pdf({ path: aus, format: 'A4', printBackground: true, displayHeaderFooter: true,
    margin: { top: '18mm', bottom: '18mm', left: '17mm', right: '17mm' },
    headerTemplate: '<div></div>',
    footerTemplate: '<div style="font-family:Inter,Arial;font-size:8px;color:#5b6573;width:100%;padding:0 17mm;display:flex;justify-content:space-between"><span>Keks Trace · Testhandbuch für QS und Büro · Stand 4.11.2026</span><span>Seite <span class="pageNumber"></span> von <span class="totalPages"></span></span></div>' });
  await b.close();
})();
