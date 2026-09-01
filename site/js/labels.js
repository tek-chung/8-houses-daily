/* Label-placement checks.

       node site/js/labels.js <inlined-page.html>

   Borough centroids sit close together where boroughs are small — Kensington and
   Hammersmith are neighbours, and Wandsworth, Lambeth and Southwark run in a
   line — so badges placed at centroids overlap and become unreadable.

   The live map exercises only the boroughs that currently carry notices, and
   they barely have to move, so it proves very little. These cases apply real
   pressure: badges on the same point, in tight lines, crammed into a corner,
   pressed against the sheet edge. Emits JSON for site/test_build.py to assert on.
*/
const { JSDOM } = require("jsdom");
const fs = require("fs");

const dom = new JSDOM(fs.readFileSync(process.argv[2], "utf8"), {
  runScripts: "dangerously", pretendToBeVisual: true,
  url: "https://example.org/all/",
});

setTimeout(() => {
  const w = dom.window;
  const overlaps = (a, b) =>
    Math.abs(a.x - b.x) < (a.w + b.w) / 2 &&
    Math.abs(a.y - b.y) < (a.h + b.h) / 2;

  const mk = (name, n, x, y) => ({ name, short: name, n, ax: x, ay: y });

  const cases = {
    "live map": (w.__MAP__ ? w.__MAP__.boroughs : []).map((b, i) =>
      mk(b.short, (i % 4) + 1, b.cx, b.cy)),
    "same point": [mk("Southwark", 3, 50, 50), mk("Lambeth", 2, 50, 50)],
    "five stacked": ["A", "B", "C", "D", "E"].map((s, i) => mk(s, i + 1, 50, 50)),
    "vertical line": Array.from({ length: 10 },
      (_, i) => mk("Borough" + i, i + 1, 50, 48 + i * 0.3)),
    "horizontal line": Array.from({ length: 12 },
      (_, i) => mk("Kensington", 9, 20 + i * 1.2, 50)),
    "corner crush": Array.from({ length: 20 },
      (_, i) => mk("Hammersmith", 9, 3 + (i % 4) * 0.5, 3 + Math.floor(i / 4) * 0.4)),
    "against the edge": Array.from({ length: 8 },
      (_, i) => mk("Tower Hamlets", 9, 99, 99 - i * 0.2)),
  };

  const out = {};
  for (const [label, items] of Object.entries(cases)) {
    if (!items.length) { out[label] = { skipped: true }; continue; }
    const p = w.placeBadges(items, null);
    let n = 0;
    for (let i = 0; i < p.length; i++)
      for (let j = i + 1; j < p.length; j++) if (overlaps(p[i], p[j])) n++;
    out[label] = {
      count: p.length,
      overlaps: n,
      terse: p.filter(x => x.terse).length,
      maxShift: +Math.max(...p.map(x => Math.hypot(x.x - x.ax, x.y - x.ay))).toFixed(1),
      offSheet: p.filter(x => x.x - x.w / 2 < -0.1 || x.x + x.w / 2 > 100.1
                           || x.y - x.h / 2 < -0.1 || x.y + x.h / 2 > 100.1).length,
    };
  }
  console.log(JSON.stringify(out, null, 1));
  process.exit(Object.values(out).some(r => r.overlaps || r.offSheet) ? 1 : 0);
}, 400);
