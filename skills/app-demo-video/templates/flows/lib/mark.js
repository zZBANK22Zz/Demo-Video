// Tells demo/scripts/mark-server.py "this step just happened", so the editor can
// cut the recordings at real moments instead of guessed offsets.
// Env: MARK (name of the moment), MARK_PORT (optional, default 8787).
var port = typeof MARK_PORT !== 'undefined' ? MARK_PORT : '8787';
http.post('http://127.0.0.1:' + port + '/mark', { body: MARK });
