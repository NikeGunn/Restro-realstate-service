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
// Phase 2 / 3 types
// ──────────────────────────────────────────────────────────
export type POStatus = 'draft' | 'sent' | 'partial' | 'received' | 'cancelled'

export interface PurchaseOrderItem {
  id: string
  purchase_order: string
  item: string
  item_name: string
  item_sku: string
  item_unit: string
  quantity_ordered: string
  quantity_received: string
  unit_cost: string
  notes: string
  line_total: string
  created_at: string
  updated_at: string
}

export interface PurchaseOrder {
  id: string
  organization: string
  location: string | null
  supplier: string
  supplier_name: string
  order_number: string
  status: POStatus
  order_date: string
  expected_date: string | null
  received_date: string | null
  notes: string
  total_amount: string
  items: PurchaseOrderItem[]
  locked_fields: string[]
  created_at: string
  updated_at: string
}

export interface RecipeIngredient {
  id?: string
  recipe?: string
  item: string
  item_name?: string
  item_sku?: string
  item_unit?: string
  quantity: string
  unit: string
  is_optional: boolean
  notes?: string
  locked_fields?: string[]
}

export interface Recipe {
  id: string
  organization: string
  location: string | null
  name: string
  description: string
  category: string | null
  output_item: string | null
  output_item_name: string | null
  output_quantity: string
  output_unit: string
  yield_percent: string
  is_active: boolean
  version: number
  ingredients: RecipeIngredient[]
  created_at: string
  updated_at: string
}

export interface RecipeCalculation {
  recipe_id: string
  recipe_name: string
  version: number
  batches: string
  yield_percent: string
  output_quantity: string | null
  output_item: string | null
  feasible: boolean
  shortfalls: Array<{
    item_id: string
    item_name: string
    required: string
    available: string
    shortfall: string
  }>
  warnings: Array<{
    item_id: string
    item_name: string
    post_deduction_stock: string
    reorder_level: string
    message: string
  }>
  estimated_cost: string
  cost_per_output: string | null
  ingredients: Array<{
    item_id: string
    item_name: string
    unit: string
    required_quantity: string
    available_raw: string
    available_reported: string
    lower_bound: string
    upper_bound: string
    shortfall: string
  }>
}

export interface RecipeVersion {
  id: string
  recipe: string
  version_number: number
  snapshot: Record<string, unknown>
  changed_by: string | null
  changed_by_email: string | null
  changed_at: string
  reason: string
}

export type ImportStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface ImportRecord {
  id: string
  organization: string
  location: string | null
  file_url: string | null
  file_name: string
  status: ImportStatus
  row_count: number
  processed_count: number
  error_count: number
  error_log: Array<{ row: number; column: string; message: string }>
  batch_id: string
  imported_at: string | null
  summary: Record<string, { name: string; sku: string; unit: string; deducted?: string; received?: string; new_stock?: string }>
  column_map: Record<string, number>
  task_id: string
  created_at: string
  updated_at: string
}

export interface SupplierImportRecord extends ImportRecord {
  supplier: string | null
}

export interface ImportPreview {
  rows: Array<{
    row_num: number
    name: string
    sku: string
    quantity: string
    unit_cost: string | null
    movement_date: string | null
    supplier_name: string
    notes: string
    errors: Array<{ row: number; column: string; message: string }>
    raw: unknown[]
  }>
  errors: Array<{ row: number; column: string; message: string }>
  column_map: Record<string, number>
  total_rows: number
  valid_rows: number
  error_rows: number
  warnings: string[]
  headers: string[]
}

export interface AuditLogEntry {
  id: string
  organization: string
  location: string | null
  action: string
  model_name: string
  object_id: string
  object_repr: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  diff: Record<string, { before: unknown; after: unknown }> | null
  performed_by: string | null
  performed_by_email: string | null
  timestamp: string
  ip_address: string | null
}

export interface StockHealthReport {
  totals: { critical: number; low: number; normal: number; overstock: number; negative: number }
  per_category: Array<{ category: string; critical: number; low: number; normal: number; overstock: number; negative: number }>
  item_count: number
}

export interface MovementTimeline {
  days: number
  series: Array<{ date: string; in: string; out: string }>
}

export interface TopConsumed {
  item_id: string
  item_name: string
  sku: string
  unit: string
  consumed: string
}

export interface AIQueryResult {
  answer: string
  confidence: number
  data_points_used: string[]
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

  reverseMovement: async (id: string, reason: string): Promise<StockMovement> => {
    const res = await api.post(`${BASE}/movements/${id}/reverse/`, { reason })
    return res.data
  },

  // Purchase Orders
  listPurchaseOrders: async (params: {
    organization?: string
    status?: POStatus
    supplier?: string
  } = {}): Promise<PurchaseOrder[]> => {
    const res = await api.get(`${BASE}/purchase-orders/`, { params })
    return unwrap<PurchaseOrder>(res.data)
  },

  getPurchaseOrder: async (id: string): Promise<PurchaseOrder> => {
    const res = await api.get(`${BASE}/purchase-orders/${id}/`)
    return res.data
  },

  createPurchaseOrder: async (
    data: Omit<Partial<PurchaseOrder>, 'items'> & { items?: Partial<PurchaseOrderItem>[] },
  ): Promise<PurchaseOrder> => {
    const res = await api.post(`${BASE}/purchase-orders/`, data)
    return res.data
  },

  updatePurchaseOrder: async (
    id: string,
    data: Omit<Partial<PurchaseOrder>, 'items'> & { items?: Partial<PurchaseOrderItem>[] },
  ): Promise<PurchaseOrder> => {
    const res = await api.patch(`${BASE}/purchase-orders/${id}/`, data)
    return res.data
  },

  receivePurchaseOrder: async (
    id: string,
    body: { line_id: string; quantity_received: string; unit_cost?: string },
  ): Promise<PurchaseOrder> => {
    const res = await api.post(`${BASE}/purchase-orders/${id}/receive/`, body)
    return res.data
  },

  cancelPurchaseOrder: async (id: string): Promise<PurchaseOrder> => {
    const res = await api.post(`${BASE}/purchase-orders/${id}/cancel/`)
    return res.data
  },

  // Recipes
  listRecipes: async (params: {
    organization?: string
    is_active?: boolean
  } = {}): Promise<Recipe[]> => {
    const res = await api.get(`${BASE}/recipes/`, { params })
    return unwrap<Recipe>(res.data)
  },

  getRecipe: async (id: string): Promise<Recipe> => {
    const res = await api.get(`${BASE}/recipes/${id}/`)
    return res.data
  },

  createRecipe: async (
    data: Omit<Partial<Recipe>, 'ingredients'> & { ingredients?: Partial<RecipeIngredient>[] },
  ): Promise<Recipe> => {
    const res = await api.post(`${BASE}/recipes/`, data)
    return res.data
  },

  updateRecipe: async (
    id: string,
    data: Omit<Partial<Recipe>, 'ingredients'> & { ingredients?: Partial<RecipeIngredient>[] },
  ): Promise<Recipe> => {
    const res = await api.patch(`${BASE}/recipes/${id}/`, data)
    return res.data
  },

  deleteRecipe: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/recipes/${id}/`)
  },

  calculateRecipe: async (id: string, batches: string): Promise<RecipeCalculation> => {
    const res = await api.post(`${BASE}/recipes/${id}/calculate/`, { batches })
    return res.data
  },

  consumeRecipe: async (id: string, batches: string): Promise<{ movements_created: number; batches: string; recipe_id: string; recipe_version: number }> => {
    const res = await api.post(`${BASE}/recipes/${id}/consume/`, { batches })
    return res.data
  },

  suggestBatches: async (id: string): Promise<{ max_batches: string }> => {
    const res = await api.get(`${BASE}/recipes/${id}/suggest_batches/`)
    return res.data
  },

  recipeVersions: async (id: string): Promise<RecipeVersion[]> => {
    const res = await api.get(`${BASE}/recipes/${id}/versions/`)
    return res.data
  },

  recipeVersionDiff: async (id: string, v1: number, v2: number) => {
    const res = await api.get(`${BASE}/recipes/${id}/version-diff/?v1=${v1}&v2=${v2}`)
    return res.data
  },

  // Imports
  uploadSalesImport: async (file: File, location?: string): Promise<ImportRecord> => {
    const fd = new FormData()
    fd.append('import_file', file)
    if (location) fd.append('location', location)
    const res = await api.post(`${BASE}/imports/sales/`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  uploadPurchaseImport: async (file: File, location?: string, supplier?: string): Promise<SupplierImportRecord> => {
    const fd = new FormData()
    fd.append('import_file', file)
    if (location) fd.append('location', location)
    if (supplier) fd.append('supplier', supplier)
    const res = await api.post(`${BASE}/imports/purchases/`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  previewImport: async (
    kind: 'sales' | 'purchases',
    id: string,
  ): Promise<ImportPreview> => {
    const res = await api.get(`${BASE}/imports/${kind}/${id}/preview/`)
    return res.data
  },

  commitImport: async (
    kind: 'sales' | 'purchases',
    id: string,
    columnMap?: Record<string, number>,
  ): Promise<ImportRecord> => {
    const res = await api.post(`${BASE}/imports/${kind}/${id}/commit/`, {
      column_map: columnMap,
    })
    return res.data
  },

  importStatus: async (
    kind: 'sales' | 'purchases',
    id: string,
  ): Promise<ImportRecord> => {
    const res = await api.get(`${BASE}/imports/${kind}/${id}/status/`)
    return res.data
  },

  // Reports
  stockHealth: async (params: { organization?: string } = {}): Promise<StockHealthReport> => {
    const res = await api.get(`${BASE}/reports/stock-health/`, { params })
    return res.data
  },

  movementTimeline: async (params: { organization?: string; days?: number } = {}): Promise<MovementTimeline> => {
    const res = await api.get(`${BASE}/reports/movement-timeline/`, { params })
    return res.data
  },

  topConsumed: async (params: { organization?: string; days?: number } = {}): Promise<TopConsumed[]> => {
    const res = await api.get(`${BASE}/reports/top-consumed/`, { params })
    return res.data
  },

  variance: async (params: { organization?: string } = {}): Promise<Array<{
    item_id: string; item_name: string; sku: string; unit: string
    reported: string; lower_bound: string; upper_bound: string
    reorder_level: string; is_critical: boolean; is_negative: boolean
  }>> => {
    const res = await api.get(`${BASE}/reports/variance/`, { params })
    return res.data
  },

  // Audit log
  listAuditLog: async (params: {
    organization?: string
    action?: string
    model_name?: string
    start?: string
    end?: string
  } = {}): Promise<AuditLogEntry[]> => {
    const res = await api.get(`${BASE}/audit-log/`, { params })
    return unwrap<AuditLogEntry>(res.data)
  },

  // AI
  aiQuery: async (question: string, organization?: string): Promise<AIQueryResult> => {
    const res = await api.post(`${BASE}/ai/query/`, { question, organization })
    return res.data
  },

  // ──────────────────────────────────────────────────────────
  // Phase 4 — bulk edit, movement export, location stock,
  // stock-take, location pricing, PO send/PDF
  // ──────────────────────────────────────────────────────────
  bulkUpdateItems: async (
    ids: string[],
    patch: Partial<{
      reorder_level: string
      reorder_quantity: string
      category: string | null
      supplier: string | null
      is_active: boolean
    }>,
  ): Promise<{ updated: number; requested: number }> => {
    const res = await api.post(`${BASE}/items/bulk-update/`, { ids, patch })
    return res.data
  },

  exportMovements: async (params: {
    item?: string; movement_type?: string
    start_date?: string; end_date?: string
    organization?: string; location?: string
  } = {}): Promise<Blob> => {
    const res = await api.get(`${BASE}/movements/export/`, {
      params, responseType: 'blob',
    })
    return res.data as Blob
  },

  itemLocationStocks: async (itemId: string): Promise<Array<{
    id: string; item: string; item_name: string; item_sku: string; item_unit: string
    location: string | null; location_name: string | null
    current_stock: string; reorder_level_override: string | null
    effective_reorder: string
  }>> => {
    const res = await api.get(`${BASE}/items/${itemId}/location-stocks/`)
    return res.data
  },

  // Stock-takes
  listStockTakes: async (params: { organization?: string; status?: string } = {}) => {
    const res = await api.get(`${BASE}/stock-takes/`, { params })
    return res.data
  },
  getStockTake: async (id: string) => {
    const res = await api.get(`${BASE}/stock-takes/${id}/`)
    return res.data
  },
  createStockTake: async (payload: {
    organization: string; location?: string | null
    name?: string; notes?: string
    lines: Array<{ item: string; system_count: string; counted: string; notes?: string }>
  }) => {
    const res = await api.post(`${BASE}/stock-takes/`, payload)
    return res.data
  },
  commitStockTake: async (id: string) => {
    const res = await api.post(`${BASE}/stock-takes/${id}/commit/`, {})
    return res.data
  },
  cancelStockTake: async (id: string) => {
    const res = await api.post(`${BASE}/stock-takes/${id}/cancel/`, {})
    return res.data
  },

  // Location pricing
  listLocationPricing: async (params: { item?: string; location?: string } = {}) => {
    const res = await api.get(`${BASE}/location-pricing/`, { params })
    return res.data
  },
  createLocationPricing: async (payload: {
    item: string; location: string
    unit_cost?: string; selling_price?: string
  }) => {
    const res = await api.post(`${BASE}/location-pricing/`, payload)
    return res.data
  },
  updateLocationPricing: async (id: string, payload: { unit_cost?: string; selling_price?: string }) => {
    const res = await api.patch(`${BASE}/location-pricing/${id}/`, payload)
    return res.data
  },
  deleteLocationPricing: async (id: string) => {
    await api.delete(`${BASE}/location-pricing/${id}/`)
  },

  // PO send / PDF
  sendPurchaseOrder: async (id: string, to_email?: string) => {
    const res = await api.post(`${BASE}/purchase-orders/${id}/send/`,
      to_email ? { to_email } : {})
    return res.data
  },
  poPdfUrl: (id: string) => `${BASE}/purchase-orders/${id}/pdf/`,
  downloadPoPdf: async (id: string): Promise<Blob> => {
    const res = await api.get(`${BASE}/purchase-orders/${id}/pdf/`, { responseType: 'blob' })
    return res.data as Blob
  },

  // ──────────────────────────────────────────────────────────
  // Phase 5 — analytics
  // ──────────────────────────────────────────────────────────
  reorderForecast: async (params: { days?: number; organization?: string } = {}) => {
    const res = await api.get(`${BASE}/reports/reorder-forecast/`, { params })
    return res.data as {
      days: number
      rows: Array<{
        item_id: string; item_name: string; sku: string; unit: string
        current_stock: string; avg_daily_consumption: string
        days_of_cover: string | null
        reorder_level: string; reorder_quantity: string
        recommended_to_reorder: boolean
      }>
    }
  },

  supplierScorecards: async (params: { organization?: string } = {}) => {
    const res = await api.get(`${BASE}/reports/supplier-scorecards/`, { params })
    return res.data as Array<{
      supplier_id: string; supplier_name: string
      po_count: number
      avg_lead_time_days: number | null
      receive_accuracy_percent: number | null
      total_spend: string
    }>
  },

  recipeProfitability: async (params: { organization?: string } = {}) => {
    const res = await api.get(`${BASE}/reports/recipe-profitability/`, { params })
    return res.data as Array<{
      recipe_id: string; recipe_name: string
      output_item: string; output_unit: string
      selling_price: string; cost_per_unit: string
      margin_per_unit: string; margin_percent: number | null
    }>
  },

  wasteAnalysis: async (params: { days?: number; organization?: string } = {}) => {
    const res = await api.get(`${BASE}/reports/waste-analysis/`, { params })
    return res.data as {
      days: number
      top_items: Array<{ item_id: string; item_name: string; sku: string; unit: string; wasted: string; event_count: number }>
      by_week: Array<{ week: string; wasted: string }>
    }
  },

  weeklyInsights: async (params: { organization?: string } = {}) => {
    const res = await api.get(`${BASE}/reports/weekly-insights/`, { params })
    return res.data as { answer: string; confidence: number; data_points_used: string[] }
  },
}
