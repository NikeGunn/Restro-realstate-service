import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Calculator, ChefHat, History } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'

import { useAuthStore } from '@/store/auth'
import {
  inventoryApi,
  type Recipe, type InventoryItem, type RecipeCalculation, type RecipeVersion,
  type FormulaType, POUR_FORMULA_TYPES,
} from '@/services/inventory'
import { restaurantApi } from '@/services/api'
import type { MenuPromoRule } from '@/types'
import { StockDisplay } from '@/components/inventory/StockDisplay'

interface DraftIngredient {
  item: string
  quantity: string
  unit: string
  is_optional: boolean
  notes: string
}

const emptyIngredient: DraftIngredient = {
  item: '', quantity: '0', unit: '', is_optional: false, notes: '',
}

const FORMULA_TYPES: FormulaType[] = [
  'food_recipe', 'drink_formula', 'cocktail_formula', 'batch_recipe', 'promo_combo_formula',
]

const FORMULA_BADGE: Record<FormulaType, string> = {
  food_recipe: 'bg-slate-100 text-slate-700',
  drink_formula: 'bg-cyan-100 text-cyan-800',
  cocktail_formula: 'bg-pink-100 text-pink-800',
  batch_recipe: 'bg-indigo-100 text-indigo-800',
  promo_combo_formula: 'bg-rose-100 text-rose-800',
}

const isPourFormula = (ft: FormulaType) => POUR_FORMULA_TYPES.includes(ft)

export function RecipesPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const orgId = useAuthStore(s => s.currentOrganization?.id)

  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [items, setItems] = useState<InventoryItem[]>([])
  const [promoRules, setPromoRules] = useState<MenuPromoRule[]>([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState<FormulaType | ''>('')

  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<Recipe | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [outputItem, setOutputItem] = useState('')
  const [outputQty, setOutputQty] = useState('1')
  const [yieldPercent, setYieldPercent] = useState('100')
  const [formulaType, setFormulaType] = useState<FormulaType>('food_recipe')
  const [servingMl, setServingMl] = useState('')
  const [pourVariance, setPourVariance] = useState('')
  const [linkedPromoRule, setLinkedPromoRule] = useState('')
  const [ingredients, setIngredients] = useState<DraftIngredient[]>([{ ...emptyIngredient }])

  const [calculator, setCalculator] = useState<Recipe | null>(null)

  useEffect(() => {
    if (!orgId) return
    void loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, typeFilter])

  async function loadAll() {
    if (!orgId) return
    setLoading(true)
    try {
      const [r, i, p] = await Promise.all([
        inventoryApi.listRecipes({
          organization: orgId,
          ...(typeFilter ? { formula_type: typeFilter } : {}),
        }),
        inventoryApi.listItems({ organization: orgId, is_active: true }),
        restaurantApi.promoRules.list({ organization: orgId }).catch(() => []),
      ])
      setRecipes(r)
      setItems(i)
      setPromoRules(p)
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  function resetForm() {
    setName(''); setDescription(''); setOutputItem(''); setOutputQty('1')
    setYieldPercent('100'); setIngredients([{ ...emptyIngredient }])
    setFormulaType('food_recipe'); setServingMl(''); setPourVariance('')
    setLinkedPromoRule('')
    setEditing(null)
  }

  function openEdit(r: Recipe) {
    setEditing(r)
    setName(r.name)
    setDescription(r.description)
    setOutputItem(r.output_item || '')
    setOutputQty(r.output_quantity)
    setYieldPercent(r.yield_percent)
    setFormulaType(r.formula_type || 'food_recipe')
    setServingMl(r.serving_ml || '')
    setPourVariance(r.pour_variance_percent || '')
    setLinkedPromoRule(r.linked_promo_rule || '')
    setIngredients(r.ingredients.map(ing => ({
      item: ing.item,
      quantity: ing.quantity,
      unit: ing.unit,
      is_optional: ing.is_optional,
      notes: ing.notes || '',
    })))
    setCreateOpen(true)
  }

  async function handleSave() {
    if (!orgId || !name) {
      toast({ title: t('inventory.recipes.nameRequired'), variant: 'destructive' })
      return
    }
    const valid = ingredients.filter(g => g.item && Number(g.quantity) > 0)
    if (valid.length === 0) {
      toast({ title: t('inventory.recipes.ingredientsRequired'), variant: 'destructive' })
      return
    }
    const payload = {
      organization: orgId,
      name,
      description,
      output_item: outputItem || null,
      output_quantity: outputQty,
      yield_percent: yieldPercent,
      formula_type: formulaType,
      // Only meaningful for pour formulas; send null otherwise to keep data clean.
      serving_ml: isPourFormula(formulaType) && servingMl ? servingMl : null,
      pour_variance_percent: isPourFormula(formulaType) && pourVariance ? pourVariance : null,
      linked_promo_rule: linkedPromoRule || null,
      ingredients: valid.map(v => ({
        item: v.item,
        quantity: v.quantity,
        unit: v.unit || items.find(it => it.id === v.item)?.unit || '',
        is_optional: v.is_optional,
        notes: v.notes,
      })),
    }
    try {
      if (editing) {
        await inventoryApi.updateRecipe(editing.id, payload)
      } else {
        await inventoryApi.createRecipe(payload)
      }
      toast({ title: t('inventory.recipes.saved') })
      setCreateOpen(false)
      resetForm()
      void loadAll()
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.data ? JSON.stringify(e.response.data) : String(e),
        variant: 'destructive',
      })
    }
  }

  async function handleDelete(r: Recipe) {
    if (!confirm(t('inventory.recipes.confirmDelete', { name: r.name }))) return
    try {
      await inventoryApi.deleteRecipe(r.id)
      toast({ title: t('inventory.recipes.deleted') })
      void loadAll()
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <ChefHat className="h-6 w-6" />
            {t('inventory.recipes.title')}
          </h1>
          <p className="text-sm text-slate-500">{t('inventory.recipes.subtitle')}</p>
        </div>
        <Button onClick={() => { resetForm(); setCreateOpen(true) }}>
          <Plus className="mr-2 h-4 w-4" />
          {t('inventory.recipes.create')}
        </Button>
      </div>

      {/* Formula-type filter chips */}
      <div className="flex flex-wrap gap-2">
        <Badge
          variant={typeFilter === '' ? 'default' : 'outline'}
          className="cursor-pointer"
          onClick={() => setTypeFilter('')}
        >
          {t('inventory.recipes.formulaTypeAll')}
        </Badge>
        {FORMULA_TYPES.map(ft => (
          <Badge
            key={ft}
            variant={typeFilter === ft ? 'default' : 'outline'}
            className="cursor-pointer"
            onClick={() => setTypeFilter(ft)}
          >
            {t(`inventory.recipes.formulaType.${ft}`)}
          </Badge>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {loading && <div className="text-slate-400">{t('common.loading')}</div>}
        {!loading && recipes.length === 0 && (
          <div className="col-span-full text-center text-slate-400 py-12">{t('inventory.recipes.empty')}</div>
        )}
        {recipes.map(r => (
          <Card key={r.id}>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold">{r.name}</h3>
                  <p className="text-xs text-slate-500">{r.output_item_name || '—'}</p>
                </div>
                <Badge variant="outline">v{r.version}</Badge>
              </div>
              <div className="flex flex-wrap gap-1">
                <Badge className={FORMULA_BADGE[r.formula_type] || FORMULA_BADGE.food_recipe} variant="outline">
                  {t(`inventory.recipes.formulaType.${r.formula_type}`)}
                </Badge>
                {isPourFormula(r.formula_type) && r.effective_pour_variance_percent && (
                  <Badge variant="outline">±{r.effective_pour_variance_percent}%</Badge>
                )}
                {r.serving_ml && (
                  <Badge variant="outline">{r.serving_ml} ml</Badge>
                )}
                {r.linked_promo_rule_label && (
                  <Badge className="bg-rose-100 text-rose-800" variant="outline">
                    {t('inventory.recipes.promoLinked')}
                  </Badge>
                )}
              </div>
              <div className="text-xs text-slate-600">
                {t('inventory.recipes.ingredientsCount', { count: r.ingredients.length })} ·{' '}
                {t('inventory.recipes.yieldX', { p: r.yield_percent })}
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setCalculator(r)}>
                  <Calculator className="mr-1 h-3 w-3" />
                  {t('inventory.recipes.calc')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => openEdit(r)}>
                  {t('common.edit')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => handleDelete(r)}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Create / edit dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editing ? t('inventory.recipes.edit') : t('inventory.recipes.create')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>{t('inventory.recipes.name')}</Label>
                <Input value={name} onChange={e => setName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>{t('inventory.recipes.outputItem')}</Label>
                <Select value={outputItem} onValueChange={setOutputItem}>
                  <SelectTrigger><SelectValue placeholder={t('common.optional')} /></SelectTrigger>
                  <SelectContent>
                    {items.map(it => (
                      <SelectItem key={it.id} value={it.id}>{it.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>{t('inventory.recipes.outputQty')}</Label>
                <Input type="number" step="0.0001" value={outputQty} onChange={e => setOutputQty(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>{t('inventory.recipes.yieldPercent')}</Label>
                <Input type="number" step="0.01" min="1" max="100" value={yieldPercent} onChange={e => setYieldPercent(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>{t('inventory.recipes.formulaTypeLabel')}</Label>
                <Select value={formulaType} onValueChange={(v) => setFormulaType(v as FormulaType)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {FORMULA_TYPES.map(ft => (
                      <SelectItem key={ft} value={ft}>
                        {t(`inventory.recipes.formulaType.${ft}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {isPourFormula(formulaType) && (
                <>
                  <div className="space-y-1">
                    <Label>{t('inventory.recipes.servingMl')}</Label>
                    <Input type="number" step="0.01" min="0" value={servingMl}
                      onChange={e => setServingMl(e.target.value)} placeholder="130" />
                  </div>
                  <div className="space-y-1">
                    <Label>{t('inventory.recipes.pourVariance')}</Label>
                    <Input type="number" step="0.01" min="0" max="100" value={pourVariance}
                      onChange={e => setPourVariance(e.target.value)} placeholder="5.0" />
                  </div>
                </>
              )}
              <div className="space-y-1 col-span-2">
                <Label>{t('inventory.recipes.linkedPromoRule')}</Label>
                <Select
                  value={linkedPromoRule || '__none__'}
                  onValueChange={(v) => setLinkedPromoRule(v === '__none__' ? '' : v)}
                >
                  <SelectTrigger><SelectValue placeholder={t('common.optional')} /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">{t('inventory.recipes.noPromoRule')}</SelectItem>
                    {promoRules.map(pr => (
                      <SelectItem key={pr.id} value={pr.id}>
                        {pr.promo_type_display} — {pr.menu_item_name} (×{pr.inventory_deduction_multiplier})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-slate-500">{t('inventory.recipes.promoRuleHint')}</p>
              </div>
            </div>

            <div className="space-y-1">
              <Label>{t('inventory.recipes.description')}</Label>
              <Textarea value={description} onChange={e => setDescription(e.target.value)} />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>{t('inventory.recipes.ingredients')}</Label>
                <Button size="sm" variant="outline"
                  onClick={() => setIngredients([...ingredients, { ...emptyIngredient }])}>
                  <Plus className="h-3 w-3 mr-1" />
                  {t('inventory.recipes.addIngredient')}
                </Button>
              </div>
              {ingredients.map((ing, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-5">
                    <Select
                      value={ing.item}
                      onValueChange={v => {
                        const next = [...ingredients]
                        const item = items.find(it => it.id === v)
                        next[i] = { ...next[i], item: v, unit: item?.unit || '' }
                        setIngredients(next)
                      }}
                    >
                      <SelectTrigger><SelectValue placeholder={t('inventory.po.selectItem')} /></SelectTrigger>
                      <SelectContent>
                        {items.map(it => (
                          <SelectItem key={it.id} value={it.id}>{it.name} ({it.unit})</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-3">
                    <Input
                      type="number" step="0.0001" placeholder="qty"
                      value={ing.quantity}
                      onChange={e => {
                        const next = [...ingredients]
                        next[i] = { ...next[i], quantity: e.target.value }
                        setIngredients(next)
                      }}
                    />
                  </div>
                  <div className="col-span-2 flex items-center gap-2">
                    <Switch
                      checked={ing.is_optional}
                      onCheckedChange={v => {
                        const next = [...ingredients]
                        next[i] = { ...next[i], is_optional: v }
                        setIngredients(next)
                      }}
                    />
                    <span className="text-xs text-slate-500">{t('inventory.recipes.optional')}</span>
                  </div>
                  <div className="col-span-2">
                    <Button size="icon" variant="ghost"
                      onClick={() => setIngredients(ingredients.filter((_, j) => j !== i))}
                      disabled={ingredients.length === 1}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleSave}>{t('common.save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {calculator && (
        <RecipeCalculatorDialog
          recipe={calculator}
          onClose={() => setCalculator(null)}
          onConsumed={() => { setCalculator(null); void loadAll() }}
        />
      )}
    </div>
  )
}

function RecipeCalculatorDialog({
  recipe, onClose, onConsumed,
}: { recipe: Recipe; onClose: () => void; onConsumed: () => void }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [batches, setBatches] = useState('1')
  const [calc, setCalc] = useState<RecipeCalculation | null>(null)
  const [versions, setVersions] = useState<RecipeVersion[]>([])
  const [showVersions, setShowVersions] = useState(false)
  const [loading, setLoading] = useState(false)

  const recalc = useCallback(async () => {
    if (Number(batches) <= 0) return
    setLoading(true)
    try {
      const out = await inventoryApi.calculateRecipe(recipe.id, batches)
      setCalc(out)
    } catch (e: any) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }, [recipe.id, batches, toast, t])

  useEffect(() => { void recalc() }, [recalc])

  async function loadVersions() {
    try {
      setVersions(await inventoryApi.recipeVersions(recipe.id))
      setShowVersions(true)
    } catch (e) {
      toast({ title: t('common.error'), description: String(e), variant: 'destructive' })
    }
  }

  async function handleConsume() {
    if (!calc?.feasible) return
    if (!confirm(t('inventory.recipes.confirmConsume', { batches, name: recipe.name }))) return
    try {
      await inventoryApi.consumeRecipe(recipe.id, batches)
      toast({ title: t('inventory.recipes.consumed') })
      onConsumed()
    } catch (e: any) {
      toast({
        title: t('common.error'),
        description: e?.response?.data ? JSON.stringify(e.response.data) : String(e),
        variant: 'destructive',
      })
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('inventory.recipes.calculator')}: {recipe.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>{t('inventory.recipes.batches')}</Label>
              <Input
                type="number" step="0.1" min="0.1"
                value={batches}
                onChange={e => setBatches(e.target.value)}
              />
            </div>
            <div className="space-y-1 self-end">
              <Button variant="outline" onClick={loadVersions}>
                <History className="h-4 w-4 mr-1" />
                {t('inventory.recipes.versions')}
              </Button>
            </div>
          </div>

          {loading && <div className="text-slate-400">{t('common.loading')}</div>}

          {calc && (
            <>
              <div className={`p-3 rounded ${calc.feasible ? 'bg-emerald-50 text-emerald-800' : 'bg-rose-50 text-rose-800'}`}>
                {calc.feasible
                  ? t('inventory.recipes.feasible')
                  : t('inventory.recipes.notFeasible')}
              </div>

              <table className="w-full text-sm border">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="p-2 text-left">{t('inventory.recipes.ingredient')}</th>
                    <th className="p-2 text-right">{t('inventory.recipes.required')}</th>
                    <th className="p-2 text-right">{t('inventory.recipes.available')}</th>
                    <th className="p-2 text-right">{t('inventory.recipes.shortfall')}</th>
                    <th className="p-2">{t('inventory.recipes.status_')}</th>
                  </tr>
                </thead>
                <tbody>
                  {calc.ingredients.map(ing => {
                    const isShort = Number(ing.shortfall) > 0
                    const isWarn = calc.warnings.some(w => w.item_id === ing.item_id)
                    return (
                      <tr key={ing.item_id} className="border-t">
                        <td className="p-2">{ing.item_name}</td>
                        <td className="p-2 text-right">{ing.required_quantity} {ing.unit}</td>
                        <td className="p-2 text-right">
                          <StockDisplay
                            reported={ing.available_reported}
                            raw={ing.available_raw}
                            lowerBound={ing.lower_bound}
                            upperBound={ing.upper_bound}
                            tolerancePercent="0"
                            unit={ing.unit}
                            isCritical={isShort}
                          />
                        </td>
                        <td className="p-2 text-right">{ing.shortfall}</td>
                        <td className="p-2">
                          {isShort ? (
                            <Badge className="bg-rose-100 text-rose-800">✗</Badge>
                          ) : isWarn ? (
                            <Badge className="bg-amber-100 text-amber-800">⚠</Badge>
                          ) : (
                            <Badge className="bg-emerald-100 text-emerald-800">✓</Badge>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>

              <div className="grid grid-cols-3 gap-3 text-sm">
                <Card><CardContent className="p-3">
                  <div className="text-xs text-slate-500">{t('inventory.recipes.estimatedCost')}</div>
                  <div className="text-lg font-bold">${calc.estimated_cost}</div>
                </CardContent></Card>
                <Card><CardContent className="p-3">
                  <div className="text-xs text-slate-500">{t('inventory.recipes.costPerOutput')}</div>
                  <div className="text-lg font-bold">${calc.cost_per_output || '—'}</div>
                </CardContent></Card>
                <Card><CardContent className="p-3">
                  <div className="text-xs text-slate-500">{t('inventory.recipes.output')}</div>
                  <div className="text-lg font-bold">
                    {calc.output_quantity ? `${calc.output_quantity}` : '—'}
                  </div>
                </CardContent></Card>
              </div>
            </>
          )}

          {showVersions && (
            <div className="border rounded p-3 max-h-60 overflow-y-auto">
              <div className="font-semibold text-sm mb-2">{t('inventory.recipes.versionHistory')}</div>
              {versions.length === 0 && <div className="text-xs text-slate-400">No versions.</div>}
              {versions.map(v => (
                <div key={v.id} className="text-xs py-1 border-b last:border-0">
                  <span className="font-mono">v{v.version_number}</span> · {new Date(v.changed_at).toLocaleString()}
                  {v.changed_by_email && <span className="text-slate-500"> · {v.changed_by_email}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>{t('common.close')}</Button>
          <Button onClick={handleConsume} disabled={!calc?.feasible}>
            {t('inventory.recipes.consume')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
