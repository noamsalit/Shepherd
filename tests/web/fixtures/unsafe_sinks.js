// Not shipped. Four shapes §13 forbids, one per line, so the scan must find
// exactly four — a scan that finds three has a hole.
export function render(row, host) {
  host.innerHTML = `<b>${row.title}</b>`;
  host.outerHTML = "<i>" + row.brief + "</i>";
  host.innerHTML = row.needs_you_reason;
  host.insertAdjacentHTML("beforeend", row.cwd);
}
