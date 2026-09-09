'use client';

import {FormEvent, useEffect, useState} from 'react';
import {Attempt, IntakeInput, readAttempt, submitIntake} from './intake';
import styles from './provider-intake.module.css';

export function ProviderIntake() {
  const [es, setEs] = useState(false);
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [error, setError] = useState('');
  const [input, setInput] = useState<IntakeInput>({repository: '', expected_commit_sha: '', customer_id: '', project_id: '',
    authorized_by: '', authorization_scope: '', authorization_confirmed: false, report_language: 'en', execution_mode: 'internal_test',
    client_name: '', project_name: '', primary_technical_contact: '', access_method: ''});
  const t = (en: string, mx: string) => es ? mx : en;
  useEffect(() => {
    const spanish = new URLSearchParams(window.location.search).get('lang') === 'es-MX';
    setEs(spanish);
    setInput(value => ({...value, report_language: spanish ? 'es-MX' : 'en'}));
    try { setAttempt(readAttempt(sessionStorage)); setReady(true); }
    catch { setError('storage'); }
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || attempt || !ready) return;
    setBusy(true); setError('');
    try { setAttempt(await submitIntake(input, token, sessionStorage)); }
    catch (reason) { setError(reason instanceof Error && reason.message === 'admin_required' ? 'admin' : 'input'); }
    finally { setToken(''); setBusy(false); }
  }
  const field = (key: 'repository' | 'expected_commit_sha' | 'customer_id' | 'project_id' | 'authorized_by' | 'authorization_scope', en: string, mx: string, extra = {}) =>
    <label>{t(en, mx)}<input required name={key} value={input[key]} maxLength={key === 'authorization_scope' ? 500 : 160}
      onChange={event => setInput({...input, [key]: event.target.value})} {...extra}/></label>;
  return <main className={styles.main} lang={es ? 'es-MX' : 'en'}>
    <nav aria-label={t('Operations navigation', 'Navegación de operaciones')}>
      <a href="/operations">{t('Operations', 'Operaciones')}</a>{' · '}
      <a href={es ? '?lang=en' : '?lang=es-MX'} lang={es ? 'en' : 'es-MX'}>{es ? 'English' : 'Español de México'}</a>
    </nav>
    <h1>{t('GitHub operator intake', 'Ingreso de GitHub por operador')}</h1>
    <p>{t('Start a Comprehensive assessment of an explicitly authorized repository at an exact commit. NICO uses its existing server-held GitHub access; never enter a GitHub token here.',
      'Inicie una evaluación Comprehensive de un repositorio expresamente autorizado en un commit exacto. NICO usa el acceso a GitHub ya configurado en el servidor; no ingrese un token de GitHub aquí.')}</p>
    <p>{t('This action requires existing NICO admin authority. A specialist session alone does not grant it. Internal tests establish only the behavior actually demonstrated; approval and delivery remain separate actions.',
      'Esta acción requiere la autoridad de administración de NICO existente. Una sesión de especialista por sí sola no la otorga. Las pruebas internas solo demuestran el comportamiento observado; la aprobación y la entrega siguen siendo acciones separadas.')}</p>
    <p>{t('Use owner/name without a URL or clone suffix. Names containing .git are unavailable in this operator form because the existing repository resolver rewrites them.', 'Use propietario/nombre sin URL ni sufijo de clonación. Los nombres que contienen .git no están disponibles en este formulario porque el resolvedor de repositorios existente los modifica.')}</p>
    {!attempt && <form onSubmit={submit}>
      <fieldset disabled={!ready || busy}>
        <legend>{t('Repository authorization', 'Autorización del repositorio')}</legend>
        {field('repository', 'GitHub repository (owner/name)', 'Repositorio de GitHub (propietario/nombre)', {placeholder: 'owner/repository', autoCapitalize: 'none', spellCheck: false})}
        {field('expected_commit_sha', 'Expected commit (40 hexadecimal characters)', 'Commit esperado (40 caracteres hexadecimales)', {pattern: '[a-fA-F0-9]{40}', maxLength: 40, spellCheck: false})}
        {field('customer_id', 'Authorized customer ID', 'ID del cliente autorizado')}
        {field('project_id', 'Authorized project ID', 'ID del proyecto autorizado')}
        {field('authorized_by', 'Actual operator / authorization attribution', 'Operador real / atribución de autorización')}
        {field('authorization_scope', 'Authorized assessment scope', 'Alcance autorizado de la evaluación')}
        <p>{t('For final approval and protected delivery, complete all four engagement fields below. Identity-free internal diagnostics cannot be approved for delivery. Use clearly labeled synthetic information for software tests.',
          'Para la aprobación final y la entrega protegida, complete los cuatro campos del encargo. Los diagnósticos internos sin identidad no pueden aprobarse para entrega. Use información sintética claramente identificada en las pruebas de software.')}</p>
        {([
          ['client_name', 'Client name', 'Nombre del cliente', 180],
          ['project_name', 'Project name', 'Nombre del proyecto', 180],
          ['primary_technical_contact', 'Primary technical contact', 'Contacto técnico principal', 600],
          ['access_method', 'Access method', 'Método de acceso', 1200],
        ] as const).map(([key, en, mx, maxLength]) => <label key={key}>{t(en, mx)}
          <input name={key} value={input[key] || ''} maxLength={maxLength}
            onChange={event => setInput({...input, [key]: event.target.value})}/></label>)}
        <label>{t('Execution mode', 'Modo de ejecución')}<select value={input.execution_mode} onChange={e => setInput({...input, execution_mode: e.target.value as IntakeInput['execution_mode']})}>
          <option value="internal_test">{t('Internal test', 'Prueba interna')}</option>
          <option value="controlled_pilot">{t('Controlled pilot', 'Piloto controlado')}</option>
          <option value="production_engagement">{t('Production engagement', 'Evaluación en producción')}</option>
        </select></label>
        <label>{t('Report language', 'Idioma del informe')}<select value={input.report_language} onChange={e => setInput({...input, report_language: e.target.value as IntakeInput['report_language']})}>
          <option value="en">English</option><option value="es-MX">Español de México</option>
        </select></label>
        <label className={styles.check}><input type="checkbox" required checked={input.authorization_confirmed} onChange={e => setInput({...input, authorization_confirmed: e.target.checked})}/>
          {t('I have explicit authorization to assess this repository and commit within the stated scope.', 'Tengo autorización expresa para evaluar este repositorio y commit dentro del alcance indicado.')}</label>
        <label>{t('NICO admin credential', 'Credencial de administración de NICO')}<input type="password" required autoComplete="off" spellCheck={false} value={token} onChange={e => setToken(e.target.value)}/></label>
        <p>{t('The credential stays in memory for this submission and is then cleared. The non-secret attempt reference is retained in this tab to prevent accidental duplicate submissions.',
          'La credencial permanece en memoria durante este envío y después se borra. La referencia del intento, sin secretos, se conserva en esta pestaña para evitar envíos duplicados accidentales.')}</p>
        <button type="submit">{busy ? t('Submitting once…', 'Enviando una vez…') : t('Start authorized assessment', 'Iniciar evaluación autorizada')}</button>
      </fieldset>
    </form>}
    {error && <p role="alert">{error === 'admin' ? t('Existing NICO admin authority is required. No assessment was started by this rejected request.', 'Se requiere autoridad de administración de NICO existente. Esta solicitud rechazada no inició una evaluación.') : error === 'storage' ? t('The attempt record cannot be read. Intake is disabled; reconcile any existing request before continuing.', 'No se puede leer el registro del intento. El ingreso está deshabilitado; concilie cualquier solicitud existente antes de continuar.') : t('Check the required source and authorization fields. If an attempt reference is already retained, recover that request before continuing.', 'Revise los campos obligatorios de origen y autorización. Si ya existe una referencia de intento, recupere esa solicitud antes de continuar.')}</p>}
    {attempt && <section aria-live="polite">
      <h2>{attempt.state === 'received' ? t('Assessment receipt', 'Acuse de evaluación') : t('Intake requires reconciliation', 'El ingreso requiere conciliación')}</h2>
      <dl><dt>{t('Request ID', 'ID de solicitud')}</dt><dd>{attempt.requestId}</dd>
        <dt>{t('Submitted at', 'Fecha de envío')}</dt><dd>{attempt.submittedAt}</dd>
        <dt>{t('Repository', 'Repositorio')}</dt><dd>{attempt.repository}</dd>
        <dt>{t('Expected commit', 'Commit esperado')}</dt><dd>{attempt.commitSha}</dd>
        {attempt.httpStatus && <><dt>{t('HTTP response status', 'Estado de respuesta HTTP')}</dt><dd>{attempt.httpStatus}</dd></>}
        {attempt.failureCode && <><dt>{t('Retained error code', 'Código de error conservado')}</dt><dd>{attempt.failureCode}</dd></>}
        {attempt.correlationId && <><dt>{t('Operational correlation ID', 'ID de correlación de operaciones')}</dt><dd>{attempt.correlationId}</dd></>}
        {attempt.runId && <><dt>{t('Run ID', 'ID de ejecución')}</dt><dd>{attempt.runId}</dd><dt>{t('Receipt observed at', 'Acuse observado el')}</dt><dd>{attempt.receivedAt}</dd></>}
      </dl>
      {attempt.runId ? <a href={`${es ? '/es' : ''}/assessment?tier=comprehensive&run_id=${encodeURIComponent(attempt.runId)}`}>{t('Open the saved assessment', 'Abrir la evaluación guardada')}</a> :
        <p>{t('The request may have started an assessment. Do not resubmit or clear the attempt record. Use the request ID and timestamp with authorized operations to locate the run; a missing receipt proves neither success nor failure.',
          'La solicitud pudo haber iniciado una evaluación. No la reenvíe ni borre el registro del intento. Use el ID de solicitud y la fecha con operaciones autorizadas para localizar la ejecución; la falta de acuse no demuestra éxito ni fracaso.')}</p>}
      {attempt.state !== 'received' && attempt.runId && <p>{t('The returned run ID is retained only for recovery: the source receipt did not verify. Do not treat this run as the requested source until an authorized operator resolves the conflict.', 'El ID de ejecución devuelto se conserva solo para recuperación: el acuse de origen no se verificó. No considere que esta ejecución corresponde al origen solicitado hasta que un operador autorizado resuelva el conflicto.')}</p>}
      <p>{t('A receipt is not scanner completion, review, approval, or delivery authorization.', 'Un acuse no equivale a finalización de escáneres, revisión, aprobación ni autorización de entrega.')}</p>
    </section>}
  </main>;
}
