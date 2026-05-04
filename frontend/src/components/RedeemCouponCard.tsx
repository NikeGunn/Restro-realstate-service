import { useState } from 'react'
import { couponsApi } from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/hooks/use-toast'
import { Sparkles, CheckCircle2 } from 'lucide-react'

export function RedeemCouponCard() {
  const { currentOrganization, setCurrentOrganization } = useAuthStore()
  const { toast } = useToast()
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)

  const handleRedeem = async () => {
    const trimmed = code.trim()
    if (!trimmed || !currentOrganization) return

    setLoading(true)
    try {
      const redemption = await couponsApi.redeem(trimmed, currentOrganization.id)
      const until = new Date(redemption.granted_until).toLocaleDateString()
      toast({
        title: 'Coupon applied',
        description: `${redemption.coupon.plan_granted.toUpperCase()} plan active until ${until}.`,
      })
      setCurrentOrganization({
        ...currentOrganization,
        plan: redemption.coupon.plan_granted,
        plan_expires_at: redemption.granted_until,
      })
      setCode('')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast({
        variant: 'destructive',
        title: 'Coupon could not be applied',
        description: detail || 'Please check the code and try again.',
      })
    } finally {
      setLoading(false)
    }
  }

  const planExpiry = currentOrganization?.plan_expires_at
    ? new Date(currentOrganization.plan_expires_at).toLocaleDateString()
    : null

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-amber-500" />
          <CardTitle>Plan & Coupons</CardTitle>
        </div>
        <CardDescription>
          Current plan: <span className="font-semibold uppercase">{currentOrganization?.plan || 'basic'}</span>
          {planExpiry && (
            <> · expires <span className="font-semibold">{planExpiry}</span></>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="redeem-code">Have a coupon code?</Label>
          <div className="flex gap-2">
            <Input
              id="redeem-code"
              placeholder="Enter coupon code"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              autoComplete="off"
              disabled={loading}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRedeem()
              }}
            />
            <Button onClick={handleRedeem} disabled={loading || !code.trim()}>
              {loading ? 'Applying...' : (
                <>
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                  Redeem
                </>
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Codes are case-insensitive. Redeeming a code applies its plan instantly.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
