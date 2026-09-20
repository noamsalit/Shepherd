// §13: all work-item text, terminal output and transcript text is untrusted.
//
// The page fills slots with `textContent`, so today nothing calls this. It
// exists anyway, and it is exported, because the moment a sink appears the rule
// is "wrapped in escapeHtml(String(v)) — no exceptions for 'it's just a
// number'", and the wrong time to write the helper is the moment you need it.
//
// All five characters, including the apostrophe: a helper that escapes four is
// exactly the shape that makes `<b title='...'>` an injection point.

const REPLACEMENTS = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => REPLACEMENTS[character]);
}
