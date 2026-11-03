import assert from 'node:assert/strict';

const baseUrl = process.env.MOCK_BASE_URL ?? 'http://127.0.0.1:4010';
assert.ok(['localhost', '127.0.0.1', '::1', '[::1]'].includes(new URL(baseUrl).hostname),
  'This check must target a loopback mock server');
const accessToken = process.env.KOMMO_MOCK_TOKEN ?? 'local-kommo-token';
Object.assign(process.env, {
  KOMMO_BASE_URL: baseUrl,
  KOMMO_ACCESS_TOKEN: accessToken,
  WEBHOOK_SECRET: 'local-mock-smoke-secret',
  DATABASE_URL: 'postgresql://unused:unused@127.0.0.1/unused',
  GOOGLE_SHEETS_SPREADSHEET_ID: 'local-unused',
  GOOGLE_AUTH_MODE: 'service_account',
  GOOGLE_APPLICATION_CREDENTIALS: '/unused/local-credentials.json',
});

const health = await fetch(`${baseUrl}/health`).then(response => response.json());
assert.ok(health.providers.includes('kommo'));

const { KommoService } = await import('../../bestcredit4you-leadmanagement/src/integrations/kommo/kommo-service.ts');
const { KommoClient, validateKommoLeadForEnrollment, mapKommoLeadToEnrollment } =
  await import('../../bestcredit4you/payment/apps/api/src/integrations/kommo.ts');

const crm = new KommoService();
const payment = new KommoClient({ baseUrl, accessToken });
const seed = await payment.getLead(33579273);
assert.deepEqual(validateKommoLeadForEnrollment(seed), []);
assert.equal(mapKommoLeadToEnrollment(seed).initialAmountCents, 20000);
assert.equal((await crm.getPipelineStatuses(14229720))[1].id, 109869808);
assert.ok((await payment.listUsers()).length > 0);
assert.ok((await payment.listRoles()).length > 0);

const lead = await crm.createLead({ name: 'Client adapter smoke', pipelineId: 14229720, statusId: 109869808 });
const leadId = String(lead.id);
const contact = await crm.createContact({ name: 'Local Smoke', phone: '+12025550125', email: 'smoke@example.test' });
await crm.linkContactToLead({ leadId, contactId: contact.id });
await crm.updateLeadResponsibleUser(leadId, 13716683);
await crm.updateLeadContactsResponsibleUser(leadId, 13716683);
assert.equal((await crm.getLeadContactInfo(leadId)).email, 'smoke@example.test');
assert.equal(await payment.hasAssignedLead(13716683), true);
await crm.addLeadCommonNote({ leadId, text: 'Lead-management smoke' });
await payment.addLeadNote(lead.id, 'Payment smoke', 'local-smoke-note');
assert.equal((await crm.getLeadNotes(leadId)).length, 2);

const taskId = await payment.addLeadTask({ leadId: lead.id, text: 'Smoke task',
  completeTill: Math.floor(Date.now() / 1000) + 3600, requestId: 'local-smoke-task', responsibleUserId: 13716683 });
assert.equal((await crm.getLeadActiveTasks(leadId))[0].id, taskId);
await crm.updateTaskResponsibleUser(taskId, 12630411);
await payment.completeTask(taskId, 'Local smoke completed');
assert.deepEqual(await crm.getLeadActiveTasks(leadId), []);

const incoming = await crm.createIncomingLeadFromForm({
  contact: { name: 'Local Form', email: null, phone: '+12025550126' },
  lead: { name: 'Local form smoke' }, pipelineId: 14229720,
  requestId: 'form-smoke', sourceName: 'Local form', sourceUid: 'local-form',
});
await crm.acceptIncomingLead({ uid: incoming.uid, statusId: 109869808 });
assert.equal(await crm.getIncomingLeadByUid(incoming.uid), null);
console.log('PASS: both real Kommo clients, payment field mapping, links, notes, tasks, Unsorted');
