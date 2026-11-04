import { api } from '../api/client'
import { docLabel, WHO } from '../lib/docLabels'
import StatusChip from './StatusChip'
import './Inventory.css'

const EMPLOYMENT = [
  ['', 'Not stated yet'],
  ['salaried', 'Salaried'],
  ['self_employed', 'Self-employed'],
]

/** A type or person dropdown. Changing it saves at once: there is nothing to confirm, and it is
 * as easy to change back. */
function Pick({ label, value, options, onPick, disabled }) {
  return (
    <select
      className="select inv-pick"
      aria-label={label}
      value={value ?? ''}
      disabled={disabled}
      onChange={(e) => onPick(e.target.value)}
    >
      {options.map(([v, t]) => (
        <option key={v} value={v}>
          {t}
        </option>
      ))}
    </select>
  )
}

function FileRow({ f, people, docTypes, onPatch, disabled, showUsed = true }) {
  const types = [...new Set([...docTypes, 'unknown', f.doc_type])]
  const typeOptions = types.map((t) => [t, docLabel(t)])
  const personOptions = [['none', 'Choose a person…'], ...people.map((r) => [r, WHO[r]])]
  return (
    <tr>
      <td data-label="File" className="inv-file">
        <span className="mono">{f.name}</span>
        {f.warnings?.length > 0 && <span className="small muted"> · slightly blurry</span>}
      </td>
      <td data-label="Type">
        <Pick
          label={`Type of ${f.name}`}
          value={f.doc_type}
          options={typeOptions}
          disabled={disabled}
          onPick={(v) => onPatch(f.id, { doc_type: v })}
        />
        {f.type_changed && f.detected && f.detected !== f.doc_type && (
          <span className="small muted"> read as {docLabel(f.detected).toLowerCase()}</span>
        )}
      </td>
      <td data-label="Person">
        <Pick
          label={`Person for ${f.name}`}
          value={f.role ?? 'none'}
          options={personOptions}
          disabled={disabled}
          onPick={(v) => onPatch(f.id, { role: v })}
        />
      </td>
      {showUsed && (
        <td data-label="Used for" className="small muted">
          {f.feeds?.length ? `Fills the form: ${f.feeds.join(', ')}` : 'Checked against the form'}
        </td>
      )}
    </tr>
  )
}

function FileTable({ files, people, docTypes, onPatch, disabled, showUsed }) {
  return (
    <div className="inv-wrap">
      <table className="inv-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Type</th>
            <th>Person</th>
            {showUsed && <th>Used for</th>}
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <FileRow
              key={f.id}
              f={f}
              people={people}
              docTypes={docTypes}
              onPatch={onPatch}
              disabled={disabled}
              showUsed={showUsed}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * What arrived, per person: received, still missing (identity papers marked essential), extra;
 * then what needs a person or a type, what was not accepted and what was ignored as a repeat.
 * Employment type is a claim, so the officer states it here (or the applicant's request did);
 * until it is known the items that depend on it are listed apart and not counted as missing.
 */
export default function Inventory({ caseId, inventory, docTypes, editable, onChange, onError }) {
  const roles = inventory.people.map((p) => p.role)

  async function patch(docId, body) {
    try {
      onChange(await api.patch(`/cases/${caseId}/documents/${docId}`, body))
    } catch (e) {
      onError?.(e.message)
    }
  }
  async function setEmployment(role, value) {
    try {
      onChange(await api.put(`/cases/${caseId}/intake`, { employment: { [role]: value || null } }))
    } catch (e) {
      onError?.(e.message)
    }
  }
  const c = inventory.counts

  return (
    <div className="inventory" data-testid="inventory">
      <p className="inv-counts" aria-label="Summary">
        <strong>{c.received}</strong> received · <strong>{c.missing}</strong> still missing ·{' '}
        <strong>{c.extra}</strong> extra · <strong>{c.unassigned + c.unrecognised}</strong> need
        your attention · <strong>{c.rejected}</strong> not accepted ·{' '}
        <strong>{c.duplicates}</strong> repeats ignored
      </p>

      {inventory.people.map((p) => (
        <section key={p.role} className="card inv-person">
          <header className="inv-head">
            <h3>{WHO[p.role]}</h3>
            <label className="inv-emp">
              <span className="small muted">Employment (the applicant&apos;s statement)</span>
              <select
                className="select"
                aria-label={`Employment type of the ${WHO[p.role].toLowerCase()}`}
                value={p.employment ?? ''}
                disabled={!editable}
                onChange={(e) => setEmployment(p.role, e.target.value)}
              >
                {EMPLOYMENT.map(([v, t]) => (
                  <option key={v} value={v}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </header>

          <h4>Received</h4>
          {p.received.length ? (
            <FileTable
              files={p.received}
              people={roles}
              docTypes={docTypes}
              onPatch={patch}
              disabled={!editable}
              showUsed
            />
          ) : (
            <p className="muted">Nothing received for this person yet.</p>
          )}

          <h4>Still missing</h4>
          {p.missing.length ? (
            <ul className="inv-missing">
              {p.missing.map((m) => (
                <li key={m.type} className={m.essential ? 'essential' : ''}>
                  <span aria-hidden="true">!</span> {docLabel(m.type)}
                  {m.needed > 1 && (
                    <span className="muted">
                      {' '}
                      ({m.have} of {m.needed})
                    </span>
                  )}
                  {m.essential && <StatusChip tone="refer">Essential</StatusChip>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Nothing is missing for what is known so far.</p>
          )}

          {p.extra.length > 0 && (
            <>
              <h4>Extra (not needed for this loan)</h4>
              <FileTable
                files={p.extra}
                people={roles}
                docTypes={docTypes}
                onPatch={patch}
                disabled={!editable}
                showUsed={false}
              />
            </>
          )}
        </section>
      ))}

      {inventory.depends_on_employment.length > 0 && (
        <section className="card" aria-label="Waiting for employment type">
          <h3>Depends on employment type</h3>
          <p className="muted">
            These are asked for once the employment type is stated above. They are not counted as
            missing yet.
          </p>
          <ul className="inv-missing">
            {inventory.depends_on_employment.map((w) => (
              <li key={`${w.role}-${w.if_employment}-${w.type}`}>
                {WHO[w.role]} · if {w.if_employment.replace('_', '-')}: {docLabel(w.type)}
                {w.needed > 1 && ` (${w.needed})`}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(inventory.unassigned.length > 0 || inventory.unrecognised.length > 0) && (
        <section className="card" aria-label="Needs your attention">
          <h3>Needs your attention</h3>
          {inventory.unassigned.length > 0 && (
            <>
              <h4>Whose is it?</h4>
              <p className="muted">
                These were recognised but could not be matched to a person. Choose one.
              </p>
              <FileTable
                files={inventory.unassigned}
                people={roles}
                docTypes={docTypes}
                onPatch={patch}
                disabled={!editable}
                showUsed={false}
              />
            </>
          )}
          {inventory.unrecognised.length > 0 && (
            <>
              <h4>Not recognised</h4>
              <p className="muted">
                Nothing is guessed. If you can tell what it is (for example the back of an ID card),
                choose its type and person.
              </p>
              <FileTable
                files={inventory.unrecognised}
                people={roles}
                docTypes={docTypes}
                onPatch={patch}
                disabled={!editable}
                showUsed={false}
              />
            </>
          )}
        </section>
      )}

      {inventory.conflicts.length > 0 && (
        <section className="card" aria-label="Conflicting repeats">
          <h3>Same document, different amounts</h3>
          <ul>
            {inventory.conflicts.map((d) => (
              <li key={d.id}>
                <span className="mono">{d.name}</span> repeats <span className="mono">{d.of}</span>{' '}
                but the amounts differ. Both are kept and flagged for review.
              </li>
            ))}
          </ul>
        </section>
      )}

      {inventory.rejected.length > 0 && (
        <section className="card" aria-label="Not accepted">
          <h3>Not accepted</h3>
          <ul>
            {inventory.rejected.map((r) => (
              <li key={r.id}>
                <span className="mono">{r.name}</span>: {r.message || r.code}
              </li>
            ))}
          </ul>
        </section>
      )}

      {inventory.duplicates.length > 0 && (
        <section className="card" aria-label="Repeats ignored">
          <h3>Repeats, ignored</h3>
          <ul>
            {inventory.duplicates.map((d) => (
              <li key={d.id}>
                <span className="mono">{d.name}</span> repeats <span className="mono">{d.of}</span>.
                It was ignored and does not count towards the list.
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
