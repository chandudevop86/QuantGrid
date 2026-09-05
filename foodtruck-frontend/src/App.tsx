import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const API = '/foodtruck-api'

type MenuItem = {
  id: string
  name: string
  price: number
  image: string
  available: boolean
}

type CartItem = MenuItem & {
  quantity: number
}

type CustomerOrder = {
  id: number
  order_number: string
  customer_name?: string
  phone?: string
  payment_method: string
  status: string
  total: number
  food_cost: number
  created_at: string
  items: {
    name: string
    quantity: number
    price: number
  }[]
}

type Expense = {
  id: number
  category: string
  description: string | null
  amount: number
  payment_method: string
  created_at: string
}

type StockItem = {
  id: string
  name: string
  quantity: number
  unit: string
  minimum_quantity: number
}

type RazorpayCheckoutOptions = {
  key: string
  amount: number
  currency: string
  name: string
  description: string
  order_id: string
  prefill?: {
    name?: string
    contact?: string
  }
  notes?: Record<string, string>
  theme?: {
    color?: string
  }
  handler: (response: {
    razorpay_order_id: string
    razorpay_payment_id: string
    razorpay_signature: string
  }) => void
  modal?: {
    ondismiss?: () => void
  }
}

type RazorpayInstance = {
  open: () => void
}

declare global {
  interface Window {
    Razorpay: new (
      options: RazorpayCheckoutOptions,
    ) => RazorpayInstance
  }
}

type Dashboard = {
  sales: number
  food_cost: number
  orders: number
  expenses: number
  profit: number
  avg_order: number
  cash_sales: number
  upi_sales: number
  razorpay_sales: number
  cash_expenses: number
  upi_expenses: number
  cash_balance: number
  target: number
}

const INITIAL_MENU: MenuItem[] = [
  {
    id: 'idli',
    name: 'Idli',
    price: 40,
    image: 'idli_plate_chutney_sambar.jpg',
    available: true,
  },
  {
    id: 'upma',
    name: 'Upma',
    price: 40,
    image: 'suji_upma_breakfast.jpg',
    available: true,
  },
  {
    id: 'vada',
    name: 'Vada',
    price: 40,
    image: 'medu_vada_sambar_chutney.jpg',
    available: true,
  },
  {
    id: 'mysore-bajji',
    name: 'Mysore Bajji',
    price: 40,
    image: 'mysore_bonda_bajji.jpg',
    available: true,
  },
  {
    id: 'plain-dosa',
    name: 'Plain Dosa',
    price: 40,
    image: 'plain_crispy_dosa.jpg',
    available: true,
  },
  {
    id: 'puri',
    name: 'Puri',
    price: 40,
    image: 'puri_aloo_curry.jpg',
    available: true,
  },
  {
    id: 'ghee-karam',
    name: 'Ghee Karam',
    price: 60,
    image: 'ghee_karam_dosa.jpg',
    available: true,
  },
  {
    id: 'ghee-onion',
    name: 'Ghee Onion',
    price: 60,
    image: 'ghee_onion_dosa.jpg',
    available: true,
  },
  {
    id: 'paneer-dosa',
    name: 'Paneer Dosa',
    price: 60,
    image: 'paneer_masala_dosa.jpg',
    available: true,
  },
  {
    id: 'upma-pesara',
    name: 'Upma Pesara',
    price: 60,
    image: 'pesarattu_upma.jpg',
    available: true,
  },
  {
    id: 'onion-pesara',
    name: 'Onion Pesara',
    price: 60,
    image: 'onion_pesarattu.jpg',
    available: true,
  },
  {
    id: 'upma-dosa',
    name: 'Upma Dosa',
    price: 50,
    image: 'upma_filled_dosa.jpg',
    available: true,
  },
  {
    id: 'rava-dosa',
    name: 'Rava Dosa',
    price: 50,
    image: 'crispy_rava_dosa.jpg',
    available: true,
  },
  {
    id: 'onion-dosa',
    name: 'Onion Dosa',
    price: 50,
    image: 'onion_dosa_roast.jpg',
    available: true,
  },
  {
    id: 'masala-dosa',
    name: 'Masala Dosa',
    price: 50,
    image: 'masala_dosa.jpg',
    available: true,
  },
  {
    id: 'pesara',
    name: 'Pesara',
    price: 50,
    image: 'pesarattu.jpg',
    available: true,
  },
]

function money(value: number) {
  return `₹${Number(value || 0).toFixed(2)}`
}

function imageUrl(filename: string) {
  return `/foodtruck/images/${filename}`
}

function App() {
  const isOwnerPage =
    window.location.pathname.replace(/\/+$/, '') ===
    '/foodtruck/owner'

  return isOwnerPage ? <OwnerPage /> : <CustomerPage />
}

/* =========================================================
   CUSTOMER PAGE
   ========================================================= */

function CustomerPage() {
  const [menu, setMenu] = useState<MenuItem[]>(INITIAL_MENU)
  const [cart, setCart] = useState<CartItem[]>([])

  const [customerName, setCustomerName] = useState('')
  const [phone, setPhone] = useState('')

  const [payment, setPayment] =
    useState<'CASH' | 'UPI' | 'RAZORPAY'>('CASH')

  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [orderPopup, setOrderPopup] = useState('')

  useEffect(() => {
    loadMenu()
  }, [])

  async function loadMenu() {
    try {
      const response = await fetch(`${API}/menu`)

      if (!response.ok) {
        return
      }

      const data = await response.json()

      if (Array.isArray(data)) {
        setMenu(
          INITIAL_MENU.map((item) => {
            const backendItem = data.find(
              (x) =>
                x.id === item.id ||
                x.name?.toLowerCase() ===
                  item.name.toLowerCase(),
            )

            return backendItem
              ? {
                  ...item,
                  available:
                    backendItem.available !== false,
                }
              : item
          }),
        )
      }
    } catch (error) {
      console.log('Menu API unavailable; using local menu.')
    }
  }

  const availableMenu = menu.filter(
    (item) => item.available,
  )

  const cartTotal = useMemo(
    () =>
      cart.reduce(
        (total, item) =>
          total + item.price * item.quantity,
        0,
      ),
    [cart],
  )

  const selectedCount = useMemo(
    () =>
      cart.reduce(
        (total, item) => total + item.quantity,
        0,
      ),
    [cart],
  )

  function addItem(item: MenuItem) {
    setCart((current) => {
      const existing = current.find(
        (x) => x.id === item.id,
      )

      if (existing) {
        return current.map((x) =>
          x.id === item.id
            ? {
                ...x,
                quantity: x.quantity + 1,
              }
            : x,
        )
      }

      return [
        ...current,
        {
          ...item,
          quantity: 1,
        },
      ]
    })
  }

  function increaseItem(id: string) {
    setCart((current) =>
      current.map((item) =>
        item.id === id
          ? {
              ...item,
              quantity: item.quantity + 1,
            }
          : item,
      ),
    )
  }

  function decreaseItem(id: string) {
    setCart((current) =>
      current
        .map((item) =>
          item.id === id
            ? {
                ...item,
                quantity: item.quantity - 1,
              }
            : item,
        )
        .filter((item) => item.quantity > 0),
    )
  }

  function quantityFor(id: string) {
    return (
      cart.find((item) => item.id === id)
        ?.quantity || 0
    )
  }

  async function submitOrder(
    event: FormEvent,
  ) {
    event.preventDefault()

    if (!customerName.trim()) {
      setMessage('Please enter customer name.')
      return
    }

    if (!phone.trim()) {
      setMessage('Please enter phone number.')
      return
    }

    if (cart.length === 0) {
      setMessage('Please select at least one item.')
      return
    }

    setSubmitting(true)
    setMessage('')

    try {
      if (payment === 'RAZORPAY') {
        const createResponse = await fetch(
          `${API}/payments/create-order`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              items: cart.map((item) => ({
                name: item.name,
                quantity: item.quantity,
              })),
            }),
          },
        )

        const createData =
          await createResponse.json()

        if (!createResponse.ok) {
          throw new Error(
            createData.detail ||
              'Unable to create Razorpay order',
          )
        }

        if (!window.Razorpay) {
          throw new Error(
            'Razorpay Checkout failed to load. Please refresh and try again.',
          )
        }

        const razorpay = new window.Razorpay({
          key: createData.key_id,
          amount: createData.amount,
          currency: createData.currency,
          name: 'KS Foods',
          description: `Food Order ${createData.order_number}`,
          order_id: createData.razorpay_order_id,
          prefill: {
            name: customerName.trim(),
            contact: phone.trim(),
          },
          notes: {
            local_order_id: String(
              createData.order_id,
            ),
            local_order_number:
              createData.order_number,
          },
          handler: async (response) => {
            try {
              setMessage(
                'Payment received. Verifying payment...',
              )

              const verifyResponse =
                await fetch(
                  `${API}/payments/verify`,
                  {
                    method: 'POST',
                    headers: {
                      'Content-Type':
                        'application/json',
                    },
                    body: JSON.stringify({
                      order_id:
                        createData.order_id,
                      razorpay_order_id:
                        response.razorpay_order_id,
                      razorpay_payment_id:
                        response.razorpay_payment_id,
                      razorpay_signature:
                        response.razorpay_signature,
                    }),
                  },
                )

              const verifyData =
                await verifyResponse.json()

              if (!verifyResponse.ok) {
                throw new Error(
                  verifyData.detail ||
                    'Payment verification failed',
                )
              }

              if (
                !verifyData.success ||
                verifyData.status !==
                  'COMPLETED'
              ) {
                throw new Error(
                  'Payment could not be confirmed.',
                )
              }

              setOrderPopup(
                String(
                  createData.order_number,
                ),
              )

              setMessage(
                'Payment successful. Order confirmed.',
              )

              setCart([])
              setCustomerName('')
              setPhone('')
              setPayment('CASH')
            } catch (error) {
              setMessage(
                error instanceof Error
                  ? error.message
                  : 'Payment verification failed',
              )
            } finally {
              setSubmitting(false)
            }
          },
          modal: {
            ondismiss: () => {
              setSubmitting(false)
              setMessage(
                'Payment cancelled. Your order was not completed.',
              )
            },
          },
        })

        razorpay.open()
        return
      }

      const response = await fetch(
        `${API}/orders`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            customer_name:
              customerName.trim(),
            phone: phone.trim(),
            payment_method: payment,
            items: cart.map((item) => ({
              name: item.name,
              quantity: item.quantity,
              price: item.price,
              food_cost: 0,
            })),
          }),
        },
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(
          data.detail || 'Order submission failed',
        )
      }

      const orderId =
        data.order_number ||
        data.order_id ||
        data.id

      setOrderPopup(String(orderId))
      setMessage(
        'Order submitted successfully.',
      )

      setCart([])
      setCustomerName('')
      setPhone('')
      setPayment('CASH')
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Order submission failed',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="app customer-page">
      <header className="topbar">
        <div>
          <h1>KS Foods</h1>
          <p>
            Fresh • Fast • Telugu Tiffins
          </p>
        </div>

        <a
          className="owner-link"
          href="/foodtruck/owner"
        >
          Owner
        </a>
      </header>

      <main>
        <section className="customer-details panel">
          <h2>Customer Details</h2>

          <div className="customer-grid">
            <input
              placeholder="Customer Name"
              value={customerName}
              onChange={(event) =>
                setCustomerName(
                  event.target.value,
                )
              }
            />

            <input
              placeholder="Phone Number"
              type="tel"
              value={phone}
              onChange={(event) =>
                setPhone(event.target.value)
              }
            />
          </div>
        </section>

        <section className="menu-section">
          <div className="section-header">
            <div>
              <h2>KS Foods Menu</h2>
              <p>
                {selectedCount} selected
              </p>
            </div>
          </div>

          <div className="menu-grid">
            {availableMenu.map((item) => {
              const quantity =
                quantityFor(item.id)

              return (
                <article
                  className={`menu-card ${
                    quantity > 0
                      ? 'selected'
                      : ''
                  }`}
                  key={item.id}
                >
                  <button
                    className="menu-image-button"
                    type="button"
                    onClick={() =>
                      addItem(item)
                    }
                  >
                    <img
                      src={imageUrl(item.image)}
                      alt={item.name}
                    />
                  </button>

                  <div className="menu-info">
                    <h3>{item.name}</h3>

                    <strong>
                      {money(item.price)}
                    </strong>

                    {quantity === 0 ? (
                      <button
                        className="add-button"
                        type="button"
                        onClick={() =>
                          addItem(item)
                        }
                      >
                        ADD
                      </button>
                    ) : (
                      <div className="quantity-control">
                        <button
                          type="button"
                          onClick={() =>
                            decreaseItem(
                              item.id,
                            )
                          }
                        >
                          −
                        </button>

                        <span>
                          {quantity}
                        </span>

                        <button
                          type="button"
                          onClick={() =>
                            increaseItem(
                              item.id,
                            )
                          }
                        >
                          +
                        </button>
                      </div>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        <form
          className="order-panel panel"
          onSubmit={submitOrder}
        >
          <div className="section-header">
            <h2>Your Order</h2>
            <strong>
              {money(cartTotal)}
            </strong>
          </div>

          {cart.length === 0 ? (
            <p className="empty">
              Select items from the menu.
            </p>
          ) : (
            <div className="cart-list">
              {cart.map((item) => (
                <div
                  className="cart-row"
                  key={item.id}
                >
                  <div>
                    <strong>
                      {item.name}
                    </strong>
                    <span>
                      {money(item.price)} ×{' '}
                      {item.quantity}
                    </span>
                  </div>

                  <div className="quantity-control">
                    <button
                      type="button"
                      onClick={() =>
                        decreaseItem(
                          item.id,
                        )
                      }
                    >
                      −
                    </button>

                    <span>
                      {item.quantity}
                    </span>

                    <button
                      type="button"
                      onClick={() =>
                        increaseItem(
                          item.id,
                        )
                      }
                    >
                      +
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <h3>Payment</h3>

          <div className="payment-buttons">
            <button
              type="button"
              className={
                payment === 'CASH'
                  ? 'payment-button active'
                  : 'payment-button'
              }
              onClick={() =>
                setPayment('CASH')
              }
            >
              💵 CASH
            </button>

            <button
              type="button"
              className={
                payment === 'UPI'
                  ? 'payment-button active'
                  : 'payment-button'
              }
              onClick={() =>
                setPayment('UPI')
              }
            >
              📱 UPI
            </button>

            <button
              type="button"
              className={
                payment === 'RAZORPAY'
                  ? 'payment-button active'
                  : 'payment-button'
              }
              onClick={() =>
                setPayment('RAZORPAY')
              }
            >
              💳 RAZORPAY
            </button>
          </div>

          {message && (
            <div className="message">
              {message}
            </div>
          )}

          <button
            className="submit-order"
            disabled={
              submitting ||
              cart.length === 0
            }
          >
            {submitting
              ? payment === 'RAZORPAY'
                ? 'Opening Payment...'
                : 'Submitting...'
              : payment === 'RAZORPAY'
                ? `PAY WITH RAZORPAY • ${money(
                    cartTotal,
                  )}`
                : `SUBMIT ORDER • ${money(
                    cartTotal,
                  )}`}
          </button>
        </form>
      </main>

      {orderPopup && (
        <div className="popup-backdrop">
          <div className="order-popup">
            <div className="success-icon">
              ✓
            </div>

            <h2>Order Submitted</h2>

            <p>Your Order ID</p>

            <strong className="order-id">
              #{orderPopup}
            </strong>

            <p>
              Please keep this Order ID for
              pickup / delivery.
            </p>

            <button
              type="button"
              onClick={() =>
                setOrderPopup('')
              }
            >
              DONE
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/* =========================================================
   OWNER PAGE
   ========================================================= */

function OwnerPage() {
  const [dashboard, setDashboard] =
    useState<Dashboard | null>(null)

  const [orders, setOrders] = useState<
    CustomerOrder[]
  >([])

  const [expenses, setExpenses] =
    useState<Expense[]>([])

  const [menu, setMenu] =
    useState<MenuItem[]>(INITIAL_MENU)

  const [stock, setStock] = useState<
    StockItem[]
  >([])

  const [activePage, setActivePage] =
    useState<
      | 'orders'
      | 'expenses'
      | 'stock'
      | 'menu'
    >('orders')

  const [loading, setLoading] =
    useState(true)

  const [saving, setSaving] =
    useState(false)

  const [message, setMessage] =
    useState('')

  const [expense, setExpense] = useState({
    category: 'Raw Material',
    description: '',
    amount: '',
    payment_method: 'CASH',
  })

  const [stockForm, setStockForm] =
    useState({
      name: '',
      quantity: '',
      unit: 'kg',
      minimum_quantity: '',
    })

  useEffect(() => {
    loadOwnerData()
  }, [])

  async function loadOwnerData() {
    try {
      const responses =
        await Promise.all([
          fetch(`${API}/dashboard`),
          fetch(`${API}/orders`),
          fetch(`${API}/expenses`),
          fetch(`${API}/menu`),
          fetch(`${API}/stock`),
        ])

      if (responses[0].ok) {
        setDashboard(
          await responses[0].json(),
        )
      }

      if (responses[1].ok) {
        const data =
          await responses[1].json()

        if (Array.isArray(data)) {
          setOrders(data)
        }
      }

      if (responses[2].ok) {
        const data =
          await responses[2].json()

        if (Array.isArray(data)) {
          setExpenses(data)
        }
      }

      if (responses[3].ok) {
        const data =
          await responses[3].json()

        if (Array.isArray(data)) {
          setMenu(
            INITIAL_MENU.map((item) => {
              const backendItem =
                data.find(
                  (x) =>
                    x.id === item.id ||
                    x.name?.toLowerCase() ===
                      item.name.toLowerCase(),
                )

              return backendItem
                ? {
                    ...item,
                    available:
                      backendItem.available !==
                      false,
                  }
                : item
            }),
          )
        }
      }

      if (responses[4].ok) {
        const data =
          await responses[4].json()

        if (Array.isArray(data)) {
          setStock(data)
        }
      }
    } catch (error) {
      console.error(error)
      setMessage(
        'Some owner data could not be loaded.',
      )
    } finally {
      setLoading(false)
    }
  }

  async function updateOrderStatus(
    orderId: number,
    status: string,
  ) {
    try {
      const response = await fetch(
        `${API}/orders/${orderId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type':
              'application/json',
          },
          body: JSON.stringify({
            status,
          }),
        },
      )

      if (!response.ok) {
        throw new Error(
          'Order status update failed',
        )
      }

      setOrders((current) =>
        current.map((order) =>
          order.id === orderId
            ? {
                ...order,
                status,
              }
            : order,
        ),
      )

      setMessage(
        `Order #${orderId} updated.`,
      )
    } catch (error) {
      console.error(error)
      setMessage(
        'Could not update order status.',
      )
    }
  }

  async function createExpense(
    event: FormEvent,
  ) {
    event.preventDefault()

    if (
      !expense.category ||
      Number(expense.amount) <= 0
    ) {
      setMessage(
        'Enter a valid expense.',
      )
      return
    }

    setSaving(true)

    try {
      const response = await fetch(
        `${API}/expenses`,
        {
          method: 'POST',
          headers: {
            'Content-Type':
              'application/json',
          },
          body: JSON.stringify({
            category: expense.category,
            description:
              expense.description ||
              null,
            amount: Number(
              expense.amount,
            ),
            payment_method:
              expense.payment_method,
          }),
        },
      )

      const data =
        await response.json()

      if (!response.ok) {
        throw new Error(
          data.detail ||
            'Expense creation failed',
        )
      }

      setExpense({
        category: 'Raw Material',
        description: '',
        amount: '',
        payment_method: 'CASH',
      })

      setMessage(
        `Expense added: ${money(
          data.amount,
        )}`,
      )

      await loadOwnerData()
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Expense creation failed',
      )
    } finally {
      setSaving(false)
    }
  }

  async function addStock(
    event: FormEvent,
  ) {
    event.preventDefault()

    if (
      !stockForm.name.trim() ||
      Number(stockForm.quantity) <= 0
    ) {
      setMessage(
        'Enter valid stock details.',
      )
      return
    }

    setSaving(true)

    try {
      const response = await fetch(
        `${API}/stock`,
        {
          method: 'POST',
          headers: {
            'Content-Type':
              'application/json',
          },
          body: JSON.stringify({
            name: stockForm.name,
            quantity: Number(
              stockForm.quantity,
            ),
            unit: stockForm.unit,
            minimum_quantity: Number(
              stockForm.minimum_quantity ||
                0,
            ),
          }),
        },
      )

      const data =
        await response.json()

      if (!response.ok) {
        throw new Error(
          data.detail ||
            'Stock creation failed',
        )
      }

      setStockForm({
        name: '',
        quantity: '',
        unit: 'kg',
        minimum_quantity: '',
      })

      setMessage('Stock added.')

      await loadOwnerData()
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Stock creation failed',
      )
    } finally {
      setSaving(false)
    }
  }

  async function toggleMenu(
    item: MenuItem,
  ) {
    const newAvailable =
      !item.available

    setMenu((current) =>
      current.map((x) =>
        x.id === item.id
          ? {
              ...x,
              available:
                newAvailable,
            }
          : x,
      ),
    )

    try {
      const response = await fetch(
        `${API}/menu/${item.id}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type':
              'application/json',
          },
          body: JSON.stringify({
            available:
              newAvailable,
          }),
        },
      )

      if (!response.ok) {
        throw new Error(
          'Menu update failed',
        )
      }

      setMessage(
        `${item.name}: ${
          newAvailable
            ? 'Available'
            : 'Unavailable'
        }`,
      )
    } catch (error) {
      console.error(error)

      setMenu((current) =>
        current.map((x) =>
          x.id === item.id
            ? {
                ...x,
                available:
                  item.available,
              }
            : x,
        ),
      )

      setMessage(
        'Could not update menu availability.',
      )
    }
  }

  if (loading) {
    return (
      <div className="loading">
        Loading KS Foods Owner Dashboard...
      </div>
    )
  }

  return (
    <div className="app owner-page">
      <header className="topbar">
        <div>
          <h1>KS Foods</h1>
          <p>Owner Control Center</p>
        </div>

        <a
          className="customer-link"
          href="/foodtruck/"
        >
          Customer View
        </a>
      </header>

      <main>
        <nav className="owner-nav">
          <button
            className={
              activePage === 'orders'
                ? 'active'
                : ''
            }
            onClick={() =>
              setActivePage('orders')
            }
          >
            Orders
          </button>

          <button
            className={
              activePage === 'expenses'
                ? 'active'
                : ''
            }
            onClick={() =>
              setActivePage('expenses')
            }
          >
            Expenses
          </button>

          <button
            className={
              activePage === 'stock'
                ? 'active'
                : ''
            }
            onClick={() =>
              setActivePage('stock')
            }
          >
            Raw Materials
          </button>

          <button
            className={
              activePage === 'menu'
                ? 'active'
                : ''
            }
            onClick={() =>
              setActivePage('menu')
            }
          >
            Menu Control
          </button>

          <button
            className="refresh-owner"
            onClick={
              loadOwnerData
            }
          >
            ↻ Refresh
          </button>
        </nav>

        {message && (
          <div className="message">
            {message}
          </div>
        )}

        {dashboard && (
          <section className="cards owner-cards">
            <div className="card">
              <span>Today's Sales</span>
              <strong>
                {money(
                  dashboard.sales,
                )}
              </strong>
            </div>

            <div className="card">
              <span>Orders</span>
              <strong>
                {dashboard.orders}
              </strong>
            </div>

            <div className="card">
              <span>Expenses</span>
              <strong>
                {money(
                  dashboard.expenses,
                )}
              </strong>
            </div>

            <div className="card profit">
              <span>Profit</span>
              <strong>
                {money(
                  dashboard.profit,
                )}
              </strong>
            </div>

            <div className="card">
              <span>Cash Balance</span>
              <strong>
                {money(
                  dashboard.cash_balance,
                )}
              </strong>
            </div>

            <div className="card">
              <span>UPI Sales</span>
              <strong>
                {money(
                  dashboard.upi_sales,
                )}
              </strong>
            </div>

            <div className="card">
              <span>Razorpay Sales</span>
              <strong>
                {money(
                  dashboard.razorpay_sales,
                )}
              </strong>
            </div>
          </section>
        )}

        {activePage ===
          'orders' && (
          <OwnerOrders
            orders={orders}
            onStatusChange={
              updateOrderStatus
            }
          />
        )}

        {activePage ===
          'expenses' && (
          <OwnerExpenses
            expenses={expenses}
            expense={expense}
            setExpense={setExpense}
            saving={saving}
            onSubmit={createExpense}
          />
        )}

        {activePage ===
          'stock' && (
          <OwnerStock
            stock={stock}
            form={stockForm}
            setForm={setStockForm}
            saving={saving}
            onSubmit={addStock}
          />
        )}

        {activePage ===
          'menu' && (
          <OwnerMenuControl
            menu={menu}
            onToggle={toggleMenu}
          />
        )}
      </main>
    </div>
  )
}

/* =========================================================
   OWNER ORDERS
   ========================================================= */

function OwnerOrders({
  orders,
  onStatusChange,
}: {
  orders: CustomerOrder[]
  onStatusChange: (
    id: number,
    status: string,
  ) => void
}) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>Orders & Delivery</h2>
          <p>
            Manage new, preparing,
            ready and delivered orders.
          </p>
        </div>

        <strong>{orders.length}</strong>
      </div>

      {orders.length === 0 ? (
        <div className="empty">
          No orders yet.
        </div>
      ) : (
        <div className="owner-order-grid">
          {orders.map((order) => (
            <article
              className="owner-order-card"
              key={order.id}
            >
              <div className="order-top">
                <div>
                  <span>ORDER ID</span>

                  <h3>
                    #
                    {order.order_number ||
                      order.id}
                  </h3>
                </div>

                <span
                  className={`status ${order.status
                    .toLowerCase()
                    .replace(
                      /\s+/g,
                      '-',
                    )}`}
                >
                  {order.status}
                </span>
              </div>

              <div className="customer-order-info">
                <strong>
                  {order.customer_name ||
                    'Customer'}
                </strong>

                {order.phone && (
                  <span>
                    📞 {order.phone}
                  </span>
                )}
              </div>

              <div className="order-items">
                {order.items?.map(
                  (item, index) => (
                    <div
                      key={`${order.id}-${item.name}-${index}`}
                    >
                      <span>
                        {item.name} ×{' '}
                        {item.quantity}
                      </span>

                      <strong>
                        {money(
                          item.price *
                            item.quantity,
                        )}
                      </strong>
                    </div>
                  ),
                )}
              </div>

              <div className="order-total">
                <span>
                  {order.payment_method}
                </span>

                <strong>
                  {money(order.total)}
                </strong>
              </div>

              <select
                value={order.status}
                onChange={(event) =>
                  onStatusChange(
                    order.id,
                    event.target.value,
                  )
                }
              >
                <option value="NEW">
                  NEW
                </option>
                <option value="PREPARING">
                  PREPARING
                </option>
                <option value="READY">
                  READY
                </option>
                <option value="OUT_FOR_DELIVERY">
                  OUT FOR DELIVERY
                </option>
                <option value="DELIVERED">
                  DELIVERED
                </option>
                <option value="CANCELLED">
                  CANCELLED
                </option>
              </select>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

/* =========================================================
   OWNER EXPENSES
   ========================================================= */

function OwnerExpenses({
  expenses,
  expense,
  setExpense,
  saving,
  onSubmit,
}: {
  expenses: Expense[]
  expense: {
    category: string
    description: string
    amount: string
    payment_method: string
  }
  setExpense: React.Dispatch<
    React.SetStateAction<{
      category: string
      description: string
      amount: string
      payment_method: string
    }>
  >
  saving: boolean
  onSubmit: (
    event: FormEvent,
  ) => void
}) {
  const categories = [
    'Raw Material',
    'Vegetables',
    'Rice',
    'Dal',
    'Oil',
    'Paneer',
    'Gas',
    'Packaging',
    'Transport',
    'Staff',
    'Rent',
    'Electricity',
    'Cleaning',
    'Maintenance',
    'Other',
  ]

  return (
    <section className="forms-grid">
      <form
        className="panel"
        onSubmit={onSubmit}
      >
        <h2>Add Expense</h2>

        <label>Category</label>

        <select
          value={expense.category}
          onChange={(event) =>
            setExpense({
              ...expense,
              category:
                event.target.value,
            })
          }
        >
          {categories.map(
            (category) => (
              <option
                value={category}
                key={category}
              >
                {category}
              </option>
            ),
          )}
        </select>

        <input
          placeholder="Description"
          value={expense.description}
          onChange={(event) =>
            setExpense({
              ...expense,
              description:
                event.target.value,
            })
          }
        />

        <input
          type="number"
          min="0.01"
          step="0.01"
          placeholder="Amount"
          value={expense.amount}
          onChange={(event) =>
            setExpense({
              ...expense,
              amount:
                event.target.value,
            })
          }
        />

        <div className="payment-buttons">
          <button
            type="button"
            className={
              expense.payment_method ===
              'CASH'
                ? 'payment-button active'
                : 'payment-button'
            }
            onClick={() =>
              setExpense({
                ...expense,
                payment_method:
                  'CASH',
              })
            }
          >
            💵 CASH
          </button>

          <button
            type="button"
            className={
              expense.payment_method ===
              'UPI'
                ? 'payment-button active'
                : 'payment-button'
            }
            onClick={() =>
              setExpense({
                ...expense,
                payment_method:
                  'UPI',
              })
            }
          >
            📱 UPI
          </button>
        </div>

        <button
          className="primary"
          disabled={saving}
        >
          {saving
            ? 'Saving...'
            : 'Add Expense'}
        </button>
      </form>

      <section className="panel">
        <div className="section-header">
          <h2>Expense History</h2>
          <strong>
            {expenses.length}
          </strong>
        </div>

        <div className="simple-list">
          {expenses.map((item) => (
            <div
              className="simple-row"
              key={item.id}
            >
              <div>
                <strong>
                  {item.category}
                </strong>

                <span>
                  {item.description ||
                    '-'}
                </span>
              </div>

              <div>
                <strong>
                  {money(item.amount)}
                </strong>

                <span>
                  {item.payment_method}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </section>
  )
}

/* =========================================================
   OWNER STOCK
   ========================================================= */

function OwnerStock({
  stock,
  form,
  setForm,
  saving,
  onSubmit,
}: {
  stock: StockItem[]
  form: {
    name: string
    quantity: string
    unit: string
    minimum_quantity: string
  }
  setForm: React.Dispatch<
    React.SetStateAction<{
      name: string
      quantity: string
      unit: string
      minimum_quantity: string
    }>
  >
  saving: boolean
  onSubmit: (
    event: FormEvent,
  ) => void
}) {
  return (
    <section className="forms-grid">
      <form
        className="panel"
        onSubmit={onSubmit}
      >
        <h2>Raw Materials / Stock</h2>

        <input
          placeholder="Material name"
          value={form.name}
          onChange={(event) =>
            setForm({
              ...form,
              name: event.target.value,
            })
          }
        />

        <input
          type="number"
          min="0"
          step="0.01"
          placeholder="Available quantity"
          value={form.quantity}
          onChange={(event) =>
            setForm({
              ...form,
              quantity:
                event.target.value,
            })
          }
        />

        <select
          value={form.unit}
          onChange={(event) =>
            setForm({
              ...form,
              unit: event.target.value,
            })
          }
        >
          <option value="kg">
            Kilogram
          </option>
          <option value="litre">
            Litre
          </option>
          <option value="packet">
            Packet
          </option>
          <option value="piece">
            Piece
          </option>
          <option value="box">
            Box
          </option>
        </select>

        <input
          type="number"
          min="0"
          step="0.01"
          placeholder="Minimum stock level"
          value={
            form.minimum_quantity
          }
          onChange={(event) =>
            setForm({
              ...form,
              minimum_quantity:
                event.target.value,
            })
          }
        />

        <button
          className="primary"
          disabled={saving}
        >
          {saving
            ? 'Saving...'
            : 'Add Stock'}
        </button>
      </form>

      <section className="panel">
        <div className="section-header">
          <h2>Available Stock</h2>
          <strong>
            {stock.length}
          </strong>
        </div>

        <div className="stock-grid">
          {stock.map((item) => {
            const low =
              item.quantity <=
              item.minimum_quantity

            return (
              <article
                className={
                  low
                    ? 'stock-card low'
                    : 'stock-card'
                }
                key={item.id}
              >
                <h3>{item.name}</h3>

                <strong>
                  {item.quantity}{' '}
                  {item.unit}
                </strong>

                <span>
                  Minimum:{' '}
                  {
                    item.minimum_quantity
                  }{' '}
                  {item.unit}
                </span>

                {low && (
                  <b>LOW STOCK</b>
                )}
              </article>
            )
          })}
        </div>
      </section>
    </section>
  )
}

/* =========================================================
   OWNER MENU CONTROL
   ========================================================= */

function OwnerMenuControl({
  menu,
  onToggle,
}: {
  menu: MenuItem[]
  onToggle: (
    item: MenuItem,
  ) => void
}) {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2>
            Available / Unavailable
            Menu
          </h2>

          <p>
            Turn dishes ON or OFF without
            changing the customer menu.
          </p>
        </div>
      </div>

      <div className="owner-menu-grid">
        {menu.map((item) => (
          <article
            className="owner-menu-card"
            key={item.id}
          >
            <img
              src={imageUrl(item.image)}
              alt={item.name}
            />

            <div>
              <h3>{item.name}</h3>

              <strong>
                {money(item.price)}
              </strong>
            </div>

            <button
              type="button"
              className={
                item.available
                  ? 'availability available'
                  : 'availability unavailable'
              }
              onClick={() =>
                onToggle(item)
              }
            >
              {item.available
                ? 'AVAILABLE'
                : 'UNAVAILABLE'}
            </button>
          </article>
        ))}
      </div>
    </section>
  )
}

export default App
