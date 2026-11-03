import { useEffect, useState } from 'react'
import { useSession } from '../App'
import AgentCard from '../components/AgentCard'
import Callout from '../components/Callout'
import HelpSection from '../components/HelpSection'
import Icon from '../components/Icons'
import ScoreBar from '../components/ScoreBar'
import StatusChip from '../components/StatusChip'
import { JOURNEY } from '../lib/journey'
import './HelpPage.css'

const AGENTS = [
  [
    'Supervisor',
    'No points',
    'Opens the case, builds the list of required documents and flags what is missing.',
    'A missing identity document stops the run as a fix-type stop. Other missing documents are flagged and the run goes on.',
  ],
  [
    'Extraction',
    'Documents 15',
    'Reads each document and pulls out the fields, marking any it is unsure of.',
    'Low-confidence fields are shown to you, never guessed. Totals and dates are checked by code.',
  ],
  [
    'KYC',
    'KYC 20',
    'Checks identity and address documents against what was entered on the application.',
    'Every applicant and co-applicant goes through the same checks.',
  ],
  [
    'Policy',
    'Policy fit 10',
    'Finds the policy clauses that apply to this loan type and checks the case against them.',
    'Runs at the same time as Risk. Every claim names the clause it relies on.',
  ],
  [
    'Risk',
    'Income and FOIR 30 · Credit 25',
    'Looks at income, FOIR (the share of income that goes to repayments) and credit behaviour.',
    'The numbers come from code. The model only writes the explanation.',
  ],
  [
    'Decision',
    'Adds it up',
    'Puts the findings together into a score, a recommendation and a short report.',
    'Hard rules override the band. The recommendation is never final until you confirm it.',
  ],
]

const OFFICER = [
  ['start', 'Create a case', 'plus'],
  ['stages', 'The five stages', 'cases'],
  ['report', 'Reading the report', 'precedent'],
  ['confirm', 'Confirm or override', 'shield'],
  ['contact', 'Contact the customer', 'mail'],
  ['problem', 'Report a problem', 'flag'],
  ['agents', 'What each agent does', 'users'],
  ['score', 'Score weights and bands', 'home'],
]
const ADMIN = [
  ['users', 'Add and disable users', 'users'],
  ['reset', 'Reset a password', 'shield'],
  ['issues', 'Read issue reports', 'flag'],
  ['precedents', 'The precedent queue', 'precedent'],
]

const AUDITOR = [
  ['aud-what', 'What you can see', 'eye'],
  ['aud-cases', 'Read a case', 'cases'],
  ['aud-data', 'Overview, log and messages', 'chart'],
  ['aud-limits', 'What you cannot do', 'shield'],
]

function AuditorGuide() {
  return (
    <>
      <HelpSection id="aud-what" icon="eye" title="What you can see">
        <p>
          The auditor account is <strong>read-only</strong>. It reads the system&apos;s own records:
          every officer&apos;s cases with their scores, decisions and overrides, the audit log,
          precedents, the staff list, the messages officers sent to customers, and charts built from
          those records.
        </p>
        <Callout tone="info" title="Masked data, no documents">
          Applicant names, PAN, phone, email and addresses are masked, and the original document
          files are never shown to this role.
        </Callout>
      </HelpSection>

      <HelpSection id="aud-cases" icon="cases" title="Read a case">
        <ol className="help-steps">
          <li>Open Cases. The list shows every officer&apos;s cases; search by case number.</li>
          <li>
            Open a case to see the stepper, the extracted fields, the report and its audit trail.
          </li>
          <li>
            The Read-only badge is shown, and there are no buttons to confirm, override, upload or
            send.
          </li>
        </ol>
      </HelpSection>

      <HelpSection id="aud-data" icon="chart" title="Overview, log and messages">
        <p>
          Overview shows counts and charts. Audit log lists who did what and when, and can be
          filtered by action. Messages shows contact requests officers sent, with the recipient
          masked. Users and Precedents are lists only.
        </p>
      </HelpSection>

      <HelpSection id="aud-limits" icon="shield" title="What you cannot do">
        <p>
          You cannot change anything. Every action that writes data answers “not allowed” for this
          account, on the server as well as in the screen. There is exactly one auditor, created
          from the command line by whoever runs the system; an admin cannot create, disable or reset
          it.
        </p>
      </HelpSection>
    </>
  )
}

function OfficerGuide() {
  return (
    <>
      <HelpSection id="start" icon="plus" title="Create a case and upload documents">
        <ol className="help-steps">
          <li>Choose New case, pick the loan type and fill in the application form.</li>
          <li>
            For a home loan you may add a co-applicant; for an education loan one is required.
          </li>
          <li>
            Select Create case and add documents, then upload each file with its document kind.
          </li>
          <li>When every file is in, start the assessment.</li>
        </ol>
        <Callout tone="info" title="Synthetic data only">
          Never enter real customer information. This is a sample bank.
        </Callout>
      </HelpSection>

      <HelpSection id="stages" icon="cases" title="The five stages">
        <p className="muted">The stepper at the top of a case shows where it is.</p>
        <ol className="help-steps">
          {JOURNEY.map((s) => (
            <li key={s.id}>
              <span>
                <strong>{s.label}.</strong> {s.detail}.
              </span>
            </li>
          ))}
        </ol>
      </HelpSection>

      <HelpSection id="report" icon="precedent" title="Reading the report">
        <ul>
          <li>Each stage has a card with its points and its findings.</li>
          <li>
            Every finding carries a rule ID. Policy findings also name the clause they rely on.
          </li>
          <li>Conditions are things to settle before the file can move ahead.</li>
        </ul>
        <p>
          <StatusChip tone="unverified">Unverified</StatusChip>
        </p>
        <Callout tone="warn" title="Unverified is not a pass">
          A check could not be completed, even after one retry. It is passed to you to look at
          yourself.
        </Callout>
        <p>
          <StatusChip tone="stopped">Stopped: needs correction</StatusChip>
        </p>
        <p>
          A stopped case has a short report. A fix-type stop asks for a correction and can be
          resumed; an eligibility-type stop recommends reject.
        </p>
      </HelpSection>

      <HelpSection id="confirm" icon="shield" title="Confirm or override">
        <ol className="help-steps">
          <li>Read the report and the recommendation.</li>
          <li>Choose Confirm recommendation, or Override with a different decision.</li>
          <li>A second dialog opens. Nothing is recorded until you click again there.</li>
          <li>An override needs a written reason.</li>
        </ol>
        <Callout tone="ok" title="You decide every case">
          The system only recommends, whatever the score.
        </Callout>
      </HelpSection>

      <HelpSection id="contact" icon="mail" title="Contact the customer">
        <ul>
          <li>
            After you confirm or override a case, or when a run stops, open the case and choose
            Write a message.
          </li>
          <li>
            Pick a template or write your own, then choose Review. A check runs on the server.
          </li>
          <li>
            The message never carries a name, number, amount, score, result, missing item or reason.
            If the check blocks it, the reason is shown and you can edit and review again.
          </li>
          <li>
            The last screen shows the exact text. Nothing is sent until you click Yes, send there.
          </li>
          <li>
            Your name, email and phone, and the fraud warning, are added automatically. Staff never
            ask a customer for an OTP, PIN or password.
          </li>
          <li>
            Sent items lists your messages. A failed one can be sent again. Messages are printed in
            the backend terminal in this version; no real email is sent.
          </li>
        </ul>
      </HelpSection>

      <HelpSection id="problem" icon="flag" title="Report a problem">
        <p>
          Use Report a problem in the menu to tell the admin about something wrong. Add a case
          reference if it helps. Never paste personal data: a report with a PAN, Aadhaar, phone,
          account number or email is refused. You can see the status of your own reports there.
        </p>
      </HelpSection>

      <HelpSection id="agents" icon="users" title="What each agent does">
        <div className="agent-grid">
          {AGENTS.map(([name, points, does, more]) => (
            <AgentCard key={name} name={name} points={points} does={does} more={more} />
          ))}
        </div>
        <p className="muted small">
          The score itself is worked out by code, never by a model. Models only read text and write
          explanations.
        </p>
      </HelpSection>

      <HelpSection id="score" icon="home" title="Score weights and bands">
        <ScoreBar />
        <p className="muted small">A hard rule overrides the band.</p>
      </HelpSection>
    </>
  )
}

function AdminGuide() {
  return (
    <>
      <HelpSection id="users" icon="users" title="Add and disable users">
        <ul>
          <li>Open Users and choose the option to add a user. Give a name, an email and a role.</li>
          <li>
            Creating an admin shows a red warning and asks you to confirm. The read-only auditor is
            not made here and cannot be disabled or reset from this screen.
          </li>
          <li>Disable an account to stop it signing in. You cannot disable your own account.</li>
          <li>Enable a disabled account to let that person sign in again.</li>
        </ul>
      </HelpSection>

      <HelpSection id="reset" icon="shield" title="Reset a password">
        <ol className="help-flow">
          <li>
            <strong>1. Users</strong>
            <span className="muted">Find the person.</span>
          </li>
          <li>
            <strong>2. Reset password</strong>
            <span className="muted">Confirm in the dialog.</span>
          </li>
          <li>
            <strong>3. Copy</strong>
            <span className="muted">Pass it on by your own channel.</span>
          </li>
        </ol>
        <Callout tone="warn" title="Shown once">
          A temporary password is made and shown once, on the next screen. It cannot be shown again.
          A locked account unlocks by itself after a while.
        </Callout>
      </HelpSection>

      <HelpSection id="issues" icon="flag" title="Read issue reports">
        <p>
          Open Issues to see problems reported by officers. Opening a report marks it read, and Mark
          as closed finishes it. Reports hold only a case reference, a category and short text; they
          never include case data. Home shows how many are open, and how many customer messages were
          sent or failed, as counts only.
        </p>
      </HelpSection>

      <HelpSection id="precedents" icon="precedent" title="The precedent queue">
        <p>
          When an officer overrides a recommendation, three gates decide whether it can guide later
          cases.
        </p>
        <ol className="help-flow">
          <li>
            <strong>Officer</strong>
            <span className="muted">Overrides with a written reason.</span>
          </li>
          <li>
            <strong>Code check</strong>
            <span className="muted">
              A summary that breaks a hard rule is held and never reaches you.
            </span>
          </li>
          <li>
            <strong>You</strong>
            <span className="muted">
              Read the card in Precedents, set a valid-until date, confirm.
            </span>
          </li>
        </ol>
        <p>
          Approved precedents help only borderline cases of the same loan type and never over a hard
          rule. Use the Approve… button (or reject) on the card.
        </p>
        <Callout tone="info" title="No case data for admins">
          Admins have no access to case data. Click an officer&apos;s name in Users to see their
          counts and case numbers only.
        </Callout>
      </HelpSection>
    </>
  )
}

/** The "On this page" menu: highlights the section on screen. */
function useActiveSection(ids) {
  const [active, setActive] = useState(ids[0])
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined
    const seen = new Set()
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) seen.add(e.target.id)
          else seen.delete(e.target.id)
        }
        const first = ids.find((id) => seen.has(id))
        if (first) setActive(first)
      },
      { rootMargin: '-10% 0px -60% 0px' },
    )
    for (const id of ids) {
      const el = document.getElementById(id)
      if (el) io.observe(el)
    }
    return () => io.disconnect()
  }, [ids])
  return active
}

export default function HelpPage() {
  const { session } = useSession()
  const role = session.user.role
  const admin = role === 'admin'
  const auditor = role === 'auditor'
  const toc = admin ? ADMIN : auditor ? AUDITOR : OFFICER
  const active = useActiveSection(toc.map(([id]) => id))
  return (
    <div className="help-page">
      <header className="help-hero card">
        <span className="help-hero-icon">
          <Icon name="help" size={28} />
        </span>
        <div className="help-hero-text">
          <h1>Help</h1>
          <p className="muted">
            {admin
              ? 'Guide for admins'
              : auditor
                ? 'Guide for the auditor'
                : 'Guide for loan officers'}
          </p>
          <p>
            {admin
              ? 'Manage staff accounts and review precedents. Short steps, in plain words.'
              : auditor
                ? 'A read-only view of cases, decisions and the audit log, in plain words.'
                : 'From a new case to your confirmed decision, and what the system is doing in between.'}
          </p>
        </div>
      </header>

      <ul className="help-quick" aria-label="Quick links">
        {toc.slice(0, 3).map(([id, label, icon]) => (
          <li key={id}>
            <a href={`#${id}`} className="card help-quick-card">
              <span className="help-section-icon">
                <Icon name={icon} size={20} />
              </span>
              <span>{label}</span>
            </a>
          </li>
        ))}
      </ul>

      <div className="help-layout">
        <div className="help">
          {admin ? <AdminGuide /> : auditor ? <AuditorGuide /> : <OfficerGuide />}
        </div>
        <nav className="help-toc" aria-label="On this page">
          <p className="help-toc-title">On this page</p>
          <ul>
            {toc.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className={id === active ? 'active' : undefined}>
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  )
}
