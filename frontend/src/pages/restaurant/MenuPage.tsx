import { useState, useEffect, useCallback } from 'react'
import { Plus, Edit, Trash, ChevronDown, ChevronRight } from 'lucide-react'
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
import type { MenuCategory, MenuItem, Organization } from '@/types'

const DIETARY_OPTIONS = [
  { value: 'vegetarian', label: 'Vegetarian', color: 'bg-green-100 text-green-800' },
  { value: 'vegan', label: 'Vegan', color: 'bg-green-200 text-green-900' },
  { value: 'gluten-free', label: 'Gluten-Free', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'dairy-free', label: 'Dairy-Free', color: 'bg-blue-100 text-blue-800' },
  { value: 'nut-free', label: 'Nut-Free', color: 'bg-orange-100 text-orange-800' },
  { value: 'spicy', label: 'Spicy', color: 'bg-red-100 text-red-800' },
]

export function MenuPage() {
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
    dietary_info: [] as string[],
    is_available: true,
    is_active: true,
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
        dietary_info: [],
        is_available: true,
        is_active: true,
      })
    }
    setItemDialogOpen(true)
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
          <h1 className="text-2xl font-bold">Menu Management</h1>
          <p className="text-muted-foreground">Manage your restaurant menu categories and items</p>
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
            Add Category
          </Button>
        </div>
      </div>

      {/* Categories List */}
      {loading ? (
        <Card className="p-8 text-center">Loading menu...</Card>
      ) : categories.length === 0 ? (
        <Card className="p-8 text-center">
          <h3 className="text-lg font-semibold mb-2">No menu categories yet</h3>
          <p className="text-muted-foreground mb-4">Start by adding your first category (e.g., Appetizers, Main Course)</p>
          <Button onClick={() => openCategoryDialog()}>
            <Plus className="h-4 w-4 mr-2" />
            Add Your First Category
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
                    <Badge variant="outline">{category.items_count} items</Badge>
                    {!category.is_active && <Badge variant="secondary">Inactive</Badge>}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => openItemDialog(category.id)}>
                      <Plus className="h-4 w-4 mr-1" />
                      Add Item
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
                      No items in this category yet.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {category.items.map(item => (
                        <div
                          key={item.id}
                          className={`flex items-start justify-between p-3 rounded-lg border ${
                            !item.is_available ? 'bg-gray-50 opacity-60' : 'bg-white'
                          }`}
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <h4 className="font-medium">{item.name}</h4>
                              <span className="font-semibold text-green-600">${item.price}</span>
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
            <DialogTitle>{editingCategory ? 'Edit Category' : 'Add Category'}</DialogTitle>
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
            <DialogTitle>{editingItem ? 'Edit Item' : 'Add Item'}</DialogTitle>
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
            <div className="flex items-center gap-4">
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
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setItemDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveItem}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
