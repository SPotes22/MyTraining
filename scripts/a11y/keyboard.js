// RNF-11: recorre con Tab login, examen, resultados y perfil; avisa si algún elemento enfocado no muestra foco.
// Uso: node scripts/a11y/keyboard.js <url_base> <sala> <intento>   (A11Y_PASSWORD, la misma de la siembra)
const { chromium } = require('playwright');
const [base, sid, attempt] = process.argv.slice(2);
const PW = process.env.A11Y_PASSWORD;
(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const page = await (await browser.newContext()).newPage();
  // Login solo con teclado
  await page.goto(base + '/login');
  await page.focus('input[name=email]'); await page.keyboard.type('s@x.com');
  await page.keyboard.press('Tab');
  console.log('tras Tab desde el correo:', await page.evaluate(() => document.activeElement.name || document.activeElement.innerText));
  await page.keyboard.type(PW);
  await Promise.all([page.waitForNavigation(), page.keyboard.press('Enter')]);
  console.log('login con teclado ->', page.url().replace(base, ''));
  for (const url of [`/exam/presentar/${sid}`, `/resultados/${attempt}`, '/perfil']) {
    await page.goto(base + url, { waitUntil: 'networkidle' });
    const bad = [], seen = new Set();
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press('Tab');
      const info = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const cs = getComputedStyle(el);
        const visible = (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== 'none';
        return { tag: el.tagName, id: el.id, name: el.getAttribute('name'), text: (el.innerText || el.value || '').trim().slice(0, 30), visible };
      });
      if (!info) continue;
      const key = `${info.tag}#${info.id}${info.name}${info.text}`;
      if (seen.has(key)) { if (process.env.SHOW) console.log("  repetido:", key); break; }
      if (process.env.SHOW) console.log('  ', key);
      seen.add(key);
      if (!info.visible) bad.push(info);
    }
    console.log(url, 'enfocables:', seen.size, 'sin foco visible:', JSON.stringify(bad));
  }
  await browser.close();
})();
