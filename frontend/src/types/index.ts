// API Types for the Chat Platform

export interface User {
  id: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  phone: string;
  date_joined: string;
  organizations?: OrganizationMembership[];
}

export interface Organization {
  id: string;
  name: string;
  business_type: 'restaurant' | 'real_estate';
  plan: 'basic' | 'power';
  email: string;
  phone: string;
  website: string;
  widget_key: string;
  widget_color: string;
  widget_position: string;
  widget_greeting: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  locations: Location[];
  locations_count: number;
  is_power_plan: boolean;
}

export interface Location {
  id: string;
  name: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  email: string;
  phone: string;
  timezone: string;
  is_primary: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrganizationMembership {
  id: string;
  name: string;
  business_type: string;
  role: 'owner' | 'manager';
}

export interface Conversation {
  id: string;
  organization: string;
  location: string | null;
  location_name: string | null;
  channel: 'website' | 'whatsapp' | 'instagram';
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  customer_metadata: Record<string, unknown>;
  state: ConversationState;
  assigned_to: string | null;
  assigned_to_name: string | null;
  intent: string;
  sentiment: string;
  tags: string[];
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  resolved_at: string | null;
  messages_count: number;
  unread_count: number;
  last_message: {
    content: string;
    sender: MessageSender;
    created_at: string;
  } | null;
  messages?: Message[];
}

export type ConversationState =
  | 'new'
  | 'ai_handling'
  | 'awaiting_user'
  | 'human_handoff'
  | 'resolved'
  | 'archived';

export interface Message {
  id: string;
  content: string;
  sender: MessageSender;
  sent_by: string | null;
  sent_by_name: string | null;
  confidence_score: number | null;
  intent: string;
  ai_metadata: Record<string, unknown>;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export type MessageSender = 'customer' | 'ai' | 'human' | 'system';

export interface HandoffAlert {
  id: string;
  conversation: string;
  conversation_customer_name: string | null;
  conversation_channel: string;
  alert_type: string;
  type: string;  // alias for alert_type
  priority: 'low' | 'medium' | 'high' | 'urgent';
  reason: string;
  status: 'pending' | 'acknowledged' | 'resolved';
  trigger_message: string | null;
  is_acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_by_name: string | null;
  acknowledged_at: string | null;
  is_resolved: boolean;
  resolved_by: string | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  resolution_notes: string;
  created_at: string;
}

export interface KnowledgeBase {
  id: string;
  organization: string;
  location: string | null;
  location_name: string | null;
  business_description: string;
  opening_hours: Record<string, { open: string; close: string }>;
  contact_info: Record<string, string>;
  services: string[];
  additional_info: string;
  policies: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface FAQ {
  id: string;
  organization: string;
  location: string | null;
  question: string;
  answer: string;
  category: string;
  tags: string[];
  order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AnalyticsOverview {
  period: {
    days: number;
    start: string;
    end: string;
  };
  conversations: {
    total: number;
    by_state: Record<string, number>;
  };
  messages: {
    total: number;
    customer: number;
    ai: number;
    human: number;
  };
  handoffs: {
    total: number;
    resolved: number;
    pending: number;
  };
  avg_response_time_seconds: number | null;
  restaurant?: {
    bookings?: {
      total: number;
      confirmed: number;
      completed: number;
      cancelled: number;
      no_shows: number;
      total_guests: number;
      by_source?: Record<string, number>;
    };
  };
  real_estate?: {
    leads?: {
      total: number;
      by_status?: Record<string, number>;
      by_intent?: Record<string, number>;
      avg_score: number;
      conversion_rate: number;
    };
    appointments?: {
      total: number;
      by_status?: Record<string, number>;
    };
    properties?: {
      active_listings: number;
      sold_in_period: number;
    };
  };
}

export interface ChannelStats {
  channel: 'website' | 'whatsapp' | 'instagram';
  conversations: number;
  messages: number;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  password: string;
  password_confirm: string;
}

// ============================================
// Restaurant Vertical Types
// ============================================

export interface MenuCategory {
  id: string;
  organization: string;
  location: string | null;
  location_name: string | null;
  name: string;
  description: string;
  display_order: number;
  is_active: boolean;
  items?: MenuItem[];
  items_count: number;
  created_at: string;
  updated_at: string;
}

export interface MenuItem {
  id: string;
  category: string;
  category_name: string;
  name: string;
  description: string;
  price: string;
  dietary_info: string[];
  prep_time_minutes: number | null;
  image_url: string;
  display_order: number;
  is_available: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OpeningHours {
  id: string;
  location: string;
  day_of_week: number;
  day_name: string;
  open_time: string | null;
  close_time: string | null;
  open_time_2: string | null;
  close_time_2: string | null;
  is_closed: boolean;
  created_at: string;
  updated_at: string;
}

export interface DailySpecial {
  id: string;
  organization: string;
  location: string | null;
  location_name: string | null;
  name: string;
  description: string;
  price: string;
  original_price: string | null;
  discount_percentage: number | null;
  start_date: string;
  end_date: string;
  recurring_days: number[];
  is_active: boolean;
  is_available_today: boolean;
  created_at: string;
  updated_at: string;
}

export interface Booking {
  id: string;
  organization: string;
  location: string;
  location_name: string;
  conversation: string | null;
  booking_date: string;
  booking_time: string;
  party_size: number;
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  special_requests: string;
  status: 'pending' | 'confirmed' | 'cancelled' | 'completed' | 'no_show';
  status_display: string;
  source: 'website' | 'whatsapp' | 'phone' | 'walk_in' | 'other';
  source_display: string;
  confirmation_code: string;
  confirmed_at: string | null;
  confirmed_by: string | null;
  confirmed_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  internal_notes: string;
  created_at: string;
  updated_at: string;
}

export interface BookingSettings {
  id: string;
  location: string;
  location_name: string;
  max_party_size: number;
  max_bookings_per_slot: number;
  total_capacity: number;
  slot_duration_minutes: number;
  booking_buffer_minutes: number;
  min_advance_hours: number;
  max_advance_days: number;
  auto_confirm: boolean;
  cancellation_hours: number;
  created_at: string;
  updated_at: string;
}

export interface BookingSlot {
  time: string;
  available: boolean;
  remaining: number;
}

export interface BookingAvailability {
  date: string;
  day: string;
  opening_time: string;
  closing_time: string;
  available_slots: BookingSlot[];
}

// ============================================
// Real Estate Vertical Types
// ============================================

export interface PropertyListing {
  id: string;
  organization: string;
  listing_type: 'sale' | 'rent';
  property_type: 'house' | 'apartment' | 'condo' | 'townhouse' | 'land' | 'commercial';
  title: string;
  description: string;
  price: string;
  bedrooms: number;
  bathrooms: string;
  square_feet: number | null;
  lot_size: number | null;
  year_built: number | null;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  latitude: string | null;
  longitude: string | null;
  features: string[];
  images: string[];
  virtual_tour_url: string;
  status: 'draft' | 'active' | 'pending' | 'sold' | 'rented' | 'off_market';
  status_display: string;
  is_featured: boolean;
  reference_number: string;
  listed_date: string | null;
  sold_date: string | null;
  sold_price: string | null;
  assigned_agent: string | null;
  assigned_agent_name: string | null;
  view_count: number;
  inquiry_count: number;
  created_at: string;
  updated_at: string;
}

export interface Lead {
  id: string;
  organization: string;
  conversation: string | null;
  name: string;
  email: string;
  phone: string;
  intent: 'buy' | 'rent' | 'sell' | 'invest' | 'other';
  intent_display: string;
  status: 'new' | 'contacted' | 'qualified' | 'negotiating' | 'converted' | 'lost';
  status_display: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  priority_display: string;
  budget_min: number | null;
  budget_max: number | null;
  preferred_areas: string[];
  property_type_preference: string;
  bedrooms_min: number | null;
  bedrooms_max: number | null;
  timeline: string;
  notes: string;
  source: 'website' | 'whatsapp' | 'referral' | 'advertising' | 'phone' | 'other';
  source_display: string;
  lead_score: number;
  qualification_data: Record<string, unknown>;
  interested_properties: PropertyListing[];
  assigned_agent: string | null;
  assigned_agent_name: string | null;
  last_contact_at: string | null;
  next_follow_up: string | null;
  created_at: string;
  updated_at: string;
}

export interface Appointment {
  id: string;
  lead: string;
  lead_name: string;
  property: string | null;
  property_title: string | null;
  property_address: string | null;
  appointment_date: string;
  appointment_time: string;
  duration_minutes: number;
  appointment_type: 'in_person' | 'virtual' | 'phone';
  appointment_type_display: string;
  status: 'scheduled' | 'confirmed' | 'completed' | 'cancelled' | 'no_show';
  status_display: string;
  confirmation_code: string;
  notes: string;
  outcome_notes: string;
  assigned_agent: string | null;
  assigned_agent_name: string | null;
  confirmed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  created_at: string;
  updated_at: string;
}

export interface LeadStats {
  total: number;
  by_status: Record<string, number>;
  by_intent: Record<string, number>;
  by_source: Record<string, number>;
  conversion_rate: number;
}

export interface BookingStats {
  total: number;
  by_status: Record<string, number>;
  by_source: Record<string, number>;
  total_guests: number;
}
