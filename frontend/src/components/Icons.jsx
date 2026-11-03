// Small inline icons (stroke follows the text colour). Always used beside a text label.
const paths = {
  home: 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  cases: 'M4 5h16M4 12h16M4 19h16',
  plus: 'M12 5v14M5 12h14',
  precedent: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7',
  users:
    'M16 20v-1a4 4 0 00-4-4H8a4 4 0 00-4 4v1M10 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7M20 20v-1a4 4 0 00-3-3.9M16 4.2a3.5 3.5 0 010 6.6',
  signout: 'M9 4H5v16h4M16 8l4 4-4 4M20 12H9',
  monitor: 'M3 5h18v11H3zM9 20h6M12 16v4',
  moon: 'M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z',
  sun: 'M12 16a4 4 0 100-8 4 4 0 000 8M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  help: 'M12 21a9 9 0 100-18 9 9 0 000 18M9.5 9.5a2.5 2.5 0 114 2c-.9.6-1.5 1-1.5 2M12 17h.01',
  alert: 'M12 3l10 18H2zM12 10v5M12 18h.01',
  info: 'M12 21a9 9 0 100-18 9 9 0 000 18M12 11v5M12 8h.01',
  mail: 'M3 6h18v12H3zM3 7l9 7 9-7',
  chart: 'M4 20V10M10 20V4M16 20v-8M22 20H2',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
}

export default function Icon({ name, size = 18 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[name]} />
    </svg>
  )
}
