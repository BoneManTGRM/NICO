// Private diagnostic retention: only authenticated ciphertext leaves the runner.
import {createCipheriv, publicEncrypt, constants, randomBytes} from 'node:crypto';
import {lstatSync, readFileSync, writeFileSync, realpathSync} from 'node:fs';
import {resolve} from 'node:path';

export function seal(raw, publicKey) {
  if (!Buffer.isBuffer(raw) || raw.length === 0 || raw.length > 128 * 1024 * 1024)
    throw new Error('diagnostic_bundle_bound');
  const key = randomBytes(32), iv = randomBytes(12);
  const wrapped = publicEncrypt({key: publicKey, padding: constants.RSA_PKCS1_OAEP_PADDING,
    oaepHash: 'sha256'}, key);
  const header = Buffer.alloc(8);
  header.write('NCP1'); header.writeUInt32BE(wrapped.length, 4);
  const cipher = createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(Buffer.concat([header, wrapped, iv]));
  const encrypted = Buffer.concat([cipher.update(raw), cipher.final()]);
  key.fill(0);
  return Buffer.concat([header, wrapped, iv, cipher.getAuthTag(), encrypted]);
}

if (process.argv[1] && realpathSync(process.argv[1]) === realpathSync(new URL(import.meta.url))) {
  const [input, output, keyPath, ...extra] = process.argv.slice(2);
  if (!input || !output || !keyPath || extra.length) throw new Error('diagnostic_seal_arguments');
  const stat = lstatSync(input);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size === 0 || stat.size > 128 * 1024 * 1024)
    throw new Error('diagnostic_bundle_bound');
  writeFileSync(resolve(output), seal(readFileSync(input), readFileSync(keyPath)), {flag: 'wx', mode: 0o600});
}
