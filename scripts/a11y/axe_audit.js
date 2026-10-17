// RNF-11: auditoría WCAG 2.1 AA (axe-core) de 22 páginas a 1280 y 360 px de ancho.
// Uso: node scripts/a11y/axe_audit.js <url_base> $(python scripts/a11y/seed_a11y.py | tail -1) > informe.jsonl
//      python scripts/a11y/report.py informe.jsonl      (requiere A11Y_PASSWORD, la misma de la siembra)
const { chromium } = require('playwright');
const fs = require('fs');
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const [base, sid, attempt, done, exam, learning] = process.argv.slice(2);
const PW = process.env.A11Y_PASSWORD;
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

async function audit(page, name, url) {
  const resp = await page.goto(base + url, { waitUntil: 'networkidle' });
  await page.addScriptTag({ content: AXE });
  const r = await page.evaluate(async (tags) => await axe.run(document, { runOnly: { type: 'tag', values: tags } }), TAGS);
  const v = r.violations.map(x => ({ id: x.id, impact: x.impact, n: x.nodes.length, help: x.help,
    targets: x.nodes.slice(0, 4).map(n => n.target.join(' ')),
    colors: x.id === 'color-contrast' ? [...new Set(x.nodes.map(n => { const d = (n.any[0] || {}).data || {}; return `${d.fgColor} on ${d.bgColor} = ${d.contrastRatio}`; }))] : undefined }));
  console.log(JSON.stringify({ page: name, status: resp.status(), url: page.url().replace(base, ''), violations: v }));
}

async function login(ctx, email) {
  const page = await ctx.newPage();
  await page.goto(base + '/login');
  await page.fill('input[name=email]', email);
  await page.fill('input[name=password]', PW);
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit], input[type=submit]')]);
  return page;
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  for (const width of [1280, 360]) {
    console.log(JSON.stringify({ viewport: width }));
    const ctx = () => browser.newContext({ viewport: { width, height: 800 } });
    const anon = await ctx();
    const p = await anon.newPage();
    for (const [n, u] of [['landing', '/'], ['login', '/login'], ['register', '/register'], ['forgot', '/forgot-password']])
      await audit(p, n, u);
    const sp = await login(await ctx(), 's@x.com');
    await audit(sp, 'student_join', '/student/join');
    await audit(sp, 'presentar_examen', `/exam/presentar/${sid}`);
    await audit(sp, 'profile', '/perfil');
    await audit(sp, 'resultados', `/resultados/${attempt}`);
    await audit(sp, 'learning_catalog', '/learning/student/catalog');
    await audit(sp, 'learning_view', `/learning/student/view/${learning}`);
    const tp = await login(await ctx(), 't@x.com');
    await audit(tp, 'instructor_dashboard', '/instructor/dashboard');
    await audit(tp, 'mis_preguntas', '/instructor/mis-preguntas');
    await audit(tp, 'lobby', `/instructor/lobby/${sid}`);
    await audit(tp, 'exam_library', '/instructor/exams');
    await audit(tp, 'exam_edit', `/instructor/exam/${exam}/edit`);
    await audit(tp, 'session_config', `/instructor/session/configure/${exam}`);
    await audit(tp, 'reports', '/instructor/reports');
    await audit(tp, 'session_report', `/instructor/session/${done}/report`);
    await audit(tp, 'learning_dashboard', '/learning/instructor/dashboard');
    await audit(tp, 'learning_builder', `/learning/instructor/builder/${learning}`);
    const ap = await login(await ctx(), 'a@x.com');
    await audit(ap, 'admin_dashboard', '/admin/dashboard');
    await audit(ap, 'admin_audit', '/admin/audit');
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
