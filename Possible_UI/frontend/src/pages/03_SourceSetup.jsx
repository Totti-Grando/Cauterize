import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileText,
  Link2,
  Trash2,
  Plus,
  ArrowRight,
  ShieldAlert,
  Loader2,
  FileCheck,
  Lock,
  FileX,
  Eye,
} from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import Stepper from '../components/Stepper'
import { Card, CardHeader } from '../components/Card'
import Button from '../components/Button'
import StatusChip from '../components/StatusChip'
import SourceUploadCard from '../components/SourceUploadCard'
import { Tabs, Input, Field } from '../components/ui'
import { api } from '../api'
import { useRun } from '../context/RunContext'

const FETCH_TONE = { success: 'success', login: 'warning', failed: 'danger' }
const EXTRACT_TONE = { extracted: 'success', blocked: 'danger', review: 'warning', pending: 'info' }
const QUALITY_ICON = { 'Extractable text': FileCheck, 'Login page detected': Lock, 'Empty source': FileX, 'Needs review': Eye }

export default function SourceSetup() {
  const navigate = useNavigate()
  const { update } = useRun()
  const [tab, setTab] = useState('upload')
  const [data, setData] = useState({ documents: [], links: [], quality: [] })
  const [loading, setLoading] = useState(true)
  const [url, setUrl] = useState('')
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    api.getSources().then((d) => {
      setData(d)
      setLoading(false)
    })
  }, [])

  const addDocs = (files) => {
    const docs = files.map((f, i) => ({
      id: `new-${i}-${f.name}`,
      name: f.name,
      type: (f.name.split('.').pop() || '').toUpperCase(),
      size: `${(f.size / 1024).toFixed(0)} KB`,
      status: 'pending',
    }))
    setData((d) => ({ ...d, documents: [...d.documents, ...docs] }))
    // simulate extraction completing
    setTimeout(() => {
      setData((d) => ({
        ...d,
        documents: d.documents.map((doc) => (doc.status === 'pending' ? { ...doc, status: 'extracted' } : doc)),
      }))
    }, 1200)
  }

  const addLink = async () => {
    if (!url.trim()) return
    setAdding(true)
    const link = await api.addLink(url.trim())
    setData((d) => ({ ...d, links: [...d.links, link] }))
    setUrl('')
    setAdding(false)
  }

  const removeDoc = (id) => setData((d) => ({ ...d, documents: d.documents.filter((x) => x.id !== id) }))
  const removeLink = (id) => setData((d) => ({ ...d, links: d.links.filter((x) => x.id !== id) }))

  const cont = () => {
    update({ documents: data.documents, links: data.links })
    navigate('/models')
  }

  return (
    <PageContainer>
      <PageHeader
        title="Source Setup"
        description="Add the documents and links that ground this evaluation."
        actions={
          <Button onClick={cont} iconRight={ArrowRight}>
            Continue to Model Setup
          </Button>
        }
      />
      <Card className="mb-6 px-6 py-4">
        <Stepper current={0} />
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: 'upload', label: 'Upload Documents', icon: FileText, count: data.documents.length },
              { key: 'links', label: 'Add Links', icon: Link2, count: data.links.length },
            ]}
          />

          {tab === 'upload' ? (
            <div className="space-y-4">
              <SourceUploadCard onFiles={addDocs} />
              <Card>
                <CardHeader title="Documents" subtitle="Uploaded files and extraction status" icon={FileText} />
                <SourceTable
                  loading={loading}
                  cols={['File Name', 'Type', 'Size', 'Status', '']}
                  rows={data.documents}
                  render={(doc) => (
                    <tr key={doc.id} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-800">{doc.name}</td>
                      <td className="px-4 py-3 text-slate-500">{doc.type}</td>
                      <td className="px-4 py-3 text-slate-500">{doc.size}</td>
                      <td className="px-4 py-3">
                        {doc.status === 'pending' ? (
                          <StatusChip tone="info" size="xs">
                            <Loader2 className="h-3 w-3 animate-spin" /> Extracting
                          </StatusChip>
                        ) : (
                          <StatusChip tone={EXTRACT_TONE[doc.status]} size="xs" dot>
                            {doc.status === 'review' ? 'Needs review' : 'Extracted'}
                          </StatusChip>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => removeDoc(doc.id)}
                          className="focusable rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  )}
                  empty="No documents yet — drag files above to begin."
                />
              </Card>
            </div>
          ) : (
            <div className="space-y-4">
              <Card className="p-5">
                <Field label="Source link">
                  <div className="flex gap-2">
                    <Input
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addLink()}
                      placeholder="Paste research link or SharePoint/source link"
                    />
                    <Button onClick={addLink} icon={adding ? Loader2 : Plus} disabled={adding}>
                      {adding ? 'Adding' : 'Add Link'}
                    </Button>
                  </div>
                </Field>
              </Card>
              <Card>
                <CardHeader title="Links" subtitle="Fetch and extraction status per source" icon={Link2} />
                <SourceTable
                  loading={loading}
                  cols={['URL', 'Source Type', 'Fetch Status', 'Extracted Text', '']}
                  rows={data.links}
                  render={(l) => (
                    <tr key={l.id} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="max-w-[260px] truncate px-4 py-3 font-medium text-brand-700">{l.url}</td>
                      <td className="px-4 py-3 text-slate-500">{l.sourceType}</td>
                      <td className="px-4 py-3">
                        <StatusChip tone={FETCH_TONE[l.fetchStatus]} size="xs" dot>
                          {l.fetchStatus === 'login' ? 'Login page' : l.fetchStatus}
                        </StatusChip>
                      </td>
                      <td className="px-4 py-3">
                        <StatusChip tone={EXTRACT_TONE[l.extractStatus]} size="xs">
                          {l.extractStatus}
                        </StatusChip>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => removeLink(l.id)}
                          className="focusable rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  )}
                  empty="No links yet — paste a URL above."
                />
              </Card>
            </div>
          )}
        </div>

        {/* Source quality panel */}
        <div>
          <Card className="sticky top-4">
            <CardHeader title="Source Quality" subtitle="Automated checks across all sources" icon={ShieldAlert} />
            <div className="divide-y divide-slate-100">
              {data.quality.map((q) => {
                const Icon = QUALITY_ICON[q.label] ?? FileCheck
                return (
                  <div key={q.label} className="flex items-center justify-between px-5 py-3">
                    <span className="flex items-center gap-2.5 text-sm text-slate-600">
                      <Icon className="h-4 w-4 text-slate-400" /> {q.label}
                    </span>
                    <StatusChip tone={q.count > 0 ? q.tone : 'neutral'}>{q.count}</StatusChip>
                  </div>
                )
              })}
            </div>
            <div className="border-t border-slate-100 bg-amber-50/60 px-5 py-3 text-xs text-amber-800">
              1 source returned a login page and was excluded from grounding.
            </div>
          </Card>
        </div>
      </div>
    </PageContainer>
  )
}

function SourceTable({ loading, cols, rows, render, empty }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
            {cols.map((c, i) => (
              <th key={i} className={`px-4 py-2.5 font-semibold ${i === cols.length - 1 ? 'text-right' : ''}`}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={cols.length} className="px-4 py-8 text-center text-sm text-slate-400">
                <Loader2 className="mx-auto h-5 w-5 animate-spin" />
              </td>
            </tr>
          ) : rows.length ? (
            rows.map(render)
          ) : (
            <tr>
              <td colSpan={cols.length} className="px-4 py-8 text-center text-sm text-slate-400">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
