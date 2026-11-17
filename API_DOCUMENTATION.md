# Iread Billing — Complete REST API & Integration Specification

This document details all backend APIs implemented for staff mobile billing, PC-based Wi-Fi thermal printer integration, and administrative controls.

---

## 1. Authentication & Security

### Token Format
Stateless, signed HMAC-SHA256 bearer tokens with 30-day expiration.
Included in requests via header:
```http
Authorization: Bearer <TOKEN>
# or
X-Auth-Token: <TOKEN>
```

---

### POST `/api/auth/login`
Authenticates staff or admin users and issues an API token.

**Request Body:**
```json
{
  "username": "staff",
  "password": "iread@staff123"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "token": "eyJ1aWQiOjIsInVzZXJuYW1lIjoic3RhZmYiLCJyb2xlIjoic3RhZmYiLCJuYW1lIjoiU3RhZmYgQ291bnRlciIsImV4cCI6MTc5NzI3MjA2MX0.97a9f6...",
  "user": {
    "id": 2,
    "username": "staff",
    "role": "staff",
    "name": "Staff Counter"
  }
}
```

---

### GET `/api/auth/me`
Returns the authenticated user profile.
- **Required Header:** `Authorization: Bearer <TOKEN>`

**Response (200 OK):**
```json
{
  "success": true,
  "user": {
    "uid": 2,
    "username": "staff",
    "role": "staff",
    "name": "Staff Counter",
    "exp": 1797272061
  }
}
```

---

## 2. Services & Catalog

### GET `/api/services`
Retrieves all active services and pricing configuration.

**Response (200 OK):**
```json
{
  "success": true,
  "services": [
    {
      "id": 52,
      "name": "Print B&W — A4",
      "rate": 10.0,
      "double_rate": 15.0,
      "extra_copy_rate": 5.0,
      "print_type": "bw",
      "paper_size": "A4",
      "sheets_per_unit": 1,
      "paper_id": 1
    },
    {
      "id": 1,
      "name": "Photostat B&W — A4",
      "rate": 2.0,
      "double_rate": 3.0,
      "extra_copy_rate": null,
      "print_type": "bw",
      "paper_size": "A4",
      "sheets_per_unit": 1,
      "paper_id": 1
    }
  ]
}
```

---

## 3. High-Speed Billing & Thermal Print Trigger

### POST `/api/create-bill`
Creates a bill, deducts paper stock from inventory, logs stock movement, and optionally queues a thermal print job.

- **Required Header:** `Authorization: Bearer <TOKEN>`

**Request Body (Save & Print):**
```json
{
  "customer": "John Doe",
  "payment_method": "Cash",
  "payment_status": "Paid",
  "discount": 5.0,
  "paid": 45.0,
  "action": "save_and_print",
  "notes": "Fast counter checkout",
  "items": [
    {
      "service_id": 52,
      "service_name": "Print B&W — A4",
      "quantity": 5,
      "pages_per_copy": 1,
      "sides": "Single",
      "rate": 6.0,
      "line_total": 30.0
    },
    {
      "service_id": 1,
      "service_name": "Photostat B&W — A4",
      "quantity": 10,
      "pages_per_copy": 1,
      "sides": "Double",
      "rate": 2.0,
      "line_total": 20.0
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "bill_id": 204,
  "bill_no": "IR261117134512",
  "subtotal": 50.0,
  "discount": 5.0,
  "total": 45.0,
  "paid": 45.0,
  "balance": 0.0,
  "payment_status": "Paid",
  "action": "save_and_print",
  "print_job": {
    "job_id": "PJ261117134512_204",
    "status": "Print Pending",
    "thermal_width": "80mm",
    "attempts": 0
  }
}
```

---

## 4. Print Job Queue & Status Polling

### GET `/api/print-jobs/<job_id>`
Polls the live execution status of a thermal print job.

**Response (200 OK):**
```json
{
  "success": true,
  "job": {
    "job_id": "PJ261117134512_204",
    "bill_id": 204,
    "bill_no": "IR261117134512",
    "status": "Printed",
    "printer_name": "POS-80",
    "thermal_width": "80mm",
    "attempts": 1,
    "error_message": "",
    "printed_by": "Staff Counter",
    "created_at": "2026-11-17T13:45:12",
    "updated_at": "2026-11-17T13:45:14"
  }
}
```

---

### POST `/api/print-jobs/<job_id>/retry`
Idempotently requeues a failed print job back to `Print Pending`.

**Response (200 OK):**
```json
{
  "success": true,
  "job": {
    "job_id": "PJ261117134512_204",
    "status": "Print Pending",
    "attempts": 1,
    "error_message": ""
  }
}
```

---

## 5. Staff Views (Strict Role Separation)

### GET `/api/staff/sales`
Provides daily sales totals and recent 20 bills.
*Crucial Security:* Strictly does NOT return `paper_cost`, `profit`, or purchase cost metrics.

**Response (200 OK):**
```json
{
  "success": true,
  "today_date": "2026-11-17",
  "today_sales": 1250.0,
  "today_bill_count": 18,
  "bills": [
    {
      "id": 204,
      "bill_no": "IR261117134512",
      "customer": "John Doe",
      "total": 45.0,
      "paid": 45.0,
      "balance": 0.0,
      "payment_status": "Paid",
      "payment_method": "Cash",
      "biller_name": "Staff Counter",
      "created_at": "2026-11-17T13:45:12"
    }
  ]
}
```

---

### GET `/api/staff/stock`
Returns available inventory sheet counts and low-stock alerts.
*Crucial Security:* Strictly does NOT return paper unit purchase costs or supplier margins.

**Response (200 OK):**
```json
{
  "success": true,
  "items": [
    {
      "id": 1,
      "item_name": "A4 75 GSM (JK Copier)",
      "category": "Paper",
      "size_spec": "A4",
      "bundles": 10,
      "sheets_per_bundle": 500,
      "total_sheets": 5000,
      "available_sheets": 4820,
      "reorder_level": 500,
      "is_low_stock": false
    }
  ]
}
```

---

## 6. PC Print Service Endpoints

Protected by header: `X-Printer-Token: <PRINTER_API_KEY>` (or Admin Bearer token).

### POST `/api/printer/heartbeat`
Counter PC daemon pings every 10 seconds.
```json
{
  "hostname": "COUNTER-PC",
  "os": "macOS 14.6",
  "printer_name": "POS-80",
  "version": "2.0.0",
  "status": "online"
}
```

---

### GET `/api/printer/pending-jobs`
Counter PC fetches pending jobs. The backend automatically marks them as `Printing` atomically.

---

### POST `/api/printer/jobs/<job_id>/status`
Counter PC reports print outcome:
```json
{
  "status": "Printed",
  "printer_name": "POS-80"
}
```
Or in case of paper jam or error:
```json
{
  "status": "Print Failed",
  "error_message": "Printer offline or out of paper."
}
```

---

### GET `/api/printer/status`
Returns live PC Print Service health, online/offline status, and active hardware settings.
