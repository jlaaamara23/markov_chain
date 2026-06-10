import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Home' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/graph', label: 'Markov chain' },
  { to: '/stocks', label: 'Stocks' },
]

function NavBar() {
  return (
    <header className="navbar">
      <div className="navbar-brand">TradeMind</div>
      <nav className="navbar-links">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}

export default NavBar
