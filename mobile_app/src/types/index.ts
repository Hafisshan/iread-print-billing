export interface User {
  id: number;
  username: string;
  role: 'admin' | 'staff';
  name: string;
}

export interface ServiceItem {
  id: number;
  name: string;
  rate: number;
  double_rate: number | null;
  extra_copy_rate: number | null;
  print_type: string;
  paper_size: string;
  sheets_per_unit: number;
  paper_id: number | null;
}

export interface CartItem {
  service_id: number | 'custom';
  service_name: string;
  quantity: number;
  pages_per_copy: number;
  sides: 'Single' | 'Double';
  rate: number;
  line_total: number;
  paper_size: string;
  print_type: string;
}

export interface PrintJob {
  job_id: string;
  bill_id?: number;
  bill_no?: string;
  status: 'Print Pending' | 'Printing' | 'Printed' | 'Print Failed';
  printer_name?: string;
  thermal_width?: string;
  attempts?: number;
  error_message?: string;
  created_at?: string;
  updated_at?: string;
}

export interface BillRecord {
  id: number;
  bill_no: string;
  created_at: string;
  customer: string;
  subtotal: number;
  discount: number;
  total: number;
  paid: number;
  balance: number;
  payment_status: 'Paid' | 'Unpaid' | 'Partially Paid';
  payment_method: string;
  biller_name: string;
}

export interface StockItem {
  id: number;
  item_name: string;
  category: string;
  size_spec: string;
  bundles: number;
  sheets_per_bundle: number;
  total_sheets: number;
  available_sheets: number;
  reorder_level: number;
  is_low_stock: boolean;
}

export interface SalesSummary {
  today_date: string;
  today_sales: number;
  today_bill_count: number;
  bills: BillRecord[];
}

export interface PrinterStatusInfo {
  is_online: boolean;
  status: 'online' | 'offline';
  last_seen: string;
  default_printer: string;
  thermal_width: string;
  pending_count: number;
  failed_count: number;
  pc_info?: {
    hostname?: string;
    os?: string;
    printer_name?: string;
    version?: string;
  };
}
