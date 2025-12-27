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
  conversation: Conversation;
  alert_type: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  reason: string;
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
