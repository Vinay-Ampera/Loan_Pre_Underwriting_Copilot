import { Link } from 'react-router-dom'
import './Breadcrumbs.css'

/**
 * Where you are on a deep page, with a way back: `items` run from the top down, the last one is
 * the current page (no link). On a narrow screen only a single "← parent" link is shown.
 */
export default function Breadcrumbs({ items }) {
  const parent = [...items].reverse().find((i) => i.to)
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <ol className="crumbs-trail">
        {items.map((item, i) => {
          const last = i === items.length - 1
          return (
            <li key={`${item.label}-${i}`}>
              {last || !item.to ? (
                <span aria-current={last ? 'page' : undefined}>{item.label}</span>
              ) : (
                <Link to={item.to}>{item.label}</Link>
              )}
            </li>
          )
        })}
      </ol>
      {parent && (
        <Link className="crumbs-back" to={parent.to}>
          ← {parent.label}
        </Link>
      )}
    </nav>
  )
}
