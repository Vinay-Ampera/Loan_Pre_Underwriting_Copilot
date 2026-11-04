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
  ['desk', 'Start with the documents', 'cases'],
  ['links', 'Ask the applicant to upload', 'link'],
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
  ['adm-links', 'Upload links for officers', 'link'],
  ['reset', 'Reset a password', 'shield'],
  ['adm-case', 'Open and correct a case', 'cases'],
  ['adm-reassign', 'Reassign a case', 'users'],
  ['adm-records', "Messages and a case's history", 'mail'],
  ['issues', 'Read issue reports', 'flag'],
  ['precedents', 'The precedent queue', 'precedent'],
]

const AUDITOR = [
  ['aud-what', 'What you can see', 'eye'],
  ['aud-cases', 'The Cases table', 'cases'],
  ['aud-data', 'Overview and audit log', 'chart'],
  ['aud-limits', 'What you cannot do', 'shield'],
]

function AuditorGuide() {
  return (
    <>
      <HelpSection id="aud-what" icon="eye" title="What you can see">
        <p>
          The auditor account is <strong>read-only</strong> and looks at how the system is used, not
          at any one loan: how many cases there are, in which state, who decided them and whether a
          decision was overridden. You see the Overview charts, the Cases table, the audit log and
          the staff list.
        </p>
        <Callout tone="info" title="No applicant data">
          You never see an applicant, a document, a report or a message. Identifiers in the audit
          log are masked.
        </Callout>
      </HelpSection>

      <HelpSection id="aud-cases" icon="cases" title="The Cases table">
        <ol className="help-steps">
          <li>
            Open Cases. Each row is one case: reference, loan type, officer, status, score, the
            officer&apos;s decision and whether an admin changed it.
          </li>
          <li>
            Filter by status, loan type, recommendation, officer, who changed it, or created date.
            Search by case reference.
          </li>
          <li>Export CSV saves the filtered rows. The rows cannot be opened.</li>
        </ol>
      </HelpSection>

      <HelpSection id="aud-data" icon="chart" title="Overview and audit log">
        <p>
          Overview shows counts and charts, with the tiles opening the matching Cases table. The
          audit log lists who did what and when, newest first, with filters for action, user, case
          reference and dates, and a CSV export. Users lists accounts with their last sign-in, with
          no buttons.
        </p>
      </HelpSection>

      <HelpSection id="aud-limits" icon="shield" title="What you cannot do">
        <p>
          You cannot change anything. Every action that writes data answers “not allowed” for this
          account, on the server as well as in the screen, and so does every case page. There is
          exactly one auditor, created from the command line by whoever runs the system; an admin
          cannot create, disable or reset it.
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
          <li>Choose New case and pick the loan type.</li>
          <li>
            Choose how to start: with the documents (recommended), or by filling in the form first.
          </li>
          <li>
            For a home loan you may add a co-applicant; for an education loan one is required.
          </li>
          <li>When every file is in and the form is saved, submit for assessment.</li>
        </ol>
        <Callout tone="info" title="Synthetic data only">
          Never enter real customer information. This is a sample bank.
        </Callout>
      </HelpSection>

      <HelpSection id="desk" icon="cases" title="Start with the documents">
        <ol className="help-steps">
          <li>
            Drop a zip, choose a folder, or pick the files. Each file is checked and read once, then
            filed to a person (the applicant or the co-applicant).
          </li>
          <li>
            The inventory shows what is received, still missing, extra, not recognised, not
            accepted, and repeats that were ignored. Change a type or a person from its list; it
            saves at once.
          </li>
          <li>
            State the employment type (salaried or self-employed) if you know it. Until then the
            items that depend on it are listed apart and not counted as missing.
          </li>
          <li>
            If something is missing choose <strong>Ask the applicant</strong> or{' '}
            <strong>Proceed anyway</strong>. Both ask you to confirm. The identity papers are always
            needed.
          </li>
          <li>
            In the application form, the name, date of birth, PAN, Aadhaar last four and address are
            filled from the PAN and Aadhaar cards and marked <em>from documents</em>. Check them
            against the cards and tick the box. If the two cards disagree, the field is left empty
            for you.
          </li>
        </ol>
        <Callout tone="info" title="Only identity is filled in">
          The loan amount, tenure, purpose, employment, income and contact details are the
          applicant&apos;s claims. They are never read from a document. The report says when a match
          was against the same card a value was read from: that is not an independent check.
        </Callout>
      </HelpSection>

      <HelpSection id="links" icon="link" title="Ask the applicant to upload">
        <ol className="help-steps">
          <li>
            Open Upload links and choose Create a link. Confirm, then copy the address. It is shown
            once.
          </li>
          <li>
            The applicant opens it with no account, states the request and adds documents. They see
            a checklist and nothing else: no score, status or outcome. They get a reference number.
          </li>
          <li>
            The case appears in your list marked <em>From applicant</em>. Their request is their own
            statement; you can correct it in the form. Once you save the form the request is locked
            and the link takes files only.
          </li>
          <li>
            From the inventory, <strong>Ask the applicant</strong> makes a link for that case; you
            can send it as the <em>Upload link</em> message, which holds only the link and the usual
            warning.
          </li>
          <li>
            A link lasts 7 days. Extend it, or disable it at any time (you confirm). Files already
            received stay on the case. Once you submit the case, the link stops taking files.
          </li>
        </ol>
        <Callout tone="warn" title="Never share a link in public">
          Anyone with the address can add files to that case until it ends. Disable it if it went to
          the wrong place.
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
      <HelpSection id="adm-links" icon="link" title="Upload links for officers">
        <p>
          On Upload links you can create a link for an officer (choose the officer), see every link
          with its state and the case it led to, and disable any link. You do not receive the
          applicant&apos;s files unless you open the case, which you can do as for any case.
        </p>
      </HelpSection>

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

      <HelpSection id="adm-case" icon="cases" title="Open and correct a case">
        <ol className="help-steps">
          <li>
            Open Users, choose an officer, then a case from their list. Home also lists the cases
            officers decided most recently.
          </li>
          <li>
            You can read everything on the case: the documents, the extracted fields, the report and
            its audit trail. You cannot confirm, upload or submit.
          </li>
          <li>
            After the officer has decided, Change the decision lets you pick a different decision
            and write a reason. The officer&apos;s decision stays on the case and your change is
            shown beneath it as the decision in force; the officer is told on the case and on Home.
          </li>
        </ol>
        <Callout tone="warn" title="Hard rules stay hard">
          A case that failed a hard rule cannot be changed by an admin, and a change does not become
          a precedent.
        </Callout>
      </HelpSection>

      <HelpSection id="adm-reassign" icon="users" title="Reassign a case">
        <p>
          If a case is waiting on an officer who is away or disabled, open the case and choose
          Reassign to another officer. Pick an active officer and write a reason; the new officer
          then decides it. An admin never decides a case first. Disabling an officer warns you when
          they still have undecided cases.
        </p>
      </HelpSection>

      <HelpSection id="adm-records" icon="mail" title="Messages and a case's history">
        <p>
          Messages lists the contact requests officers actually sent (no drafts), with filters for
          officer, template, case and date. Each case has an Audit tab with that case&apos;s own
          history. The system-wide audit log belongs to the auditor alone, so that nobody reviews
          their own actions.
        </p>
      </HelpSection>

      <HelpSection id="issues" icon="flag" title="Read issue reports">
        <p>
          Open Issues to see problems reported by officers. Opening a report marks it read, and Mark
          as closed finishes it. Reports hold only a case reference, a category and short text; they
          never include case data. Home shows how many are open.
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
        <Callout tone="info" title="Corrections are not precedents">
          An admin change to one case never creates a precedent. Only an officer&apos;s override
          goes through the three gates.
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
