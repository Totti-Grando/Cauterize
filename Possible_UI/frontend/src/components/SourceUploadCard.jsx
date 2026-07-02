import { useRef, useState } from 'react'
import { UploadCloud, FileText } from 'lucide-react'

// Drag-and-drop upload dropzone. Calls onFiles(File[]) — wire to backend later.
export default function SourceUploadCard({ onFiles, accept = '.pdf,.docx,.txt' }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const handle = (fileList) => {
    const files = Array.from(fileList || [])
    if (files.length) onFiles?.(files)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        handle(e.dataTransfer.files)
      }}
      onClick={() => inputRef.current?.click()}
      className={`grid-backdrop flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
        dragging ? 'border-brand-500 bg-brand-50/60' : 'border-slate-300 bg-slate-50/40 hover:border-brand-400'
      }`}
    >
      <span className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-white text-brand-600 shadow-card">
        <UploadCloud className="h-7 w-7" />
      </span>
      <div className="text-sm font-semibold text-slate-700">
        Drag &amp; drop documents here, or <span className="text-brand-600">browse</span>
      </div>
      <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
        <FileText className="h-3.5 w-3.5" /> PDF, DOCX, TXT · up to 25 MB each
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={accept}
        className="hidden"
        onChange={(e) => handle(e.target.files)}
      />
    </div>
  )
}
