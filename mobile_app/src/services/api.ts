import AsyncStorage from '@react-native-async-storage/async-storage';
import { User, ServiceItem, CartItem, BillRecord, StockItem, SalesSummary, PrinterStatusInfo, PrintJob } from '../types';

const STORAGE_SERVER_URL = '@iread_server_url';
const STORAGE_TOKEN = '@iread_token';
const STORAGE_USER = '@iread_user';

// Default to local server URL (works on LAN or emulator)
const DEFAULT_SERVER_URL = 'http://127.0.0.1:5000';

class ApiService {
  private serverUrl: string = DEFAULT_SERVER_URL;
  private token: string | null = null;

  async init() {
    try {
      const storedUrl = await AsyncStorage.getItem(STORAGE_SERVER_URL);
      if (storedUrl) {
        this.serverUrl = storedUrl.trim().replace(/\/+$/, '');
      }
      const storedToken = await AsyncStorage.getItem(STORAGE_TOKEN);
      if (storedToken) {
        this.token = storedToken;
      }
    } catch (e) {
      console.warn('Failed to load initial settings from storage:', e);
    }
  }

  getServerUrl(): string {
    return this.serverUrl;
  }

  async setServerUrl(url: string) {
    this.serverUrl = url.trim().replace(/\/+$/, '');
    await AsyncStorage.setItem(STORAGE_SERVER_URL, this.serverUrl);
  }

  getToken(): string | null {
    return this.token;
  }

  async setToken(token: string | null) {
    this.token = token;
    if (token) {
      await AsyncStorage.setItem(STORAGE_TOKEN, token);
    } else {
      await AsyncStorage.removeItem(STORAGE_TOKEN);
    }
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.serverUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
      headers['X-Auth-Token'] = this.token;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.error || `Server returned error HTTP ${response.status}`);
      }

      return data as T;
    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Network request failed')) {
        throw new Error(`Cannot connect to server at ${this.serverUrl}. Please check Wi-Fi connection and server IP.`);
      }
      throw error;
    }
  }

  async testConnection(): Promise<{ ok: boolean; status?: string; error?: string }> {
    try {
      const data = await this.request<{ success: boolean; status: string }>('/api/printer/status');
      return { ok: true, status: data.status };
    } catch (err: any) {
      return { ok: false, error: err.message };
    }
  }

  async login(username: string, password: string): Promise<{ user: User; token: string }> {
    const data = await this.request<{ success: boolean; token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });

    if (data.success && data.token) {
      await this.setToken(data.token);
      await AsyncStorage.setItem(STORAGE_USER, JSON.stringify(data.user));
      return { user: data.user, token: data.token };
    }
    throw new Error('Login failed: invalid response.');
  }

  async logout() {
    await this.setToken(null);
    await AsyncStorage.removeItem(STORAGE_USER);
  }

  async getStoredUser(): Promise<User | null> {
    const raw = await AsyncStorage.getItem(STORAGE_USER);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async getServices(): Promise<ServiceItem[]> {
    const data = await this.request<{ success: boolean; services: ServiceItem[] }>('/api/services');
    return data.services || [];
  }

  async createBill(payload: {
    customer: string;
    payment_method: string;
    payment_status: 'Paid' | 'Unpaid';
    discount: number;
    paid: number;
    action: 'save_only' | 'save_and_print';
    items: {
      service_id: number | 'custom';
      service_name: string;
      quantity: number;
      pages_per_copy?: number;
      sides: 'Single' | 'Double';
      rate: number;
      line_total: number;
    }[];
    notes?: string;
  }): Promise<{
    success: boolean;
    bill_id: number;
    bill_no: string;
    total: number;
    paid: number;
    balance: number;
    payment_status: string;
    action: string;
    print_job?: PrintJob;
  }> {
    return await this.request('/api/create-bill', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getPrintJob(jobId: string): Promise<PrintJob> {
    const data = await this.request<{ success: boolean; job: PrintJob }>(`/api/print-jobs/${encodeURIComponent(jobId)}`);
    return data.job;
  }

  async retryPrintJob(jobId: string): Promise<PrintJob> {
    const data = await this.request<{ success: boolean; job: PrintJob }>(`/api/print-jobs/${encodeURIComponent(jobId)}/retry`, {
      method: 'POST',
    });
    return data.job;
  }

  async getSales(): Promise<SalesSummary> {
    return await this.request<SalesSummary>('/api/staff/sales');
  }

  async getStock(): Promise<StockItem[]> {
    const data = await this.request<{ success: boolean; items: StockItem[] }>('/api/staff/stock');
    return data.items || [];
  }

  async getPrinterStatus(): Promise<PrinterStatusInfo> {
    return await this.request<PrinterStatusInfo>('/api/printer/status');
  }
}

export const api = new ApiService();
