'use strict';
// Test-process guard only. No application or OS network configuration changes.
const net = require('node:net');
const tls = require('node:tls');
const mode = process.env.NICO_REVIEWER_PROOF_NETWORK;
if (!['build', 'server'].includes(mode)) throw new Error('proof network mode required');
const allowed = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);
function check(args) {
  let options = args[0];
  if (Array.isArray(options)) options = options[0]; // normalized Node connect tuple
  const host = typeof options === 'object' ? options.host || options.hostname : args[1];
  const port = typeof options === 'object' ? options.port : options;
  if (mode === 'build' && allowed.has(host) && Number(port) === 443) return;
  throw new Error('reviewer proof blocked outbound connection');
}
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) { check(args); return connect.apply(this, args); };
const tlsConnect = tls.connect;
tls.connect = function (...args) { check(args); return tlsConnect.apply(this, args); };
