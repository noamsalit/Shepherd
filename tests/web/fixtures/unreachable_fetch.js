// An inert fixture for `test_frontend_unreachable_daemon.py`. **Nothing
// imports this file and nothing may**: it is read as text by the gate that
// proves the gate bites, in the shape `fixtures/unsafe_sinks.js` established.
//
// A comment that says fetch( and must not be counted.

const NOTE = "a string that says fetch( and has a } in it";

// Guarded: the rejection has somewhere to go.
async function guarded(path) {
  try {
    const response = await fetch(path);
    return await response.json();
  } catch (unreachable) {
    return null;
  }
}

// Unguarded: this is the defect, frozen. One line, and the gate must name it.
async function unguarded(path) {
  const response = await fetch(path);
  return await response.json();
}

export { NOTE, guarded, unguarded };
