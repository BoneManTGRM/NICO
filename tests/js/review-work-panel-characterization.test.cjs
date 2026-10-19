'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const {test} = require('node:test');
const {harness, payload, characterize, ACTIONS, RUN} = require('./helpers/review-work-panel.cjs');
// Full-output fingerprints captured before edits on main 024a67b632967f2131e6899fcf0fa8a9dca4f6e3.
// Includes DOM markup and complete transport/callback observations, not selected labels.
const expected = require('./review-work-panel-characterization.json');

test('complete bilingual rendered output, requests and callbacks match pre-refactor main', async () => {
  const output = await characterize();
  assert.deepEqual(Object.keys(output), Object.keys(expected));
  for (const [name, value] of Object.entries(output)) {
    assert.equal(crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex'), expected[name], name);
  }
});

for (const locale of ['en', 'es-MX']) {
  test(`${locale}: all action payloads preserve exact human input and authorization`, async () => {
    for (const action of ACTIONS) {
      const h = harness(locale); await h.load(); h.action(action); h.fill();
      // All identity/action fields use the same whitespace-rich input, except enums.
      h.find(n => ['input', 'textarea'].includes(n.type) && !n.props.readOnly)
        .forEach(n => n.props.onChange({target: {value: ' human value \n evidence://two \n\n '}}));
      await h.submit();
      const calls = h.calls.filter(c => c.init.method === 'POST');
      assert.equal(calls.length, 1);
      const common = {action, reviewer: 'human value \n evidence://two', reviewer_role: 'human value \n evidence://two',
        review_authorized: true, authorization_confirmed: true};
      const value = common.reviewer;
      const details = {
        assign: {target_id: value, assignee: value, specialist_role: value},
        disposition_candidate: {candidate_id: value, disposition: 'confirmed', rationale: value, residual_risk: value,
          residual_risk_owner: value, escalation_resolution: value, escalation_owner: value},
        disposition_group: {cluster_id: value, disposition: 'confirmed', rationale: value, residual_risk: value,
          residual_risk_owner: value, escalation_resolution: value, escalation_owner: value},
        quality_control: {candidate_id: value, qc_outcome: 'agree', qc_note: value},
        request_evidence: {candidate_id: value, request_text: value, owner: value},
        resolve_evidence_request: {request_id: value, resolution_note: value, evidence_references: ['human value', 'evidence://two']},
        stakeholder_evidence: {statement: value, source_role: value, evidence_reference: value},
      };
      assert.deepEqual(JSON.parse(calls[0].init.body), {...common, ...details[action]});
      assert.equal(calls[0].url, `/api/nico/assessment/comprehensive-run/${RUN}/review-work`);
      assert.equal(calls[0].init.credentials, 'same-origin');
      assert.equal(calls[0].init.cache, 'no-store');
      assert.deepEqual(h.changed, [RUN]);
      assert.match(h.html(), /data-client-delivery-allowed="false"/);
    }
  });
  test(`${locale}: recorded QC and evidence selections preserve target and reset fields`, async () => {
    const h = harness(locale); await h.load(); h.action('quality_control'); h.fill();
    h.find(n => n.type === 'select')[1].props.onChange({target: {value: 'disagree'}});
    h.find(n => n.type === 'button' && String(n.props.children).includes(locale === 'en' ? 'Review QC' : 'Revisar control'))[0].props.onClick();
    assert.equal(h.find(n => n.type === 'select')[0].props.value, 'quality_control');
    assert.equal(h.find(n => n.type === 'select')[1].props.value, 'agree');
    assert.equal(h.find(n => n.type === 'textarea')[0].props.value, '');
    assert.equal(h.find(n => n.type === 'input')[3].props.value, 'candidate_a');
    h.action('resolve_evidence_request'); h.fill();
    h.find(n => n.type === 'button' && String(n.props.children).includes(locale === 'en' ? 'Resolve request' : 'Resolver solicitud'))[0].props.onClick();
    assert.equal(h.find(n => n.type === 'select')[0].props.value, 'resolve_evidence_request');
    assert.equal(h.find(n => n.type === 'input')[3].props.value, 'request_a');
    assert.ok(h.find(n => n.type === 'textarea').every(n => n.props.value === ''));
    assert.equal(h.calls.length, 1, 'selection must not submit');
  });
  test(`${locale}: language navigation retains run, other query and fragment`, () => {
    const h = harness(locale);
    h.find(n => n.type === 'button')[0].props.onClick();
    assert.deepEqual(h.navigations, [`/operations/reviewer-queue?run_id=${RUN}&lang=${locale === 'en' ? 'es-MX' : 'en'}&keep=yes#work`]);
  });
  for (const outcome of ['success', 'denied', 'ambiguous', 'reconciliationFailed']) {
    test(`${locale}: ${outcome} write preserves lock, reconciliation and uncertainty`, async () => {
      let release, posted = false;
      const h = harness(locale, call => {
        if (call.init.method === 'POST') {posted = true; return new Promise(resolve => {release = resolve;});}
        return Response.json(payload(posted && outcome === 'reconciliationFailed' ? {run_id: 'wrong_run'} : {}));
      });
      await h.load(); h.authorize();
      const pending = h.submit();
      assert.equal(h.find(n => n.type === 'button' && n.props.type === 'submit')[0].props.disabled, true);
      assert.equal(h.find(n => n.type === 'details').length, 0, 'stale projection is hidden during write');
      await h.submit();
      assert.equal(h.calls.filter(c => c.init.method === 'POST').length, 1);
      release(outcome === 'success' ? Response.json(payload()) : outcome === 'denied'
        ? Response.json({detail: 'private backend detail'}, {status: 403}) : new Response('{'));
      await pending;
      assert.equal(h.calls.length, ['ambiguous', 'reconciliationFailed'].includes(outcome) ? 3 : 2);
      assert.deepEqual(h.changed, ['success', 'ambiguous'].includes(outcome) ? [RUN] : []);
      assert.equal(h.find(n => n.type === 'button' && n.props.type === 'submit')[0].props.disabled,
        ['denied', 'reconciliationFailed'].includes(outcome));
      assert.equal(h.find(n => n.props.role === 'alert').length, outcome === 'success' ? 0 : 1);
      assert.ok(!h.html().includes('private backend detail'));
    });
  }
}
