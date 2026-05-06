import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Upload, ArrowLeft, ArrowRight, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/hooks/use-toast'

import { inventoryApi, type ImportRecord, type ImportPreview } from '@/services/inventory'

type Step = 'upload' | 'preview' | 'processing' | 'done'

export function SalesImportPage() {
  return <ImportWizard kind="sales" />
}
export function PurchaseImportPage() {
  return <ImportWizard kind="purchases" />
}

function ImportWizard({ kind }: { kind: 'sales' | 'purchases' }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [step, setStep] = useState<Step>('upload')
  const [record, setRecord] = useState<ImportRecord | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Poll status while processing
  useEffect(() => {
    if (step !== 'processing' || !record) return
    const t = setInterval(async () => {
      try {
        const s = await inventoryApi.importStatus(kind, record.id)
        setRecord(s)
        if (s.status === 'completed') setStep('done')
        if (s.status === 'failed') { setStep('done') }
      } catch {
        /* swallow — keep polling */
      }
    }, 2000)
    return () => clearInterval(t)
  }, [step, record, kind])

  async function handleFileSelected(file: File) {
    if (file.size > 10 * 1024 * 1024) {
      toast({ title: t('inventory.import.tooLarge'), variant: 'destructive' })
      return
    }
    const ok = ['.csv', '.xlsx', '.xls'].some(ext => file.name.toLowerCase().endsWith(ext))
    if (!ok) {
      toast({ title: t('inventory.import.unsupported'), variant: 'destructive' })
      return
    }
    setUploading(true)
    try {
      const rec = kind === 'sales'
        ? await inventoryApi.uploadSalesImport(file)
        : await inventoryApi.uploadPurchaseImport(file)
      setRecord(rec)
      const pv = await inventoryApi.previewImport(kind, rec.id)
      setPreview(pv)
      setStep('preview')
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.data?.detail || String(e),
        variant: 'destructive',
      })
    } finally {
      setUploading(false)
    }
  }

  async function handleCommit() {
    if (!record) return
    try {
      const updated = await inventoryApi.commitImport(kind, record.id)
      setRecord(updated)
      setStep('processing')
    } catch (e: any) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  function reset() {
    setStep('upload'); setRecord(null); setPreview(null)
  }

  return (
    <div className="space-y-6 p-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">
          {kind === 'sales' ? t('inventory.import.salesTitle') : t('inventory.import.purchaseTitle')}
        </h1>
        <p className="text-sm text-slate-500">{t('inventory.import.subtitle')}</p>
      </div>

      <Stepper step={step} />

      {step === 'upload' && (
        <Card>
          <CardContent className="p-12">
            <div
              className="border-2 border-dashed border-slate-300 rounded-lg p-12 text-center"
              onDragOver={e => { e.preventDefault() }}
              onDrop={e => {
                e.preventDefault()
                const f = e.dataTransfer.files[0]
                if (f) void handleFileSelected(f)
              }}
            >
              <Upload className="h-12 w-12 mx-auto text-slate-400 mb-4" />
              <h3 className="text-lg font-medium mb-2">{t('inventory.import.dropZone')}</h3>
              <p className="text-sm text-slate-500 mb-4">{t('inventory.import.formats')}</p>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) void handleFileSelected(f) }}
              />
              <Button disabled={uploading} onClick={() => fileRef.current?.click()}>
                {uploading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Upload className="h-4 w-4 mr-2" />}
                {t('inventory.import.browse')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 'preview' && record && preview && (
        <PreviewStep
          record={record}
          preview={preview}
          onBack={reset}
          onCommit={handleCommit}
        />
      )}

      {step === 'processing' && record && (
        <Card>
          <CardContent className="p-8 text-center space-y-4">
            <Loader2 className="h-10 w-10 mx-auto animate-spin text-blue-600" />
            <div className="font-medium">{t('inventory.import.processing')}</div>
            <div className="text-sm text-slate-500">
              {record.processed_count} / {record.row_count} {t('inventory.import.rows')}
            </div>
            <div className="h-2 bg-slate-200 rounded overflow-hidden mx-auto max-w-md">
              <div
                className="h-full bg-blue-600 transition-all"
                style={{
                  width: `${record.row_count > 0
                    ? Math.round((record.processed_count / record.row_count) * 100)
                    : 0}%`,
                }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {step === 'done' && record && (
        <DoneStep record={record} onAgain={reset} />
      )}
    </div>
  )
}

function Stepper({ step }: { step: Step }) {
  const { t } = useTranslation()
  const steps: { key: Step; label: string }[] = [
    { key: 'upload', label: t('inventory.import.step.upload') },
    { key: 'preview', label: t('inventory.import.step.preview') },
    { key: 'processing', label: t('inventory.import.step.processing') },
    { key: 'done', label: t('inventory.import.step.done') },
  ]
  const idx = steps.findIndex(s => s.key === step)
  return (
    <div className="flex items-center gap-2 text-xs">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-2">
          <div className={`px-3 py-1 rounded-full ${
            i < idx ? 'bg-emerald-100 text-emerald-800' :
            i === idx ? 'bg-blue-100 text-blue-800 font-medium' :
            'bg-slate-100 text-slate-500'
          }`}>
            {i + 1}. {s.label}
          </div>
          {i < steps.length - 1 && <ArrowRight className="h-3 w-3 text-slate-400" />}
        </div>
      ))}
    </div>
  )
}

function PreviewStep({
  preview, onBack, onCommit,
}: { record: ImportRecord; preview: ImportPreview; onBack: () => void; onCommit: () => void }) {
  const { t } = useTranslation()
  const validPercent = preview.total_rows > 0
    ? Math.round((preview.valid_rows / preview.total_rows) * 100)
    : 0
  const tone = validPercent < 70 ? 'rose' : validPercent < 90 ? 'amber' : 'emerald'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Card><CardContent className="p-3">
          <div className="text-xs text-slate-500">{t('inventory.import.totalRows')}</div>
          <div className="text-2xl font-bold">{preview.total_rows}</div>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <div className="text-xs text-slate-500">{t('inventory.import.validRows')}</div>
          <div className={`text-2xl font-bold text-${tone}-700`}>{preview.valid_rows} ({validPercent}%)</div>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <div className="text-xs text-slate-500">{t('inventory.import.errorRows')}</div>
          <div className="text-2xl font-bold text-rose-700">{preview.error_rows}</div>
        </CardContent></Card>
      </div>

      {preview.warnings.length > 0 && (
        <Card>
          <CardContent className="p-3 bg-amber-50">
            {preview.warnings.map((w, i) => (
              <div key={i} className="flex items-center gap-2 text-sm text-amber-800">
                <AlertCircle className="h-4 w-4" /> {w}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-3">
          <div className="text-sm font-medium mb-2">{t('inventory.import.detectedColumns')}</div>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(preview.column_map).map(([k, v]) => (
              <Badge key={k} variant="outline">
                {k} → "{preview.headers[v]}"
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-xs">
            <thead className="bg-slate-50">
              <tr>
                <th className="p-2 text-left">#</th>
                <th className="p-2 text-left">{t('inventory.import.name')}</th>
                <th className="p-2 text-left">{t('inventory.import.qty')}</th>
                <th className="p-2 text-left">{t('inventory.import.date')}</th>
                <th className="p-2 text-left">{t('inventory.import.errors')}</th>
              </tr>
            </thead>
            <tbody>
              {preview.rows.map(r => (
                <tr key={r.row_num} className={`border-t ${r.errors.length > 0 ? 'bg-rose-50' : ''}`}>
                  <td className="p-2 font-mono">{r.row_num}</td>
                  <td className="p-2">{r.name || r.sku}</td>
                  <td className="p-2">{r.quantity}</td>
                  <td className="p-2">{r.movement_date || '—'}</td>
                  <td className="p-2 text-rose-700">
                    {r.errors.map(e => e.message).join('; ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          {t('common.back')}
        </Button>
        <Button onClick={onCommit} disabled={preview.valid_rows === 0}>
          {t('inventory.import.commit')}
          <ArrowRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  )
}

function DoneStep({ record, onAgain }: { record: ImportRecord; onAgain: () => void }) {
  const { t } = useTranslation()
  const ok = record.status === 'completed'
  return (
    <Card>
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center gap-3">
          {ok ? (
            <CheckCircle2 className="h-8 w-8 text-emerald-600" />
          ) : (
            <AlertCircle className="h-8 w-8 text-rose-600" />
          )}
          <div>
            <h3 className="text-lg font-semibold">
              {ok ? t('inventory.import.success') : t('inventory.import.failed')}
            </h3>
            <p className="text-sm text-slate-500">
              {record.processed_count} / {record.row_count} {t('inventory.import.processed')}
            </p>
          </div>
        </div>

        {Object.keys(record.summary || {}).length > 0 && (
          <div>
            <div className="font-medium text-sm mb-2">{t('inventory.import.summary')}</div>
            <table className="w-full text-sm border">
              <thead className="bg-slate-50">
                <tr>
                  <th className="p-2 text-left">{t('inventory.import.item')}</th>
                  <th className="p-2 text-right">{t('inventory.import.changeApplied')}</th>
                  <th className="p-2 text-right">{t('inventory.import.newStock')}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(record.summary).map(([id, s]) => (
                  <tr key={id} className="border-t">
                    <td className="p-2">{s.name}</td>
                    <td className="p-2 text-right">{s.deducted ? `-${s.deducted}` : `+${s.received}`} {s.unit}</td>
                    <td className="p-2 text-right">{s.new_stock} {s.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {record.error_log && record.error_log.length > 0 && (
          <div>
            <div className="font-medium text-sm mb-2 text-rose-700">
              {t('inventory.import.errors')} ({record.error_log.length})
            </div>
            <div className="text-xs space-y-1 max-h-48 overflow-y-auto bg-rose-50 p-2 rounded">
              {record.error_log.map((e, i) => (
                <div key={i}>Row {e.row}: {e.column} — {e.message}</div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <Button onClick={onAgain}>{t('inventory.import.importAnother')}</Button>
        </div>
      </CardContent>
    </Card>
  )
}
