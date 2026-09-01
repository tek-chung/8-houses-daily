/* Execute a built page and report anything the browser console would show.
   The first version missed the error entirely: jsdom routes uncaught script
   exceptions through a VirtualConsole "jsdomError", not through window.onerror,
   so a harness that only listens on window reports a clean run on a broken page. */
const { JSDOM, VirtualConsole } = require("jsdom");
const fs = require("fs");

const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push(`${e.type || "Error"}: ${e.message}`));
vc.on("error", (...a) => errors.push("console.error: " + a.join(" ")));

const dom = new JSDOM(fs.readFileSync(process.argv[2], "utf8"), {
  runScripts: "dangerously", pretendToBeVisual: true,
  url: "https://example.org" + (process.argv[3] || "/"), virtualConsole: vc,
});
dom.window.addEventListener("error", e =>
  errors.push("window.onerror: " + (e.message || "")));

setTimeout(() => {
  const d = dom.window.document;
  const report = {
    errors,
    boroughPaths: d.querySelectorAll("path.bo").length,
    litPaths: d.querySelectorAll("path.bo.lit").length,
    badges: d.querySelectorAll(".badge").length,
    chips: d.querySelectorAll("#tilemap .bt").length,
    chipsAreButtons: [...d.querySelectorAll("#tilemap .bt")]
      .every(b => b.tagName === "BUTTON"),
    chipsLabelled: [...d.querySelectorAll("#tilemap .bt")]
      .every(b => b.getAttribute("aria-label") && b.title),
    textInsideSvg: d.querySelectorAll("#boroughs text").length,
    classifieds: d.querySelectorAll(".ad").length,
    count: d.querySelector("#cnum") ? d.querySelector("#cnum").textContent : null,
    filledSlots: d.querySelectorAll(".slot.filled").length,
    plates: d.querySelectorAll(".plate").length,
  };
  console.log(JSON.stringify(report, null, 2));
  process.exit(errors.length ? 1 : 0);
}, 400);
