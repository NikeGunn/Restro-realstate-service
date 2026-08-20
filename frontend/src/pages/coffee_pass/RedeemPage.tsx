import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  CheckCircle2, Coffee, RotateCcw, ScanLine, AlertTriangle, XCircle,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  coffeePassApi, type CoffeePassRedemption, type ResolveResult,
} from '@/services/coffeePass'

/**
 * The till screen. Designed for one-handed use under time pressure:
 *
 * - one job per step (find the pass -> enter the amount -> confirm);
 * - the discount is displayed BIG because it is the number the barista types
 *   into the POS, and a misread costs the cafe money;
 * - refusal states are loud and specific — "expired" and "already used" require
 *   different words to the customer standing there;
 * - the whole flow resets to a focused input, so the next customer needs zero
 *   clicks to start.
 */
type Step = 'scan' | 'confirm' | 'done'

export function CoffeePassRedeemPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { currentOrganization } = useAuthStore()
  const orgId = currentOrganization?.id

  const [step, setStep] = useState<Step>('scan')
  const [code, setCode] = useState('')
  const [resolved, setResolved] = useState<ResolveResult | null>(null)
  const [subtotal, setSubtotal] = useState('')
  const [receipt, setReceipt] = useState('')
  const [result, setResult] = useState<CoffeePassRedemption | null>(null)
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)

  const codeInputRef = useRef<HTMLInputElement>(null)
  const subtotalInputRef = useRef<HTMLInputElement>(null)

  // Keep the cursor where the next keystroke belongs — a barista should never
  // have to reach for the mouse between customers.
  useEffect(() => {
    if (step === 'scan') codeInputRef.current?.focus()
    if (step === 'confirm') subtotalInputRef.current?.focus()
  }, [step])

  const reset = useCallback(() => {
    setStep('scan')
    setCode('')
    setResolved(null)
    setSubtotal('')
    setReceipt('')
    setResult(null)
    setRefusal(null)
  }, [])

  const handleResolve = async () => {
    if (!code.trim() || !orgId) return
    setBusy(true)
    setRefusal(null)
    try {
      const data = await coffeePassApi.resolveCode({
        code: code.trim(), organization: orgId,
      })
      if (!data.valid) {
        // A refused code is normal at a busy till — show precise copy, keep the
        // field focused, do not treat it as an error state.
        setRefusal(data.reason_code)
        setCode('')
        codeInputRef.current?.focus()
        return
      }
      setResolved(data)
      setStep('confirm')
    } catch {
      toast({ title: t('coffeePass.redeem.resolveFailed'), variant: 'destructive' })
    } finally {
      setBusy(false)
    }
  }

  const handleRedeem = async () => {
    if (!resolved?.verification_token_id || !orgId) return
    const amount = parseFloat(subtotal)
    if (!Number.isFinite(amount) || amount < 0) {
      toast({ title: t('coffeePass.redeem.invalidSubtotal'), variant: 'destructive' })
      return
    }
    setBusy(true)
    try {
      const redemption = await coffeePassApi.createRedemption({
        verification_token_id: resolved.verification_token_id,
        eligible_subtotal_hkd: amount.toFixed(2),
        pos_receipt_reference: receipt.trim(),
        organization: orgId,
      })
      setResult(redemption)
      setStep('done')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        .response?.data?.detail
      // Send the staff member back to the start on a terminal refusal — the
      // token is gone and retrying the same one cannot work.
      setRefusal(detail ?? 'redeem_failed')
      setStep('scan')
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  // Preview the discount live so the barista knows the POS figure before
  // committing. Server recalculates authoritatively — this is display only.
  const previewDiscount = useMemo(() => {
    const amount = parseFloat(subtotal)
    const pct = parseFloat(resolved?.discount_percent ?? '0')
    if (!Number.isFinite(amount) || !Number.isFinite(pct) || amount <= 0) return null
    return {
      discount: ((amount * pct) / 100).toFixed(2),
      payable: (amount - (amount * pct) / 100).toFixed(2),
    }
  }, [subtotal, resolved?.discount_percent])

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold">{t('coffeePass.redeem.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('coffeePass.redeem.subtitle')}</p>
      </div>

      {refusal && <RefusalBanner reason={refusal} onDismiss={() => setRefusal(null)} />}

      {step === 'scan' && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div>
              <Label htmlFor="cp-code">{t('coffeePass.redeem.codeLabel')}</Label>
              <div className="flex gap-2 mt-1.5">
                <Input
                  ref={codeInputRef}
                  id="cp-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleResolve() }}
                  placeholder={t('coffeePass.redeem.codePlaceholder')}
                  // Large, monospaced: a 6-digit code read aloud across a
                  // counter must be unambiguous.
                  className="text-lg font-mono tracking-widest h-12"
                  autoComplete="off"
                />
                <Button
                  onClick={handleResolve}
                  disabled={busy || !code.trim()}
                  className="h-12 px-6"
                >
                  <ScanLine className="h-4 w-4 mr-2" />
                  {t('coffeePass.redeem.lookUp')}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {t('coffeePass.redeem.codeHint')}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 'confirm' && resolved && (
        <>
          <Card className="border-emerald-200 bg-emerald-50/50">
            <CardContent className="pt-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                    <span className="font-semibold">{resolved.customer_name}</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    {resolved.plan_name}
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-bold text-emerald-700 tabular-nums">
                    {parseFloat(resolved.discount_percent ?? '0')}%
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t('coffeePass.redeem.discount')}
                  </p>
                </div>
              </div>

              {/* Eligible items — the barista must apply the discount only to
                  these lines, so they are listed explicitly. */}
              {resolved.eligible_items && resolved.eligible_items.length > 0 && (
                <div className="mt-4 pt-4 border-t border-emerald-200">
                  <p className="text-xs font-medium mb-2">
                    {t('coffeePass.redeem.eligibleItems')}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {resolved.eligible_items.map((item) => (
                      <span
                        key={item.id}
                        className="inline-flex items-center gap-1 rounded-full bg-white
                                   border px-2.5 py-1 text-xs"
                      >
                        <Coffee className="h-3 w-3 text-muted-foreground" />
                        {item.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6 space-y-4">
              <div>
                <Label htmlFor="cp-subtotal">
                  {t('coffeePass.redeem.subtotalLabel')}
                </Label>
                <Input
                  ref={subtotalInputRef}
                  id="cp-subtotal"
                  type="number" min="0" step="0.01"
                  value={subtotal}
                  onChange={(e) => setSubtotal(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRedeem() }}
                  placeholder="0.00"
                  className="text-lg h-12 tabular-nums"
                />
                <p className="text-xs text-muted-foreground mt-1.5">
                  {t('coffeePass.redeem.subtotalHint')}
                </p>
              </div>

              {/* THE number the barista types into the POS. Deliberately the
                  largest element on screen. */}
              {previewDiscount && (
                <div className="rounded-lg bg-muted p-4">
                  <div className="flex items-baseline justify-between">
                    <span className="text-sm text-muted-foreground">
                      {t('coffeePass.redeem.discountAmount')}
                    </span>
                    <span className="text-3xl font-bold tabular-nums">
                      −HK${previewDiscount.discount}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between mt-2 pt-2 border-t">
                    <span className="text-sm text-muted-foreground">
                      {t('coffeePass.redeem.customerPays')}
                    </span>
                    <span className="text-lg font-semibold tabular-nums">
                      HK${previewDiscount.payable}
                    </span>
                  </div>
                </div>
              )}

              <div>
                <Label htmlFor="cp-receipt">{t('coffeePass.redeem.receiptLabel')}</Label>
                <Input
                  id="cp-receipt" value={receipt}
                  onChange={(e) => setReceipt(e.target.value)}
                  placeholder={t('coffeePass.redeem.receiptPlaceholder')}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  {t('coffeePass.redeem.receiptHint')}
                </p>
              </div>

              <div className="flex gap-2">
                <Button variant="outline" onClick={reset} disabled={busy}>
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={handleRedeem}
                  disabled={busy || !subtotal}
                  className="flex-1 h-11"
                >
                  {busy
                    ? t('coffeePass.redeem.recording')
                    : t('coffeePass.redeem.confirm')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {step === 'done' && result && (
        <Card className="border-emerald-300">
          <CardContent className="pt-8 pb-6 text-center space-y-4">
            <CheckCircle2 className="h-14 w-14 text-emerald-600 mx-auto" />
            <div>
              <h2 className="text-xl font-semibold">
                {t('coffeePass.redeem.recorded')}
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                {result.customer_name}
              </p>
            </div>

            <div className="inline-flex flex-col items-center rounded-lg bg-emerald-50 px-8 py-4">
              <span className="text-xs text-muted-foreground uppercase tracking-wide">
                {t('coffeePass.redeem.saved')}
              </span>
              <span className="text-4xl font-bold text-emerald-700 tabular-nums">
                HK${result.discount_amount_hkd}
              </span>
            </div>

            <Button onClick={reset} className="w-full h-11">
              <RotateCcw className="h-4 w-4 mr-2" />
              {t('coffeePass.redeem.next')}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/**
 * Refusal copy is per-reason on purpose: "this code was already used" and "this
 * pass expired" need different things said to the customer at the counter.
 */
function RefusalBanner({ reason, onDismiss }: { reason: string; onDismiss: () => void }) {
  const { t } = useTranslation()

  // Wrong-location and already-used are the two a barista must explain, so they
  // get the louder treatment.
  const severe = ['wrong_location', 'wrong_organization', 'code_already_used_or_expired']
    .includes(reason)

  return (
    <div className={`rounded-lg border p-4 flex items-start gap-3 ${
      severe
        ? 'border-rose-200 bg-rose-50 text-rose-900'
        : 'border-amber-200 bg-amber-50 text-amber-900'
    }`}>
      {severe
        ? <XCircle className="h-5 w-5 shrink-0 mt-0.5" />
        : <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />}
      <div className="flex-1">
        <p className="font-medium text-sm">
          {t(`coffeePass.redeem.refusal.${reason}`, {
            defaultValue: t('coffeePass.redeem.refusal.generic'),
          })}
        </p>
        <p className="text-xs mt-0.5 opacity-80">
          {t(`coffeePass.redeem.refusalHint.${reason}`, { defaultValue: '' })}
        </p>
      </div>
      <Button variant="ghost" size="sm" onClick={onDismiss}>
        {t('common.dismiss')}
      </Button>
    </div>
  )
}
