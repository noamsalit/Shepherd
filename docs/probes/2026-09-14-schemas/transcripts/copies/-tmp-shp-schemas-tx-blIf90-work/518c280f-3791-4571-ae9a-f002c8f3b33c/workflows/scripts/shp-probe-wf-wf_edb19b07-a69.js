export const meta = { name: 'shp-probe-wf', description: 'schema probe', phases: [ { title: 'Ping' } ] }
phase('Ping')
const r = await agent('Reply with exactly the word PONG.', { label: 'ping' })
return r