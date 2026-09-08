import { useEffect, useMemo, useState } from 'react'
import './ks-redesign.css'

const API = '/foodtruck-api'
const QR_IMAGE = import.meta.env.VITE_PAYTM_QR_IMAGE || '/foodtruck/images/paytm-qr.png'
const DELIVERY_FEE = Number(import.meta.env.VITE_DELIVERY_FEE || 20)
const FREE_THRESHOLD = Number(import.meta.env.VITE_FREE_DELIVERY_THRESHOLD || 300)

type MenuItem = { id: string; name: string; price: number; image: string; available: boolean }
type CartItem = MenuItem & { quantity: number }
type OrderType = 'LIVE' | 'DELIVERY'
type Payment = 'CASH' | 'UPI' | 'RAZORPAY'

const fallback: MenuItem[] = [
  ['Idli',40,'idli_plate_chutney_sambar.jpg'],['Upma',40,'suji_upma_breakfast.jpg'],['Vada',40,'medu_vada_sambar_chutney.jpg'],['Mysore Bajji',40,'mysore_bonda_bajji.jpg'],['Plain Dosa',40,'plain_crispy_dosa.jpg'],['Puri',40,'puri_aloo_curry.jpg'],['Ghee Karam',60,'ghee_karam_dosa.jpg'],['Ghee Onion',60,'ghee_onion_dosa.jpg'],['Paneer Dosa',60,'paneer_masala_dosa.jpg'],['Upma Pesara',60,'pesarattu_upma.jpg'],['Onion Pesara',60,'onion_pesarattu.jpg'],['Upma Dosa',50,'upma_filled_dosa.jpg'],['Rava Dosa',50,'crispy_rava_dosa.jpg'],['Onion Dosa',50,'onion_dosa_roast.jpg'],['Masala Dosa',50,'masala_dosa.jpg'],['Pesara',50,'pesara_dosa.jpg'],
].map(([name,price,image]) => ({ id: String(name).toLowerCase().replaceAll(' ','-'), name: String(name), price: Number(price), image: String(image), available: true }))

const money = (n:number) => `₹${n.toFixed(2)}`
const imageUrl = (f:string) => `/foodtruck/images/${f}`

export default function CustomerPageV2() {
  const [menu,setMenu] = useState<MenuItem[]>(fallback)
  const [cart,setCart] = useState<CartItem[]>([])
  const [orderType,setOrderType] = useState<OrderType>('LIVE')
  const [payment,setPayment] = useState<Payment>('CASH')
  const [name,setName] = useState('')
  const [phone,setPhone] = useState('')
  const [house,setHouse] = useState('')
  const [street,setStreet] = useState('')
  const [area,setArea] = useState('')
  const [landmark,setLandmark] = useState('')
  const [instructions,setInstructions] = useState('')
  const [upiPaid,setUpiPaid] = useState(false)
  const [message,setMessage] = useState('')
  const [popup,setPopup] = useState<{number:string,status:string}|null>(null)
  const [submitting,setSubmitting] = useState(false)

  useEffect(() => { fetch(`${API}/menu`).then(r=>r.ok?r.json():[]).then(rows => { if(Array.isArray(rows)&&rows.length) setMenu(fallback.map(x => { const r=rows.find((m:any)=>m.name===x.name); return r ? {...x,price:Number(r.price),available:Boolean(r.available),id:String(r.id)} : x }).filter(x=>x.available)) }).catch(()=>{}) },[])

  const subtotal = useMemo(() => cart.reduce((s,i)=>s+i.price*i.quantity,0),[cart])
  const deliveryFee = orderType === 'DELIVERY' ? (subtotal >= FREE_THRESHOLD ? 0 : DELIVERY_FEE) : 0
  const total = subtotal + deliveryFee

  const add = (item:MenuItem) => setCart(c => { const x=c.find(i=>i.id===item.id); return x ? c.map(i=>i.id===item.id?{...i,quantity:i.quantity+1}:i) : [...c,{...item,quantity:1}] })
  const change = (id:string,d:number) => setCart(c=>c.map(i=>i.id===id?{...i,quantity:i.quantity+d}:i).filter(i=>i.quantity>0))

  async function submit() {
    setMessage('')
    if(!name.trim() || !/^\d{10}$/.test(phone.replace(/\D/g,''))) return setMessage('Enter a valid name and 10-digit mobile number.')
    if(!cart.length) return setMessage('Add at least one item.')
    if(orderType==='DELIVERY' && (!house.trim()||!street.trim()||!area.trim())) return setMessage('Enter house/flat, street and area for delivery.')
    if(payment==='UPI' && !upiPaid) return setMessage('Scan the Paytm QR and confirm payment before placing the order.')
    setSubmitting(true)
    try {
      if(payment==='RAZORPAY') {
        const r=await fetch(`${API}/payments/create-order`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_name:name.trim(),phone:phone.trim(),order_type:orderType,delivery_address:orderType==='DELIVERY'?{house,street,area,landmark,instructions}:null,items:cart.map(i=>({name:i.name,quantity:i.quantity}))})})
        const d=await r.json(); if(!r.ok) throw new Error(d.detail||'Unable to create Razorpay order')
        if(!(window as any).Razorpay) throw new Error('Razorpay failed to load. Refresh and try again.')
        new (window as any).Razorpay({key:d.razorpay_key_id,amount:d.amount,currency:d.currency,name:'KS Foods',description:`Food Order ${d.order_number}`,order_id:d.razorpay_order_id,prefill:{name,contact:phone},handler:async (resp:any)=>{ const v=await fetch(`${API}/payments/verify`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:d.order_id,razorpay_payment_id:resp.razorpay_payment_id,razorpay_order_id:resp.razorpay_order_id,razorpay_signature:resp.razorpay_signature})}); const vd=await v.json(); if(!v.ok||!vd.success) throw new Error(vd.detail||'Payment verification failed'); setCart([]);setPopup({number:d.order_number,status:vd.status||'RECEIVED'}); }}).open()
        return
      }
      const r=await fetch(`${API}/orders`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_name:name.trim(),phone:phone.trim(),payment_method:payment,order_type:orderType,delivery_address:orderType==='DELIVERY'?{house,street,area,landmark,instructions}:null,payment_confirmed:payment==='UPI',items:cart.map(i=>({name:i.name,quantity:i.quantity}))})})
      const d=await r.json(); if(!r.ok) throw new Error(d.detail||'Unable to place order')
      setCart([]);setPopup({number:d.order_number,status:d.status||'RECEIVED'});setUpiPaid(false)
    } catch(e:any) { setMessage(e.message||'Unable to place order') } finally { setSubmitting(false) }
  }

  return <div className="customer-page">
    <header className="ks-topbar"><div><strong>KS Foods</strong><span>Fresh • Fast • Telugu Tiffins</span></div><a href="/foodtruck/owner">Owner</a></header>
    <section className="ks-hero"><div><p className="ks-eyebrow">ORDER DIRECT</p><h1>Hot Telugu tiffins,<br/>ready your way.</h1><p>Order at the truck or get your favourites delivered.</p></div><div className="ks-mode-toggle"><button className={orderType==='LIVE'?'active':''} onClick={()=>setOrderType('LIVE')}>📍 At Truck</button><button className={orderType==='DELIVERY'?'active':''} onClick={()=>setOrderType('DELIVERY')}>🛵 Delivery</button></div></section>
    <section className="ks-customer-card"><input placeholder="Customer name" value={name} onChange={e=>setName(e.target.value)}/><input placeholder="Mobile number" inputMode="numeric" maxLength={10} value={phone} onChange={e=>setPhone(e.target.value.replace(/\D/g,''))}/></section>
    {orderType==='DELIVERY' && <section className="ks-address-card"><h2>Delivery address</h2><div className="ks-form-grid"><input placeholder="House / Flat *" value={house} onChange={e=>setHouse(e.target.value)}/><input placeholder="Street *" value={street} onChange={e=>setStreet(e.target.value)}/><input placeholder="Area *" value={area} onChange={e=>setArea(e.target.value)}/><input placeholder="Landmark" value={landmark} onChange={e=>setLandmark(e.target.value)}/><textarea placeholder="Delivery instructions" value={instructions} onChange={e=>setInstructions(e.target.value)}/></div></section>}
    <main><h2>KS Foods Menu</h2><div className="ks-menu-grid">{menu.map(item=><article className="ks-food-card" key={item.id}><img src={imageUrl(item.image)} alt={item.name}/><div><h3>{item.name}</h3><strong>{money(item.price)}</strong><button onClick={()=>add(item)}>ADD</button></div></article>)}</div></main>
    <aside className="ks-order-panel"><div><h2>Your order</h2>{cart.length?cart.map(i=><div className="ks-cart-row" key={i.id}><span>{i.name}</span><span>{money(i.price*i.quantity)}</span><div><button onClick={()=>change(i.id,-1)}>−</button><b>{i.quantity}</b><button onClick={()=>change(i.id,1)}>+</button></div></div>):<p className="ks-muted">Your cart is empty.</p>}</div><div className="ks-totals"><div><span>Food total</span><b>{money(subtotal)}</b></div>{orderType==='DELIVERY'&&<div><span>Delivery</span><b>{deliveryFee?money(deliveryFee):'FREE'}</b></div>}<div className="grand"><span>Total</span><b>{money(total)}</b></div></div><div className="ks-payment"><h3>Payment</h3>{(['CASH','UPI','RAZORPAY'] as Payment[]).map(p=><button key={p} className={payment===p?'active':''} onClick={()=>{setPayment(p);if(p!=='UPI')setUpiPaid(false)}}>{p==='CASH'?'💵 Cash':p==='UPI'?'📱 UPI / Paytm':'💳 Razorpay'}</button>)}</div>{payment==='UPI'&&<div className="ks-qr-card"><img src={QR_IMAGE} alt="Paytm UPI QR code"/><p>Scan with Paytm, Google Pay or PhonePe</p><label><input type="checkbox" checked={upiPaid} onChange={e=>setUpiPaid(e.target.checked)}/> I HAVE PAID</label></div>}{message&&<div className="ks-error">{message}</div>}<button className="ks-submit" disabled={submitting||!cart.length} onClick={submit}>{submitting?'PROCESSING…':orderType==='DELIVERY'?'PLACE DELIVERY ORDER':'PLACE ORDER'}</button></aside>
    {popup&&<div className="ks-modal-backdrop"><div className="ks-modal"><h2>Order received 🎉</h2><p>Order <strong>#{popup.number}</strong></p><p>Status: <strong>{popup.status}</strong></p><p>Keep your order number for tracking.</p><a href={`/foodtruck/track?order=${popup.number}`}>Track order</a><button onClick={()=>setPopup(null)}>DONE</button></div></div>}
  </div>
}
