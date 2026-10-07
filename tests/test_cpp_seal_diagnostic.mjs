import {generateKeyPairSync, privateDecrypt, createDecipheriv, constants} from 'node:crypto';
import assert from 'node:assert/strict';
import {seal} from '../scripts/cpp_seal_diagnostic.mjs';

const {publicKey, privateKey} = generateKeyPairSync('rsa', {modulusLength: 3072});
const raw = Buffer.from('owned private evidence');
function unseal(bytes, key = privateKey) {
  assert.equal(bytes.subarray(0, 4).toString(), 'NCP1');
  const length = bytes.readUInt32BE(4), end = 8 + length;
  const symmetric = privateDecrypt({key, padding: constants.RSA_PKCS1_OAEP_PADDING,
    oaepHash: 'sha256'}, bytes.subarray(8, end));
  const cipher = createDecipheriv('aes-256-gcm', symmetric, bytes.subarray(end, end + 12));
  cipher.setAAD(bytes.subarray(0, end + 12));
  cipher.setAuthTag(bytes.subarray(end + 12, end + 28));
  return Buffer.concat([cipher.update(bytes.subarray(end + 28)), cipher.final()]);
}
const one = seal(raw, publicKey), two = seal(raw, publicKey);
assert.deepEqual(unseal(one), raw);
assert.notDeepEqual(one, two);
assert.equal(one.includes(raw), false);
for (const index of [12, one.length - 1, 8 + one.readUInt32BE(4) + 15]) {
  const changed = Buffer.from(one); changed[index] ^= 1;
  assert.throws(() => unseal(changed));
}
const other = generateKeyPairSync('rsa', {modulusLength: 3072});
assert.throws(() => unseal(one, other.privateKey));
assert.throws(() => seal(Buffer.alloc(0), publicKey));
console.log('Sealed retention positive, tamper, wrong-recipient, and empty-input controls passed.');
