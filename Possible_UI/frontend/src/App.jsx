import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'

import Terms from './pages/01_Terms'
import StoryDashboard from './pages/02_StoryDashboard'
import SourceSetup from './pages/03_SourceSetup'
import ModelProvider from './pages/04_ModelProvider'
import QAMode from './pages/05_QAMode'
import Workspace from './pages/06_Workspace'
import AssistedReview from './pages/07_AssistedReview'
import RunMonitor from './pages/08_RunMonitor'
import ResultsDashboard from './pages/09_ResultsDashboard'
import EvidenceDetail from './pages/10_EvidenceDetail'
import RunHistory from './pages/11_RunHistory'
import Settings from './pages/12_Settings'
import ClaimGraph from './pages/13_ClaimGraph'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Terms />} />
      <Route element={<AppLayout />}>
        <Route path="/dashboard" element={<StoryDashboard />} />
        <Route path="/sources" element={<SourceSetup />} />
        <Route path="/models" element={<ModelProvider />} />
        <Route path="/qa-mode" element={<QAMode />} />
        <Route path="/workspace" element={<Workspace />} />
        <Route path="/assisted" element={<AssistedReview />} />
        <Route path="/monitor" element={<RunMonitor />} />
        <Route path="/results" element={<ResultsDashboard />} />
        <Route path="/graph" element={<ClaimGraph />} />
        <Route path="/evidence" element={<EvidenceDetail />} />
        <Route path="/evidence/:id" element={<EvidenceDetail />} />
        <Route path="/history" element={<RunHistory />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
