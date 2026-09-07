const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "https://quantgrid.info/foodtruck-api";

export type Dashboard = {
  sales: number;
  food_cost: number;
  orders: number;
  expenses: number;
  profit: number;
  avg_order: number;
  cash_sales: number;
  upi_sales: number;
  razorpay_sales: number;
  cash_expenses: number;
  upi_expenses: number;
  cash_balance: number;
  target: number;
};

export type OrderItem = {
  name: string;
  quantity: number;
  price: number;
};

export type Order = {
  id: number;
  order_number: string;
  payment_method: string;
  status: string;
  total: number;
  food_cost: number;
  created_at: string;
  items: OrderItem[];
};

export type Expense = {
  id: number;
  category: string;
  description: string | null;
  amount: number;
  payment_method: string;
  created_at: string;
};

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json();
}

export function getDashboard() {
  return request<Dashboard>("/dashboard");
}

export function getOrders() {
  return request<Order[]>("/orders");
}

export function getExpenses() {
  return request<Expense[]>("/expenses");
}


export type RazorpayCreateOrderResponse = {
  order_id: number;
  order_number: string;
  razorpay_order_id: string;
  razorpay_key_id: string;
  amount: number;
  currency: string;
  total: number;
};

export type RazorpayVerifyResponse = {
  success: boolean;
  status: string;
  payment_id: string;
  order_id: number;
};

export function createRazorpayOrder(payload: {
  items: {
    name: string;
    quantity: number;
  }[];
}) {
  return request<RazorpayCreateOrderResponse>(
    "/payments/create-order",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function verifyRazorpayPayment(payload: {
  order_id: number;
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}) {
  return request<RazorpayVerifyResponse>(
    "/payments/verify",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function createOrder(payload: {
  payment_method: string;
  items: {
    name: string;
    quantity: number;
    price: number;
    food_cost: number;
  }[];
}) {
  return request("/orders", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createExpense(payload: {
  category: string;
  description?: string;
  amount: number;
  payment_method: string;
}) {
  return request("/expenses", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
