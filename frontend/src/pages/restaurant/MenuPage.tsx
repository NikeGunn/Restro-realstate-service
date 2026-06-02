import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Edit, Trash, ChevronDown, ChevronRight, Percent } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { restaurantApi, organizationsApi } from '@/services/api'
import type { MenuCategory, MenuItem, MenuItemType, MenuPromoRule, Organization } from '@/types'

const DIETARY_OPTIONS = [
  { value: 'vegetarian', label: 'Vegetarian', color: 'bg-green-100 text-green-800' },
  { value: 'vegan', label: 'Vegan', color: 'bg-green-200 text-green-900' },
  { value: 'gluten-free', label: 'Gluten-Free', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'dairy-free', label: 'Dairy-Free', color: 'bg-blue-100 text-blue-800' },
  { value: 'nut-free', label: 'Nut-Free', color: 'bg-orange-100 text-orange-800' },
  { value: 'spicy', label: 'Spicy', color: 'bg-red-100 text-red-800' },
]

const ITEM_TYPES: MenuItemType[] = [
  'food', 'drink', 'alcohol', 'cocktail', 'buffet', 'combo', 'promotion', 'addon',
]

const PROMO_TYPES = [
  'buy_x_get_y', 'combo', 'staff_discount', 'happy_hour', 'buffet_session',
] as const

const ITEM_TYPE_BADGE: Record<MenuItemType, string> = {
  food: 'bg-slate-100 text-slate-800',
  drink: 'bg-cyan-100 text-cyan-800',
  alcohol: 'bg-amber-100 text-amber-900',
  cocktail: 'bg-pink-100 text-pink-800',
  buffet: 'bg-purple-100 text-purple-800',
  combo: 'bg-indigo-100 text-indigo-800',
  promotion: 'bg-rose-100 text-rose-800',
  addon: 'bg-gray-100 text-gray-700',
}

export function MenuPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedOrgId, setSelectedOrgId] = useState<string>('')
  const [categories, setCategories] = useState<MenuCategory[]>([])
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)

  // Category Dialog State
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false)
  const [editingCategory, setEditingCategory] = useState<MenuCategory | null>(null)
  const [categoryForm, setCategoryForm] = useState({ name: '', description: '', is_active: true })

  // Item Dialog State
  const [itemDialogOpen, setItemDialogOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<MenuItem | null>(null)
  const [itemCategoryId, setItemCategoryId] = useState<string>('')
  const [itemForm, setItemForm] = useState({
    name: '',
    description: '',
    price: '',
    item_type: 'food' as MenuItemType,
    is_alcohol: false,
    alcohol_brand: '',
    sold_out: false,
    dietary_info: [] as string[],
    is_available: true,
    is_active: true,
  })

  // Item-type filter chip ('' = all)
  const [typeFilter, setTypeFilter] = useState<MenuItemType | ''>('')

  // Promo Rule Dialog State
  const [promoDialogOpen, setPromoDialogOpen] = useState(false)
  const [promoItem, setPromoItem] = useState<MenuItem | null>(null)
  const [existingRule, setExistingRule] = useState<MenuPromoRule | null>(null)
  const [promoForm, setPromoForm] = useState({
    promo_type: 'happy_hour' as string,
    sales_quantity_multiplier: '1.00',
    revenue_multiplier: '1.00',
    inventory_deduction_multiplier: '1.00',
    active_from: '',
    active_to: '',
    notes: '',
  })

  // Load organizations
  useEffect(() => {
    const loadOrgs = async () => {
      try {
        const data = await organizationsApi.list()
        const restaurantOrgs = data.filter((org: Organization) => org.business_type === 'restaurant')
        setOrganizations(restaurantOrgs)
        if (restaurantOrgs.length > 0) {
          setSelectedOrgId(restaurantOrgs[0].id)
        }
      } catch (error) {
        console.error('Failed to load organizations:', error)
        toast({ title: 'Error', description: 'Failed to load organizations', variant: 'destructive' })
      }
    }
    loadOrgs()
  }, [toast])

  // Load categories when org changes
  const loadCategories = useCallback(async () => {
    if (!selectedOrgId) return
    setLoading(true)
    try {
      const data = await restaurantApi.categories.list({ organization: selectedOrgId })
      setCategories(Array.isArray(data) ? data : data.results || [])
    } catch (error) {
      console.error('Failed to load categories:', error)
      toast({ title: 'Error', description: 'Failed to load menu categories', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }, [selectedOrgId, toast])

  useEffect(() => {
    loadCategories()
  }, [loadCategories])

  // Toggle category expansion
  const toggleCategory = (categoryId: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev)
      if (next.has(categoryId)) {
        next.delete(categoryId)
      } else {
        next.add(categoryId)
      }
      return next
    })
  }

  // Category CRUD
  const openCategoryDialog = (category?: MenuCategory) => {
    if (category) {
      setEditingCategory(category)
      setCategoryForm({
        name: category.name,
        description: category.description || '',
        is_active: category.is_active,
      })
    } else {
      setEditingCategory(null)
      setCategoryForm({ name: '', description: '', is_active: true })
    }
    setCategoryDialogOpen(true)
  }

  const handleSaveCategory = async () => {
    try {
      if (editingCategory) {
        await restaurantApi.categories.update(editingCategory.id, categoryForm)
        toast({ title: 'Success', description: 'Category updated successfully' })
      } else {
        await restaurantApi.categories.create({
          organization: selectedOrgId,
          ...categoryForm,
        })
        toast({ title: 'Success', description: 'Category created successfully' })
      }
      setCategoryDialogOpen(false)
      loadCategories()
    } catch (error) {
      console.error('Failed to save category:', error)
      toast({ title: 'Error', description: 'Failed to save category', variant: 'destructive' })
    }
  }

  const handleDeleteCategory = async (categoryId: string) => {
    if (!confirm('Are you sure you want to delete this category and all its items?')) return
    try {
      await restaurantApi.categories.delete(categoryId)
      toast({ title: 'Success', description: 'Category deleted successfully' })
      loadCategories()
    } catch (error) {
      console.error('Failed to delete category:', error)
      toast({ title: 'Error', description: 'Failed to delete category', variant: 'destructive' })
    }
  }

  // Item CRUD
  const openItemDialog = (categoryId: string, item?: MenuItem) => {
    setItemCategoryId(categoryId)
    if (item) {
      setEditingItem(item)
      setItemForm({
        name: item.name,
        description: item.description || '',
        price: item.price,
        item_type: item.item_type || 'food',
        is_alcohol: item.is_alcohol ?? false,
        alcohol_brand: item.alcohol_brand || '',
        sold_out: item.sold_out ?? false,
        dietary_info: item.dietary_info || [],
        is_available: item.is_available,
        is_active: item.is_active,
      })
    } else {
      setEditingItem(null)
      setItemForm({
        name: '',
        description: '',
        price: '',
        item_type: 'food',
        is_alcohol: false,
        alcohol_brand: '',
        sold_out: false,
        dietary_info: [],
        is_available: true,
        is_active: true,
      })
    }
    setItemDialogOpen(true)
  }

  // Promo Rule handlers
  const openPromoDialog = async (item: MenuItem) => {
    setPromoItem(item)
    setPromoDialogOpen(true)
    try {
      const rule = await restaurantApi.promoRules.getForItem(item.id)
      setExistingRule(rule)
      if (rule) {
        setPromoForm({
          promo_type: rule.promo_type,
          sales_quantity_multiplier: rule.sales_quantity_multiplier,
          revenue_multiplier: rule.revenue_multiplier,
          inventory_deduction_multiplier: rule.inventory_deduction_multiplier,
          active_from: rule.active_from || '',
          active_to: rule.active_to || '',
          notes: rule.notes || '',
        })
      } else {
        setPromoForm({
          promo_type: 'happy_hour',
          sales_quantity_multiplier: '1.00',
          revenue_multiplier: '1.00',
          inventory_deduction_multiplier: '1.00',
          active_from: '',
          active_to: '',
          notes: '',
        })
      }
    } catch {
      setExistingRule(null)
    }
  }

  const handleSavePromo = async () => {
    if (!promoItem) return
    const payload = {
      promo_type: promoForm.promo_type,
      sales_quantity_multiplier: promoForm.sales_quantity_multiplier,
      revenue_multiplier: promoForm.revenue_multiplier,
      inventory_deduction_multiplier: promoForm.inventory_deduction_multiplier,
      active_from: promoForm.active_from || null,
      active_to: promoForm.active_to || null,
      notes: promoForm.notes,
    }
    try {
      if (existingRule) {
        await restaurantApi.promoRules.update(promoItem.id, existingRule.id, payload)
      } else {
        await restaurantApi.promoRules.create(promoItem.id, payload)
      }
      toast({ title: t('restaurant.menu.promoRuleSaved') })
      setPromoDialogOpen(false)
    } catch (error) {
      console.error('Failed to save promo rule:', error)
      toast({ title: 'Error', description: t('restaurant.menu.saveError'), variant: 'destructive' })
    }
  }

  const handleDeletePromo = async () => {
    if (!promoItem || !existingRule) return
    try {
      await restaurantApi.promoRules.delete(promoItem.id, existingRule.id)
      toast({ title: t('restaurant.menu.promoRuleDeleted') })
      setExistingRule(null)
      setPromoDialogOpen(false)
    } catch (error) {
      console.error('Failed to delete promo rule:', error)
      toast({ title: 'Error', description: t('restaurant.menu.deleteError'), variant: 'destructive' })
    }
  }

  const handleSaveItem = async () => {
    try {
      if (editingItem) {
        await restaurantApi.items.update(editingItem.id, itemForm)
        toast({ title: 'Success', description: 'Item updated successfully' })
      } else {
        await restaurantApi.items.create({
          category: itemCategoryId,
          ...itemForm,
        })
        toast({ title: 'Success', description: 'Item created successfully' })
      }
      setItemDialogOpen(false)
      loadCategories()
    } catch (error) {
      console.error('Failed to save item:', error)
      toast({ title: 'Error', description: 'Failed to save item', variant: 'destructive' })
    }
  }

  const handleDeleteItem = async (itemId: string) => {
    if (!confirm('Are you sure you want to delete this item?')) return
    try {
      await restaurantApi.items.delete(itemId)
      toast({ title: 'Success', description: 'Item deleted successfully' })
      loadCategories()
    } catch (error) {
      console.error('Failed to delete item:', error)
      toast({ title: 'Error', description: 'Failed to delete item', variant: 'destructive' })
    }
  }

  const handleToggleAvailability = async (itemId: string) => {
    try {
      await restaurantApi.items.toggleAvailability(itemId)
      loadCategories()
    } catch (error) {
      console.error('Failed to toggle availability:', error)
      toast({ title: 'Error', description: 'Failed to update item', variant: 'destructive' })
    }
  }

  const toggleDietaryInfo = (value: string) => {
    setItemForm(prev => ({
      ...prev,
      dietary_info: prev.dietary_info.includes(value)
        ? prev.dietary_info.filter(d => d !== value)
        : [...prev.dietary_info, value],
    }))
  }

  if (organizations.length === 0 && !loading) {
    return (
      <div className="p-6">
        <Card className="p-8 text-center">
          <h2 className="text-xl font-semibold mb-2">No Restaurant Organization</h2>
          <p className="text-muted-foreground">
            Create a restaurant organization first to manage your menu.
          </p>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('restaurant.menu.title')}</h1>
          <p className="text-muted-foreground">{t('restaurant.menu.subtitle')}</p>
        </div>
        <div className="flex gap-4">
          {organizations.length > 1 && (
            <Select value={selectedOrgId} onValueChange={setSelectedOrgId}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Select restaurant" />
              </SelectTrigger>
              <SelectContent>
                {organizations.map(org => (
                  <SelectItem key={org.id} value={org.id}>{org.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button onClick={() => openCategoryDialog()}>
            <Plus className="h-4 w-4 mr-2" />
            {t('restaurant.menu.addCategory')}
          </Button>
        </div>
      </div>

      {/* Item-type filter chips */}
      <div className="flex flex-wrap gap-2">
        <Badge
          variant={typeFilter === '' ? 'default' : 'outline'}
          className="cursor-pointer"
          onClick={() => setTypeFilter('')}
        >
          {t('restaurant.menu.filterAll')}
        </Badge>
        {ITEM_TYPES.map(tp => (
          <Badge
            key={tp}
            variant={typeFilter === tp ? 'default' : 'outline'}
            className="cursor-pointer"
            onClick={() => setTypeFilter(tp)}
          >
            {t(`restaurant.menu.itemType.${tp}`)}
          </Badge>
        ))}
      </div>

      {/* Categories List */}
      {loading ? (
        <Card className="p-8 text-center">Loading menu...</Card>
      ) : categories.length === 0 ? (
        <Card className="p-8 text-center">
          <h3 className="text-lg font-semibold mb-2">{t('restaurant.menu.noCategoriesYet')}</h3>
          <p className="text-muted-foreground mb-4">{t('restaurant.menu.startByAdding')}</p>
          <Button onClick={() => openCategoryDialog()}>
            <Plus className="h-4 w-4 mr-2" />
            {t('restaurant.menu.addFirstCategory')}
          </Button>
        </Card>
      ) : (
        <div className="space-y-4">
          {categories.map(category => (
            <Card key={category.id} className={!category.is_active ? 'opacity-60' : ''}>
              <CardHeader className="py-3">
                <div className="flex items-center justify-between">
                  <div
                    className="flex items-center gap-2 cursor-pointer flex-1"
                    onClick={() => toggleCategory(category.id)}
                  >
                    {expandedCategories.has(category.id) ? (
                      <ChevronDown className="h-5 w-5" />
                    ) : (
                      <ChevronRight className="h-5 w-5" />
                    )}
                    <CardTitle className="text-lg">{category.name}</CardTitle>
                    <Badge variant="outline">{category.items_count} {t('restaurant.menu.items')}</Badge>
                    {!category.is_active && <Badge variant="secondary">Inactive</Badge>}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => openItemDialog(category.id)}>
                      <Plus className="h-4 w-4 mr-1" />
                      {t('restaurant.menu.addItem')}
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => openCategoryDialog(category)}>
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => handleDeleteCategory(category.id)}>
                      <Trash className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                </div>
                {category.description && (
                  <p className="text-sm text-muted-foreground mt-1 ml-7">{category.description}</p>
                )}
              </CardHeader>

              {expandedCategories.has(category.id) && category.items && (
                <CardContent className="border-t pt-4">
                  {category.items.length === 0 ? (
                    <p className="text-center text-muted-foreground py-4">
                      {t('restaurant.menu.noItemsYet')}
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {category.items
                        .filter(item => !typeFilter || item.item_type === typeFilter)
                        .map(item => (
                        <div
                          key={item.id}
                          className={`flex items-start justify-between p-3 rounded-lg border ${
                            !item.is_available || item.sold_out ? 'bg-gray-50 opacity-60' : 'bg-white'
                          }`}
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h4 className="font-medium">{item.name}</h4>
                              <span className="font-semibold text-green-600">${item.price}</span>
                              {item.item_type && (
                                <Badge className={ITEM_TYPE_BADGE[item.item_type]} variant="outline">
                                  {t(`restaurant.menu.itemType.${item.item_type}`)}
                                </Badge>
                              )}
                              {item.is_alcohol && item.alcohol_brand && (
                                <Badge variant="outline">{item.alcohol_brand}</Badge>
                              )}
                              {item.sold_out && (
                                <Badge variant="destructive">{t('restaurant.menu.soldOut')}</Badge>
                              )}
                              {!item.is_available && (
                                <Badge variant="secondary">Unavailable</Badge>
                              )}
                            </div>
                            {item.description && (
                              <p className="text-sm text-muted-foreground mt-1">{item.description}</p>
                            )}
                            {item.dietary_info && item.dietary_info.length > 0 && (
                              <div className="flex gap-1 mt-2">
                                {item.dietary_info.map(diet => {
                                  const option = DIETARY_OPTIONS.find(d => d.value === diet)
                                  return (
                                    <Badge key={diet} className={option?.color || ''} variant="outline">
                                      {option?.label || diet}
                                    </Badge>
                                  )
                                })}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            <Switch
                              checked={item.is_available}
                              onCheckedChange={() => handleToggleAvailability(item.id)}
                              title="Toggle availability"
                            />
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => openPromoDialog(item)}
                              title={t('restaurant.menu.managePromo')}
                            >
                              <Percent className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" onClick={() => openItemDialog(category.id, item)}>
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" onClick={() => handleDeleteItem(item.id)}>
                              <Trash className="h-4 w-4 text-red-500" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Category Dialog */}
      <Dialog open={categoryDialogOpen} onOpenChange={setCategoryDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingCategory ? t('restaurant.menu.editCategory') : t('restaurant.menu.addCategory')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="cat-name">Name</Label>
              <Input
                id="cat-name"
                value={categoryForm.name}
                onChange={e => setCategoryForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g., Appetizers"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cat-desc">Description (optional)</Label>
              <Textarea
                id="cat-desc"
                value={categoryForm.description}
                onChange={e => setCategoryForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Brief description of this category"
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={categoryForm.is_active}
                onCheckedChange={checked => setCategoryForm(prev => ({ ...prev, is_active: checked }))}
              />
              <Label>Active</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCategoryDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveCategory}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Item Dialog */}
      <Dialog open={itemDialogOpen} onOpenChange={setItemDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editingItem ? t('restaurant.menu.editItem') : t('restaurant.menu.addItem')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="item-name">Name</Label>
              <Input
                id="item-name"
                value={itemForm.name}
                onChange={e => setItemForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g., Bruschetta"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="item-price">Price ($)</Label>
              <Input
                id="item-price"
                type="number"
                step="0.01"
                min="0"
                value={itemForm.price}
                onChange={e => setItemForm(prev => ({ ...prev, price: e.target.value }))}
                placeholder="9.99"
              />
            </div>
            <div className="space-y-2">
              <Label>{t('restaurant.menu.itemTypeLabel')}</Label>
              <Select
                value={itemForm.item_type}
                onValueChange={(v) => setItemForm(prev => ({
                  ...prev,
                  item_type: v as MenuItemType,
                  // sensible default: cocktail/alcohol implies alcohol flag
                  is_alcohol: v === 'alcohol' || v === 'cocktail' ? true : prev.is_alcohol,
                }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ITEM_TYPES.map(tp => (
                    <SelectItem key={tp} value={tp}>
                      {t(`restaurant.menu.itemType.${tp}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={itemForm.is_alcohol}
                onCheckedChange={checked => setItemForm(prev => ({ ...prev, is_alcohol: checked }))}
              />
              <Label>{t('restaurant.menu.isAlcohol')}</Label>
            </div>
            {(itemForm.is_alcohol || itemForm.item_type === 'cocktail') && (
              <div className="space-y-2">
                <Label htmlFor="item-brand">{t('restaurant.menu.alcoholBrand')}</Label>
                <Input
                  id="item-brand"
                  value={itemForm.alcohol_brand}
                  onChange={e => setItemForm(prev => ({ ...prev, alcohol_brand: e.target.value }))}
                  placeholder={t('restaurant.menu.alcoholBrandPlaceholder')}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="item-desc">Description (optional)</Label>
              <Textarea
                id="item-desc"
                value={itemForm.description}
                onChange={e => setItemForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Describe this item"
              />
            </div>
            <div className="space-y-2">
              <Label>Dietary Information</Label>
              <div className="flex flex-wrap gap-2">
                {DIETARY_OPTIONS.map(option => (
                  <Badge
                    key={option.value}
                    variant={itemForm.dietary_info.includes(option.value) ? 'default' : 'outline'}
                    className={`cursor-pointer ${itemForm.dietary_info.includes(option.value) ? option.color : ''}`}
                    onClick={() => toggleDietaryInfo(option.value)}
                  >
                    {option.label}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2">
                <Switch
                  checked={itemForm.is_available}
                  onCheckedChange={checked => setItemForm(prev => ({ ...prev, is_available: checked }))}
                />
                <Label>Available</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={itemForm.is_active}
                  onCheckedChange={checked => setItemForm(prev => ({ ...prev, is_active: checked }))}
                />
                <Label>Active</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={itemForm.sold_out}
                  onCheckedChange={checked => setItemForm(prev => ({ ...prev, sold_out: checked }))}
                />
                <Label>{t('restaurant.menu.soldOut')}</Label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setItemDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveItem}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Promo Rule Dialog */}
      <Dialog open={promoDialogOpen} onOpenChange={setPromoDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('restaurant.menu.promoRule.title')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-muted-foreground">
              {promoItem?.name} — {t('restaurant.menu.promoRule.subtitle')}
            </p>
            <div className="space-y-2">
              <Label>{t('restaurant.menu.promoRule.promoType')}</Label>
              <Select
                value={promoForm.promo_type}
                onValueChange={(v) => setPromoForm(prev => ({ ...prev, promo_type: v }))}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PROMO_TYPES.map(pt => (
                    <SelectItem key={pt} value={pt}>
                      {t(`restaurant.menu.promoRule.type.${pt}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t('restaurant.menu.promoRule.salesMultiplier')}</Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={promoForm.sales_quantity_multiplier}
                  onChange={e => setPromoForm(prev => ({ ...prev, sales_quantity_multiplier: e.target.value }))}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('restaurant.menu.promoRule.revenueMultiplier')}</Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={promoForm.revenue_multiplier}
                  onChange={e => setPromoForm(prev => ({ ...prev, revenue_multiplier: e.target.value }))}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('restaurant.menu.promoRule.inventoryMultiplier')}</Label>
                <Input
                  type="number" step="0.01" min="0"
                  value={promoForm.inventory_deduction_multiplier}
                  onChange={e => setPromoForm(prev => ({ ...prev, inventory_deduction_multiplier: e.target.value }))}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{t('restaurant.menu.promoRule.hint')}</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t('restaurant.menu.promoRule.activeFrom')}</Label>
                <Input
                  type="time"
                  value={promoForm.active_from}
                  onChange={e => setPromoForm(prev => ({ ...prev, active_from: e.target.value }))}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('restaurant.menu.promoRule.activeTo')}</Label>
                <Input
                  type="time"
                  value={promoForm.active_to}
                  onChange={e => setPromoForm(prev => ({ ...prev, active_to: e.target.value }))}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t('restaurant.menu.promoRule.notes')}</Label>
              <Textarea
                value={promoForm.notes}
                onChange={e => setPromoForm(prev => ({ ...prev, notes: e.target.value }))}
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:justify-between">
            {existingRule ? (
              <Button variant="ghost" className="text-red-500" onClick={handleDeletePromo}>
                {t('restaurant.menu.promoRule.removeRule')}
              </Button>
            ) : <span />}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setPromoDialogOpen(false)}>Cancel</Button>
              <Button onClick={handleSavePromo}>Save</Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
