import { useMemo, useState } from 'react'
import './index.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function newSessionId() {
  return crypto.randomUUID()
}

function Field({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-900">{value || 'Not captured'}</p>
    </div>
  )
}

function EmergencyPanel() {
  return (
    <section className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-950 shadow-sm">
      <h2 className="text-lg font-bold text-red-700 flex items-center gap-2">
        <span>⚠️</span> Emergency Helplines
      </h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
        <li><strong>National Emergency Number (ERSS):</strong> 112</li>
        <li><strong>Medical Emergency / Ambulance:</strong> 108 or 102</li>
        <li><strong>National Health Helpline:</strong> 104</li>
      </ul>
    </section>
  )
}

function DoctorCard({ doctor }) {
  return (
    <article className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-[72px_1fr]">
      <img
        src={doctor.profile_image || '/favicon.svg'}
        alt={doctor.name}
        className="h-16 w-16 rounded-lg object-cover"
        onError={(event) => {
          event.currentTarget.src = '/favicon.svg'
        }}
      />
      <div className="min-w-0">
        <h3 className="truncate text-base font-bold text-slate-950">{doctor.name}</h3>
        <p className="mt-1 text-sm text-slate-600">{doctor.speciality_names || 'Speciality unavailable'}</p>
        <p className="mt-1 text-sm text-slate-600">
          {doctor.experience ? `${doctor.experience} years experience` : 'Experience unavailable'}
        </p>
        <div className="mt-3 rounded-md bg-slate-50 p-2 text-xs text-slate-700">
          <p className="font-semibold capitalize">{doctor.availability_status || 'Availability pending'}</p>
          <p>{doctor.next_available_date || 'Date unavailable'} {doctor.next_available_time || ''}</p>
          <p>{doctor.next_available_slot || 'Slot unavailable'}</p>
        </div>
        {doctor.web_url && (
          <a
            className="mt-3 inline-flex rounded-md bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800"
            href={doctor.web_url}
            target="_blank"
            rel="noreferrer"
          >
            Book appointment
          </a>
        )}
      </div>
    </article>
  )
}

function App() {
  const [sessionId, setSessionId] = useState(newSessionId)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [schema, setSchema] = useState(null)
  const [finalReport, setFinalReport] = useState('')
  const [doctors, setDoctors] = useState([])
  const [doctorKeyword, setDoctorKeyword] = useState('')
  const [doctorError, setDoctorError] = useState('')
  const [emergency, setEmergency] = useState(false)
  const [complete, setComplete] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const canSend = input.trim() && !loading && !complete
  const associatedSymptoms = useMemo(() => schema?.associated_symptoms || [], [schema])

  async function sendMessage(event) {
    event.preventDefault()
    if (!canSend) return

    const userText = input.trim()
    setInput('')
    setError('')
    setLoading(true)
    setMessages((current) => [...current, { role: 'user', content: userText }])

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: userText }),
      })
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      const data = await response.json()

      const rawResponse = data.response || ''

      // Intercept clinical text summaries and separate them from timeline bubbles
      const isReport = 
        rawResponse.includes('Patient Summary:') || 
        rawResponse.includes('**Session Complete**') ||
        rawResponse.includes('URGENT MEDICAL ATTENTION') ||
        rawResponse.includes('Chat Session Report')

      if (!isReport) {
        setMessages((current) => [...current, { role: 'assistant', content: rawResponse }])
      } else {
        let cleanReport = rawResponse.split('Full JSON report:')[0].trim()
        if (cleanReport.endsWith('---')) cleanReport = cleanReport.slice(0, -3).trim()
        setFinalReport(cleanReport)
      }

      setSchema(data.current_schema)
      setEmergency(data.emergency)
      setComplete(data.session_complete)
      setDoctorKeyword(data.doctor_keyword || '')
      setDoctors(data.doctors || [])
      setDoctorError(data.doctor_lookup_error || '')
    } catch (err) {
      setError(err.message || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function resetSession() {
    try {
      await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' })
    } catch {
      // Best effort cleanup
    }
    setSessionId(newSessionId())
    setMessages([])
    setInput('')
    setSchema(null)
    setFinalReport('')
    setDoctors([])
    setDoctorKeyword('')
    setDoctorError('')
    setEmergency(false)
    setComplete(false)
    setError('')
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-950">
      <div className="mx-auto max-w-3xl px-4 py-5">
        <section className="flex min-h-[calc(100vh-40px)] flex-col rounded-lg border border-slate-200 bg-white shadow-sm">
          <header className="flex items-center justify-between border-b border-slate-200 p-4">
            <div>
              <h1 className="text-xl font-bold">Rural Medical Assistant</h1>
              <p className="text-sm text-slate-500">Short intake chat for symptom report and doctor booking.</p>
            </div>
            <button className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50" onClick={resetSession}>
              New session
            </button>
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
                Tell me symptom, duration, severity. Example: fever since yesterday, 6/10.
              </div>
            )}

            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[82%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm leading-6 ${
                  message.role === 'user' ? 'bg-emerald-700 text-white' : 'bg-slate-100 text-slate-900'
                }`}>
                  {message.content}
                </div>
              </div>
            ))}

            {loading && <p className="text-sm text-slate-500 animate-pulse">Analyzing symptoms...</p>}
            {error && <p className="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p>}

            {/* Assessment Completion Banners */}
            {complete && (
              <div className="flex justify-start pt-2 w-full">
                {emergency ? (
                  <div className="w-full rounded-lg bg-red-100 border border-red-300 p-4 text-sm text-red-950 leading-6 font-semibold shadow-sm animate-pulse">
                    <div className="flex items-center gap-2 text-base text-red-700 font-bold mb-1">
                      <span>🚨</span> Urgent Critical Alert
                    </div>
                    Immediate clinical medical attention is required. Please follow the safety guidance and phone lines referenced below immediately.
                  </div>
                ) : (
                  <div className="max-w-[82%] rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-900 leading-6 font-medium">
                    Thank you. Your assessment is complete. Below are the recommended paths forward based on your summary.
                  </div>
                )}
              </div>
            )}

            {/* Emergency Support Panel Render Path */}
            {emergency && (
              <div className="mt-4 pt-2">
                <EmergencyPanel />
              </div>
            )}

            {/* Routine Doctor Directory Render Path */}
            {complete && !emergency && (
              <div className="mt-4 space-y-3 border-t border-slate-100 pt-4">
                <h2 className="text-base font-bold text-slate-900">Recommended Available Doctors</h2>
                {doctorError && <p className="rounded-md bg-amber-50 p-2 text-sm text-amber-800">{doctorError}</p>}
                <div className="space-y-3">
                  {doctors.length > 0
                    ? doctors.map((doctor) => <DoctorCard doctor={doctor} key={doctor.id} />)
                    : !doctorError && <p className="text-sm text-slate-600">No matching doctors found in your region.</p>}
                </div>
              </div>
            )}
          </div>

          <form className="flex gap-2 border-t border-slate-200 p-4" onSubmit={sendMessage}>
            <input
              className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-700"
              disabled={complete || loading}
              onChange={(event) => setInput(event.target.value)}
              placeholder={complete ? 'Session complete' : 'Describe symptoms...'}
              value={input}
            />
            <button
              className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
              disabled={!canSend}
              type="submit"
            >
              Send
            </button>
          </form>
        </section>
      </div>
    </main>
  )
}

export default App