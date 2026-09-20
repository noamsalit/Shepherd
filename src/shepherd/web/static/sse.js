// §12: one stream, and **no polling anywhere in the UI**.
//
// `EventSource` reconnects on its own and sends `Last-Event-ID` with the last
// `id:` it saw, which is the `seq` the server's ring issued — so the gap is
// replayed by the same contract the server already enforces. There is no timer
// in this file, and no route this page can call on a schedule: liveness is the
// stream, and a page that asks again is a page that is guessing.

const STREAM_PATH = "/api/events";

// The gap marker is an event like any other (principle 5): the page is told it
// fell behind rather than handed a history that looks complete.
export const GAP = "stream.gap";

export function connect(onEnvelope, onStatus) {
  const source = new EventSource(STREAM_PATH);

  source.addEventListener("open", () => onStatus("live"));

  // One `message` listener: the server sends no named frames precisely so that
  // an event type this build has never heard of still reaches the page.
  source.addEventListener("message", (message) => {
    let envelope;
    try {
      envelope = JSON.parse(message.data);
    } catch (error) {
      onStatus("unreadable");
      return;
    }
    onEnvelope(envelope);
  });

  // The browser retries by itself. Saying "reconnecting" is honest; retrying
  // here in parallel would be the poll §12 forbids.
  source.addEventListener("error", () => onStatus("reconnecting"));

  return source;
}
