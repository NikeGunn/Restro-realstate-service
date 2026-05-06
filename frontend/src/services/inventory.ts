import { api } from './api'

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────
export type Unit =
  | 'kg' | 'g' | 'liter' | 'ml' | 'piece' | 'box' | 'bag' | 'dozen' | 'pack'

export type StockStatus = 'ok' | 'low' | 'critical' | 'negative'

export type MovementType =
  | 'purchase' | 'sale' | 'waste' | 'adjustment' | 'recipe_consumption'
  | 'supplier_return' | 'opening_stock' | 'import_sale' | 'import_purchase'

export interface InventoryCategory {
  id: string
  organization: string
  location: string | null
  name: string
  description: string
  is_active: boolean
  item_count: number
  created_at: string
  updated_at: string
}

export interface Supplier {
  id: string
  organization: string
  location: string | null
  name: string
  contact_name: string
  email: string
  phone: string
  address: string
  tax_id: string
  payment_terms: 'cod' | 'net7' | 'net15' | 'net30' | 'net60'
  notes: string
  is_active: boolean
  item_count: number
  created_at: string
  updated_at: string
}

export interface InventoryItem {
  id: string
  organization: string
  location: string | null
  sku: string
  name: string
  description: string
  category: string | null
  category_name: string | null
  unit: Unit
  unit_cost: string
  selling_price: string | null
  reorder_level: string
  reorder_quantity: string
  current_stock: string
  tolerance_percent: string
  is_active: boolean
  is_perishable: boolean
  expiry_days: number | null
  supplier: string | null
  supplier_name: string | null
  barcode: string | null
  stock_status: StockStatus
  effective_stock: {
    raw: string
    reported: string
    lower_bound: string
    upper_bound: string
    tolerance_percent: string
  }
  created_at: string
  updated_at: string
}

export interface StockMovement {
  id: string
  organization: string
  location: string | null
  item: string
  item_name: string
  item_sku: string
  item_unit: string
  movement_type: MovementType
  quantity: string
  unit_cost: string | null
  reference_id: string
  reference_type: string
  notes: string
  movement_date: string
  created_by: string | null
  created_by_email: string | null
  batch_id: string | null
  is_reversed: boolean
  reversed_by: string | null
  created_at: string
}

export interface StockAlert {
  id: string
  organization: string
  location: string | null
  item: string
  item_name: string
  item_sku: string
  item_current_stock: string
  item_unit: string
  alert_type: 'low_stock' | 'expiry' | 'negative_stock' | 'variance' | 'overstock'
  message: string
  is_resolved: boolean
  resolved_at: string | null
  resolved_by: string | null
  triggered_at: string
  whatsapp_sent: boolean
  whatsapp_sent_at: string | null
}

export interface InventoryDashboard {
  total_items: number
  critical_count: number
  negative_count: number
  total_inventory_value: string
  open_alerts: number
}

// ──────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────
function unwrap<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results
  }
  return []
}

const BASE = '/v1/inventory'

// ──────────────────────────────────────────────────────────
// Items
// ──────────────────────────────────────────────────────────
export const inventoryApi = {
  // Items
  listItems: async (params: {
    organization?: string
    location?: string
    category?: string
    supplier?: string
    is_active?: boolean
    search?: string
    status?: 'critical' | 'negative'
  } = {}): Promise<InventoryItem[]> => {
    const res = await api.get(`${BASE}/items/`, { params })
    return unwrap<InventoryItem>(res.data)
  },

  getItem: async (id: string): Promise<InventoryItem> => {
    const res = await api.get(`${BASE}/items/${id}/`)
    return res.data
  },

  createItem: async (data: Partial<InventoryItem>): Promise<InventoryItem> => {
    const res = await api.post(`${BASE}/items/`, data)
    return res.data
  },

  updateItem: async (id: string, data: Partial<InventoryItem>): Promise<InventoryItem> => {
    const res = await api.patch(`${BASE}/items/${id}/`, data)
    return res.data
  },

  deleteItem: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/items/${id}/`)
  },

  adjustStock: async (
    id: string,
    body: { quantity: string; reason: string; movement_date?: string },
  ): Promise<InventoryItem> => {
    const res = await api.post(`${BASE}/items/${id}/adjust/`, body)
    return res.data
  },

  dashboard: async (params: { organization?: string } = {}): Promise<InventoryDashboard> => {
    const res = await api.get(`${BASE}/items/dashboard/`, { params })
    return res.data
  },

  // Categories
  listCategories: async (params: { organization?: string } = {}): Promise<InventoryCategory[]> => {
    const res = await api.get(`${BASE}/categories/`, { params })
    return unwrap<InventoryCategory>(res.data)
  },

  createCategory: async (data: Partial<InventoryCategory>): Promise<InventoryCategory> => {
    const res = await api.post(`${BASE}/categories/`, data)
    return res.data
  },

  // Suppliers
  listSuppliers: async (params: { organization?: string } = {}): Promise<Supplier[]> => {
    const res = await api.get(`${BASE}/suppliers/`, { params })
    return unwrap<Supplier>(res.data)
  },

  createSupplier: async (data: Partial<Supplier>): Promise<Supplier> => {
    const res = await api.post(`${BASE}/suppliers/`, data)
    return res.data
  },

  updateSupplier: async (id: string, data: Partial<Supplier>): Promise<Supplier> => {
    const res = await api.patch(`${BASE}/suppliers/${id}/`, data)
    return res.data
  },

  deleteSupplier: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/suppliers/${id}/`)
  },

  // Movements
  listMovements: async (params: {
    organization?: string
    item?: string
    movement_type?: MovementType
    start_date?: string
    end_date?: string
  } = {}): Promise<StockMovement[]> => {
    const res = await api.get(`${BASE}/movements/`, { params })
    return unwrap<StockMovement>(res.data)
  },

  // Alerts
  listAlerts: async (params: {
    organization?: string
    resolved?: boolean
  } = {}): Promise<StockAlert[]> => {
    const res = await api.get(`${BASE}/alerts/`, { params })
    return unwrap<StockAlert>(res.data)
  },

  resolveAlert: async (id: string): Promise<StockAlert> => {
    const res = await api.post(`${BASE}/alerts/${id}/resolve/`)
    return res.data
  },
}
