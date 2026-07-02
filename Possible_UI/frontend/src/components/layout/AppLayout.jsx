import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopStatusBar from './TopStatusBar'

// Shell used by every page except the Terms gate.
export default function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopStatusBar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

// Standard page padding wrapper + optional page header.
export function PageContainer({ children, className = '' }) {
  return <div className={`mx-auto w-full max-w-[1400px] px-6 py-6 ${className}`}>{children}</div>
}

export function PageHeader({ title, description, actions, children }) {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
