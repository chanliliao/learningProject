/**
 * NavBar — persistent top navigation bar rendered on every page.
 *
 * Uses React Router's `useLocation` to highlight the currently active link.
 * Must be rendered inside a `<Router>` context.
 */

import { Link, useLocation } from 'react-router-dom'

/** Route entries rendered in the nav bar. */
const NAV_LINKS = [
  { to: '/', label: 'Upload' },
  { to: '/eval', label: 'Eval' },
  { to: '/health', label: 'Health' },
]

/**
 * Application-wide navigation bar.
 *
 * Renders the app name and a set of links.  The link matching the current
 * pathname is styled in blue; all others are gray.
 */
export default function NavBar() {
  const { pathname } = useLocation()
  return (
    <nav className="bg-white border-b border-gray-200 px-8 py-3 flex items-center gap-6">
      <span className="font-semibold text-gray-900 mr-2">Pipeline</span>
      {NAV_LINKS.map(({ to, label }) => (
        <Link
          key={to}
          to={to}
          className={`text-sm font-medium transition-colors ${
            pathname === to ? 'text-blue-600' : 'text-gray-500 hover:text-gray-900'
          }`}
        >
          {label}
        </Link>
      ))}
    </nav>
  )
}
