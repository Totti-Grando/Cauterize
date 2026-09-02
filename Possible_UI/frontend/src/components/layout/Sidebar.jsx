import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FolderUp,
  Cpu,
  ListChecks,
  MessagesSquare,
  ClipboardCheck,
  Activity,
  BarChart3,
  FileSearch,
  History,
  Settings,
  ShieldCheck,
  Waypoints,
} from 'lucide-react'

const NAV = [
  {
    section: 'Overview',
    items: [{ to: '/dashboard', label: 'Story Dashboard', icon: LayoutDashboard }],
  },
  {
    section: 'Setup',
    items: [
      { to: '/sources', label: 'Source Setup', icon: FolderUp },
      { to: '/models', label: 'Models & Providers', icon: Cpu },
      { to: '/qa-mode', label: 'Q&A Mode', icon: ListChecks },
    ],
  },
  {
    section: 'Evaluate',
    items: [
      { to: '/workspace', label: 'Evaluation Workspace', icon: MessagesSquare },
      { to: '/assisted', label: 'Assisted Review', icon: ClipboardCheck },
      { to: '/monitor', label: 'Run Monitor', icon: Activity },
    ],
  },
  {
    section: 'Results',
    items: [
      { to: '/results', label: 'Results Dashboard', icon: BarChart3 },
      { to: '/graph', label: 'Claim Graph', icon: Waypoints },
      { to: '/evidence', label: 'Evidence Detail', icon: FileSearch },
      { to: '/history', label: 'Run History', icon: History },
    ],
  },
  {
    section: 'System',
    items: [{ to: '/settings', label: 'Settings', icon: Settings }],
  },
]

export default function Sidebar() {
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-navy-900 text-slate-300">
      <div className="flex items-center gap-3 px-5 py-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
          <ShieldCheck className="h-5 w-5" />
        </span>
        <div className="leading-tight">
          <div className="text-sm font-bold text-white">Q&A Evaluation</div>
          <div className="text-[11px] font-medium text-brand-300">Studio</div>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-6">
        {NAV.map((group) => (
          <div key={group.section}>
            <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              {group.section}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `focusable flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-brand-600/15 text-white ring-1 ring-inset ring-brand-500/30'
                        : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'
                    }`
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-white/5 px-5 py-4">
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Responsible AI Operations
        </div>
        <div className="mt-1 text-[10px] text-slate-500">Internal evaluation use only · v0.1</div>
      </div>
    </aside>
  )
}
