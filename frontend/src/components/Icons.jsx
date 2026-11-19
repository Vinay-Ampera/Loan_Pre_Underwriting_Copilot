// Small inline line icons, one set, one stroke (1.5). The stroke follows the text colour.
// Always used beside a text label or with an accessible name on the control.
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
  'eye-off':
    'M3 3l18 18M10.6 6.1A9.8 9.8 0 0112 6c6 0 10 6 10 6a17 17 0 01-3.2 3.7M6.6 7.6A17 17 0 002 12s4 7 10 7c1.6 0 3-.4 4.3-1M9.9 9.9a3 3 0 004.2 4.2',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  link: 'M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 4v6M9 14v6',
  // status marks (replace the old text glyphs)
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  minus: 'M6 12h12',
  'alert-circle': 'M12 21a9 9 0 100-18 9 9 0 000 18M12 7.5v5.5M12 16.5h.01',
  'help-circle':
    'M12 21a9 9 0 100-18 9 9 0 000 18M9.5 9.5a2.5 2.5 0 114 2c-.9.6-1.5 1-1.5 2M12 17h.01',
  stop: 'M12 21a9 9 0 100-18 9 9 0 000 18M9 9h6v6H9z',
  loader: 'M12 3a9 9 0 109 9',
  circle: 'M12 20a8 8 0 100-16 8 8 0 000 16',
  dot: 'M12 14.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  bell: 'M6 16v-5a6 6 0 1112 0v5l2 2H4zM10 21a2 2 0 004 0',
  inbox: 'M3 13h5l1.5 3h5L16 13h5M5 5h14l2 8v6H3v-6z',
  upload: 'M12 15V4M7.5 8.5L12 4l4.5 4.5M4 15v5h16v-5',
  'shield-check': 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM8.5 12l2.5 2.5 4.5-5',
}

export default function Icon({ name, size = 18, className }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[name]} />
    </svg>
  )
}
