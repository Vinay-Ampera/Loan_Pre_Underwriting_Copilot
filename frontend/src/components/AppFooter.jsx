import { Link } from 'react-router-dom'
import './AppFooter.css'

/** Slim footer inside the signed-in shell. The login page does not render it. */
export default function AppFooter() {
  return (
    <footer className="app-footer">
      <span>Pramaan, sample bank, synthetic data only</span>
      <span className="app-footer-end">
        <Link to="/help">Help</Link>
        <span>Version {__APP_VERSION__}</span>
      </span>
    </footer>
  )
}
