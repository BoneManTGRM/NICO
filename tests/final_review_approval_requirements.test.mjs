// Run with: node --experimental-strip-types tests/final_review_approval_requirements.test.mjs
import assert from 'node:assert/strict';
import {unmetApprovalRequirements} from '../apps/web/app/operations/final-review/finalReviewApprovalRequirements.ts';

const ready = {
  operatorReady: true,
  reviewer: 'Reviewer',
  reviewerRole: 'Cybersecurity specialist',
  pdfDigest: 'a'.repeat(64),
  downloadedDigest: 'a'.repeat(64),
  confirmed: true,
  reviewStatus: 'human_review_required',
};
let cases = 0;
for (let mask = 0; mask < 32; mask++) {
  const value = {
    ...ready,
    operatorReady: Boolean(mask & 1),
    reviewer: mask & 2 ? 'Reviewer' : '  ',
    reviewerRole: mask & 4 ? 'Cybersecurity specialist' : '',
    downloadedDigest: mask & 8 ? ready.pdfDigest : 'b'.repeat(64),
    confirmed: Boolean(mask & 16),
  };
  const before = JSON.stringify(value);
  const result = unmetApprovalRequirements(value);
  assert.equal(result.length === 0, mask === 31);
  assert.equal(result.includes('secureAccess'), !(mask & 1));
  assert.equal(result.includes('reviewer'), !(mask & 2));
  assert.equal(result.includes('reviewerRole'), !(mask & 4));
  assert.equal(result.includes('download'), !(mask & 8));
  assert.equal(result.includes('confirmation'), !(mask & 16));
  assert.equal(JSON.stringify(value), before);
  cases++;
}
for (const reviewStatus of ['rejected', 'request_more_evidence', ' REJECTED ']) {
  assert.deepEqual(unmetApprovalRequirements({...ready, reviewStatus}), ['locked']);
  cases++;
}
for (const pdfDigest of ['', 'bad', 'a'.repeat(63), 'a'.repeat(65)]) {
  assert.deepEqual(unmetApprovalRequirements({...ready, pdfDigest}), ['report']);
  cases++;
}
assert.deepEqual(unmetApprovalRequirements({...ready, pdfDigest: 'A'.repeat(64)}), []);
cases++;
assert.deepEqual(unmetApprovalRequirements({...ready, downloadedDigest: ''}), ['download']);
cases++;
assert.deepEqual(unmetApprovalRequirements({...ready, confirmed: false}), ['confirmation']);
cases++;
console.log(`${cases} approval requirement scenarios passed; no inputs mutated.`);
