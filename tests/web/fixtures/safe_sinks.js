// Not shipped. The two shapes §13 allows: a static literal, and a value that
// went through escapeHtml. Neither may be reported, or the gate is noise.
import { escapeHtml } from "../../../src/shepherd/web/static/escape.js";

export function render(row, host) {
  host.innerHTML = "<span class='chip'></span>";
  host.insertAdjacentHTML("beforeend", escapeHtml(String(row.title)));
}
