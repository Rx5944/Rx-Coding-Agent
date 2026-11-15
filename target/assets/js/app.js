// ============================================================
// APEXRIG — APP CORE: cart, art, search, toasts, theme, UI
// ============================================================

/* ---------- THEME ---------- */
function initTheme(){
  const saved = localStorage.getItem('apexrig-theme');
  const theme = saved || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  document.documentElement.dataset.theme = theme;
  const btn = document.getElementById('themeBtn');
  if (btn) btn.innerHTML = theme === 'dark'
    ? '<svg class="ic-moon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg><svg class="ic-sun" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
    : '<svg class="ic-moon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg><svg class="ic-sun" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  if (btn) btn.querySelector('.ic-sun').style.display = theme === 'dark' ? 'none' : 'block';
  if (btn) btn.querySelector('.ic-moon').style.display = theme === 'dark' ? 'block' : 'none';
}

/* ---------- SVG PRODUCT ART ---------- */
function artSVG(p, size = 400){
  const c = p.color || '#22d3ee';
  const gid = 'g' + Math.random().toString(36).slice(2,7);
  const defs = `
    <defs>
      <linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="${c}" stop-opacity=".35"/>
        <stop offset="100%" stop-color="${c}" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="${gid}2" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#22d3ee"/><stop offset="100%" stop-color="#8b5cf6"/>
      </linearGradient>
    </defs>`;
  let body = '';
  const W = 200, H = 125;
  if (p.cat === 'laptops'){
    body = `
      <rect x="55" y="18" width="90" height="62" rx="8" fill="url(#${gid})"/>
      <rect x="62" y="25" width="76" height="48" rx="4" fill="#0a0c14"/>
      <rect x="70" y="33" width="60" height="32" rx="2" fill="url(#${gid}2)" opacity=".85"/>
      <rect x="55" y="80" width="90" height="8" rx="4" fill="${c}"/>
      <rect x="70" y="92" width="60" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'desktops'){
    body = `
      <rect x="40" y="30" width="120" height="70" rx="8" fill="url(#${gid})"/>
      <rect x="50" y="40" width="100" height="50" rx="4" fill="#0a0c14"/>
      <rect x="60" y="50" width="80" height="30" rx="2" fill="url(#${gid}2)" opacity=".85"/>
      <rect x="40" y="98" width="120" height="8" rx="4" fill="${c}"/>
      <circle cx="70" cy="112" r="4" fill="${c}"/><circle cx="90" cy="112" r="4" fill="${c}" opacity=".6"/><circle cx="110" cy="112" r="4" fill="${c}" opacity=".3"/>`;
  } else if (p.cat === 'workstations'){
    body = `
      <rect x="45" y="22" width="110" height="80" rx="8" fill="url(#${gid})"/>
      <rect x="55" y="32" width="90" height="60" rx="4" fill="#0a0c14"/>
      <rect x="65" y="42" width="70" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/>
      <rect x="45" y="102" width="110" height="8" rx="4" fill="${c}"/>
      <rect x="60" y="114" width="80" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'peripherals'){
    if (p.id && p.id.includes('keyboard')){
      body = `<rect x="45" y="40" width="110" height="45" rx="6" fill="#141826"/><rect x="50" y="45" width="100" height="35" rx="3" fill="#0a0c14"/><rect x="56" y="51" width="88" height="23" rx="2" fill="${c}" opacity=".8"/><circle cx="70" cy="62" r="3" fill="#0a0c14"/><circle cx="82" cy="62" r="3" fill="#0a0c14"/><circle cx="94" cy="62" r="3" fill="#0a0c14"/><circle cx="106" cy="62" r="3" fill="#0a0c14"/><rect x="45" y="88" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    } else if (p.id && p.id.includes('mouse')){
      body = `<ellipse cx="100" cy="72" rx="42" ry="30" fill="url(#${gid})"/><ellipse cx="100" cy="72" rx="30" ry="20" fill="#0a0c14"/><ellipse cx="100" cy="72" rx="12" ry="8" fill="url(#${gid}2)" opacity=".9"/>`;
    } else if (p.id && p.id.includes('headset')){
      body = `<path d="M55 60 C55 30 145 30 145 60 L145 66 C145 40 55 40 55 66 Z" fill="url(#${gid})"/><rect x="52" y="58" width="96" height="34" rx="14" fill="#0a0c14"/><rect x="60" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".85"/><rect x="106" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".5"/>`;
    } else {
      body = `<rect x="45" y="30" width="110" height="70" rx="6" fill="url(#${gid})"/><rect x="52" y="37" width="96" height="56" rx="3" fill="#0a0c14"/><rect x="60" y="45" width="80" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="45" y="98" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    }
  }
  const glow = `<circle cx="${W*0.2}" cy="${H*0.2}" r="60" fill="url(#${gid})" opacity=".5"/><circle cx="${W*0.85}" cy="${H*0.85}" r="70" fill="url(#${gid}2)" opacity=".35"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="${p.name}"><defs>${defs}</defs>${glow}${body}</svg>`;
}

function productArt(p, cls = ''){
  const c = p.color || '#22d3ee';
  const gid = 'ag' + Math.abs(hash(p.id)).toString(36);
  const defs = `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="${c}" stop-opacity=".4"/><stop offset="100%" stop-color="${c}" stop-opacity="0"/></linearGradient><linearGradient id="${gid}2" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#22d3ee"/><stop offset="100%" stop-color="#8b5cf6"/></linearGradient></defs>`;
  let body = '';
  const W = 200, H = 125;
  if (p.cat === 'laptops'){
    body = `<rect x="55" y="18" width="90" height="62" rx="8" fill="url(#${gid})"/><rect x="62" y="25" width="76" height="48" rx="4" fill="#0a0c14"/><rect x="70" y="33" width="60" height="32" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="55" y="80" width="90" height="8" rx="4" fill="${c}"/><rect x="70" y="92" width="60" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'desktops'){
    body = `<rect x="40" y="30" width="120" height="70" rx="8" fill="url(#${gid})"/><rect x="50" y="40" width="100" height="50" rx="4" fill="#0a0c14"/><rect x="60" y="50" width="80" height="30" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="40" y="98" width="120" height="8" rx="4" fill="${c}"/><circle cx="70" cy="112" r="4" fill="${c}"/><circle cx="90" cy="112" r="4" fill="${c}" opacity=".6"/><circle cx="110" cy="112" r="4" fill="${c}" opacity=".3"/>`;
  } else if (p.cat === 'workstations'){
    body = `<rect x="45" y="22" width="110" height="80" rx="8" fill="url(#${gid})"/><rect x="55" y="32" width="90" height="60" rx="4" fill="#0a0c14"/><rect x="65" y="42" width="70" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="45" y="102" width="110" height="8" rx="4" fill="${c}"/><rect x="60" y="114" width="80" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'peripherals'){
    if (p.id && p.id.includes('keyboard')){
      body = `<rect x="45" y="40" width="110" height="45" rx="6" fill="#141826"/><rect x="50" y="45" width="100" height="35" rx="3" fill="#0a0c14"/><rect x="56" y="51" width="88" height="23" rx="2" fill="${c}" opacity=".8"/><circle cx="70" cy="62" r="3" fill="#0a0c14"/><circle cx="82" cy="62" r="3" fill="#0a0c14"/><circle cx="94" cy="62" r="3" fill="#0a0c14"/><circle cx="106" cy="62" r="3" fill="#0a0c14"/><rect x="45" y="88" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    } else if (p.id && p.id.includes('mouse')){
      body = `<ellipse cx="100" cy="72" rx="42" ry="30" fill="url(#${gid})"/><ellipse cx="100" cy="72" rx="30" ry="20" fill="#0a0c14"/><ellipse cx="100" cy="72" rx="12" ry="8" fill="url(#${gid}2)" opacity=".9"/>`;
    } else if (p.id && p.id.includes('headset')){
      body = `<path d="M55 60 C55 30 145 30 145 60 L145 66 C145 40 55 40 55 66 Z" fill="url(#${gid})"/><rect x="52" y="58" width="96" height="34" rx="14" fill="#0a0c14"/><rect x="60" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".85"/><rect x="106" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".5"/>`;
    } else {
      body = `<rect x="45" y="30" width="110" height="70" rx="6" fill="url(#${gid})"/><rect x="52" y="37" width="96" height="56" rx="3" fill="#0a0c14"/><rect x="60" y="45" width="80" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="45" y="98" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    }
  }
  const glow = `<circle cx="${W*0.2}" cy="${H*0.2}" r="60" fill="url(#${gid})" opacity=".5"/><circle cx="${W*0.85}" cy="${H*0.85}" r="70" fill="url(#${gid}2)" opacity=".35"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="${p.name}">${defs}${glow}${body}</svg>`;
}

function hash(s){let h=0;for(let i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0}return Math.abs(h)}
function productArt(p, cls = ''){
  const c = p.color || '#22d3ee';
  const gid = 'ag' + Math.abs(hash(p.id)).toString(36);
  const defs = `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="${c}" stop-opacity=".4"/><stop offset="100%" stop-color="${c}" stop-opacity="0"/></linearGradient><linearGradient id="${gid}2" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#22d3ee"/><stop offset="100%" stop-color="#8b5cf6"/></linearGradient></defs>`;
  let body = '';
  const W = 200, H = 125;
  if (p.cat === 'laptops'){
    body = `<rect x="55" y="18" width="90" height="62" rx="8" fill="url(#${gid})"/><rect x="62" y="25" width="76" height="48" rx="4" fill="#0a0c14"/><rect x="70" y="33" width="60" height="32" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="55" y="80" width="90" height="8" rx="4" fill="${c}"/><rect x="70" y="92" width="60" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'desktops'){
    body = `<rect x="40" y="30" width="120" height="70" rx="8" fill="url(#${gid})"/><rect x="50" y="40" width="100" height="50" rx="4" fill="#0a0c14"/><rect x="60" y="50" width="80" height="30" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="40" y="98" width="120" height="8" rx="4" fill="${c}"/><circle cx="70" cy="112" r="4" fill="${c}"/><circle cx="90" cy="112" r="4" fill="${c}" opacity=".6"/><circle cx="110" cy="112" r="4" fill="${c}" opacity=".3"/>`;
  } else if (p.cat === 'workstations'){
    body = `<rect x="45" y="22" width="110" height="80" rx="8" fill="url(#${gid})"/><rect x="55" y="32" width="90" height="60" rx="4" fill="#0a0c14"/><rect x="65" y="42" width="70" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="45" y="102" width="110" height="8" rx="4" fill="${c}"/><rect x="60" y="114" width="80" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'peripherals'){
    if (p.id && p.id.includes('keyboard')){
      body = `<rect x="45" y="40" width="110" height="45" rx="6" fill="#141826"/><rect x="50" y="45" width="100" height="35" rx="3" fill="#0a0c14"/><rect x="56" y="51" width="88" height="23" rx="2" fill="${c}" opacity=".8"/><circle cx="70" cy="62" r="3" fill="#0a0c14"/><circle cx="82" cy="62" r="3" fill="#0a0c14"/><circle cx="94" cy="62" r="3" fill="#0a0c14"/><circle cx="106" cy="62" r="3" fill="#0a0c14"/><rect x="45" y="88" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    } else if (p.id && p.id.includes('mouse')){
      body = `<ellipse cx="100" cy="72" rx="42" ry="30" fill="url(#${gid})"/><ellipse cx="100" cy="72" rx="30" ry="20" fill="#0a0c14"/><ellipse cx="100" cy="72" rx="12" ry="8" fill="url(#${gid}2)" opacity=".9"/>`;
    } else if (p.id && p.id.includes('headset')){
      body = `<path d="M55 60 C55 30 145 30 145 60 L145 66 C145 40 55 40 55 66 Z" fill="url(#${gid})"/><rect x="52" y="58" width="96" height="34" rx="14" fill="#0a0c14"/><rect x="60" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".85"/><rect x="106" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".5"/>`;
    } else {
      body = `<rect x="45" y="30" width="110" height="70" rx="6" fill="url(#${gid})"/><rect x="52" y="37" width="96" height="56" rx="3" fill="#0a0c14"/><rect x="60" y="45" width="80" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="45" y="98" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    }
  }
  const glow = `<circle cx="${W*0.2}" cy="${H*0.2}" r="60" fill="url(#${gid})" opacity=".5"/><circle cx="${W*0.85}" cy="${H*0.85}" r="70" fill="url(#${gid}2)" opacity=".35"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="${p.name}">${defs}${glow}${body}</svg>`;
}

function hash(s){let h=0;for(let i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0}return Math.abs(h)}
function productArt(p, cls = ''){
  const c = p.color || '#22d3ee';
  const gid = 'ag' + Math.abs(hash(p.id)).toString(36);
  const defs = `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="${c}" stop-opacity=".4"/><stop offset="100%" stop-color="${c}" stop-opacity="0"/></linearGradient><linearGradient id="${gid}2" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#22d3ee"/><stop offset="100%" stop-color="#8b5cf6"/></linearGradient></defs>`;
  let body = '';
  const W = 200, H = 125;
  if (p.cat === 'laptops'){
    body = `<rect x="55" y="18" width="90" height="62" rx="8" fill="url(#${gid})"/><rect x="62" y="25" width="76" height="48" rx="4" fill="#0a0c14"/><rect x="70" y="33" width="60" height="32" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="55" y="80" width="90" height="8" rx="4" fill="${c}"/><rect x="70" y="92" width="60" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'desktops'){
    body = `<rect x="40" y="30" width="120" height="70" rx="8" fill="url(#${gid})"/><rect x="50" y="40" width="100" height="50" rx="4" fill="#0a0c14"/><rect x="60" y="50" width="80" height="30" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="40" y="98" width="120" height="8" rx="4" fill="${c}"/><circle cx="70" cy="112" r="4" fill="${c}"/><circle cx="90" cy="112" r="4" fill="${c}" opacity=".6"/><circle cx="110" cy="112" r="4" fill="${c}" opacity=".3"/>`;
  } else if (p.cat === 'workstations'){
    body = `<rect x="45" y="22" width="110" height="80" rx="8" fill="url(#${gid})"/><rect x="55" y="32" width="90" height="60" rx="4" fill="#0a0c14"/><rect x="65" y="42" width="70" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="45" y="102" width="110" height="8" rx="4" fill="${c}"/><rect x="60" y="114" width="80" height="5" rx="2.5" fill="${c}" opacity=".5"/>`;
  } else if (p.cat === 'peripherals'){
    if (p.id && p.id.includes('keyboard')){
      body = `<rect x="45" y="40" width="110" height="45" rx="6" fill="#141826"/><rect x="50" y="45" width="100" height="35" rx="3" fill="#0a0c14"/><rect x="56" y="51" width="88" height="23" rx="2" fill="${c}" opacity=".8"/><circle cx="70" cy="62" r="3" fill="#0a0c14"/><circle cx="82" cy="62" r="3" fill="#0a0c14"/><circle cx="94" cy="62" r="3" fill="#0a0c14"/><circle cx="106" cy="62" r="3" fill="#0a0c14"/><rect x="45" y="88" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    } else if (p.id && p.id.includes('mouse')){
      body = `<ellipse cx="100" cy="72" rx="42" ry="30" fill="url(#${gid})"/><ellipse cx="100" cy="72" rx="30" ry="20" fill="#0a0c14"/><ellipse cx="100" cy="72" rx="12" ry="8" fill="url(#${gid}2)" opacity=".9"/>`;
    } else if (p.id && p.id.includes('headset')){
      body = `<path d="M55 60 C55 30 145 30 145 60 L145 66 C145 40 55 40 55 66 Z" fill="url(#${gid})"/><rect x="52" y="58" width="96" height="34" rx="14" fill="#0a0c14"/><rect x="60" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".85"/><rect x="106" y="66" width="34" height="18" rx="9" fill="${c}" opacity=".5"/>`;
    } else {
      body = `<rect x="45" y="30" width="110" height="70" rx="6" fill="url(#${gid})"/><rect x="52" y="37" width="96" height="56" rx="3" fill="#0a0c14"/><rect x="60" y="45" width="80" height="40" rx="2" fill="url(#${gid}2)" opacity=".85"/><rect x="45" y="98" width="110" height="6" rx="3" fill="${c}" opacity=".6"/>`;
    }
  }
  const glow = `<circle cx="${W*0.2}" cy="${H*0.2}" r="60" fill="url(#${gid})" opacity=".5"/><circle cx="${W*0.85}" cy="${H*0.85}" r="70" fill="url(#${gid}2)" opacity=".35"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="${p.name}">${defs}${glow}${body}</svg>`;
}

function hash(s){let h=0;for(let i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0}return Math.abs(h)}

/* ---------- HELPERS ---------- */
function fmt(n){ return '$' + n.toLocaleString('en-US'); }
function stars(r){ const full = Math.round(r); return '★'.repeat(full) + '☆'.repeat(5-full); }
function productById(id){ return PRODUCTS.find(p => p.id === id); }
function getProducts(cat, sortField, sortDir){
  let list = PRODUCTS.filter(p => cat === 'all' || p.cat === cat);
  if (sortField === 'price'){
    list = list.slice().sort((a,b)=> sortDir === 'asc' ? a.price - b.price : b.price - a.price);
  } else if (sortField === 'popular'){
    list = list.slice().sort((a,b)=> b.popularity - a.popularity);
  } else if (sortField === 'perf'){
    list = list.slice().sort((a,b)=> b.renderScore - a.renderScore);
  }
  return list;
}

/* ---------- CART ---------- */
const CART_KEY = 'apexrig-cart';
let cart = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
let cartOpen = false;
let appliedPromo = null;

function cartCount(){ return cart.reduce((s,i)=>s+i.qty,0); }
function cartSubtotal(){ return cart.reduce((s,i)=> s + i.price*i.qty, 0); }
function cartDiscount(){ return appliedPromo ? Math.round(cartSubtotal()*appliedPromo.rate) : 0; }
function cartShipping(){
  const sub = cartSubtotal() - cartDiscount();
  if (sub <= 0) return 0;
  if (sub >= 999) return 0;
  return 59;
}
function cartTotal(){ return cartSubtotal() - cartDiscount() + cartShipping(); }

function saveCart(){ localStorage.setItem(CART_KEY, JSON.stringify(cart)); updateCartUI(); }
function addToCart(id, qty = 1, priceOverride = null){
  const p = productById(id);
  if (!p) return;
  const price = priceOverride !== null ? priceOverride : p.price;
  const existing = cart.find(i => i.id === id);
  if (existing) existing.qty += qty;
  else cart.push({ id, qty, price });
  saveCart();
  showToast(`${p.name} added to cart`, 'ok');
}
function removeFromCart(id){
  cart = cart.filter(i => i.id !== id);
  saveCart();
}
function setQty(id, qty){
  if (qty <= 0){ removeFromCart(id); return; }
  const i = cart.find(i => i.id === id);
  if (i) i.qty = qty;
  saveCart();
}
function clearCart(){ cart = []; saveCart(); }

function updateCartUI(){
  const count = cartCount();
  const el = document.getElementById('cartCount');
  const el2 = document.getElementById('cartCountInline');
  if (el){ el.textContent = count; el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump'); }
  if (el2) el2.textContent = `(${count})`;
  const sub = cartSubtotal(), disc = cartDiscount(), ship = cartShipping(), tot = cartTotal();
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  set('cartSubtotal', fmt(sub));
  set('cartDiscount', '-' + fmt(disc));
  set('cartShipping', ship === 0 ? 'FREE' : fmt(ship));
  set('cartTotal', fmt(tot));
  const shipBar = document.getElementById('shipBar');
  const shipMsg = document.getElementById('shipMsg');
  const pct = Math.min(100, (sub / 999) * 100);
  if (shipBar) shipBar.style.width = pct + '%';
  if (shipMsg) shipMsg.innerHTML = sub >= 999
    ? '<b>$0</b> away from free shipping — nice!'
    : `You're <b>$${(999 - sub).toFixed(0)}</b> away from free shipping`;
}

/* ---------- TOASTS ---------- */
function showToast(msg, type = ''){
  const stack = document.getElementById('toastStack');
  const t = document.createElement('div');
  t.className = 'toast ' + (type || '');
  t.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M20 6 9 17l-5-5"/></svg>${msg}`;
  stack.appendChild(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(()=>t.remove(), 300); }, 2600);
}

/* ---------- SEARCH ---------- */
function runSearch(q){
  const input = document.getElementById('searchInput');
  const box = document.getElementById('searchResults');
  const results = PRODUCTS.filter(p => (p.name + ' ' + (p.brand||'') + ' ' + (p.gpuSeries||'') + ' ' + (p.cpu||'')).toLowerCase().includes(q.toLowerCase()));
  if (!box) return;
  if (q.trim().length < 2){ box.hidden = true; return; }
  if (!results.length){ box.innerHTML = '<div class="sr-empty">No rigs found for “' + q + '”</div>'; box.hidden = false; return; }
  box.innerHTML = results.slice(0,5).map(p => `
    <div class="sr-item" data-id="${p.id}">
      <div class="sr-art">${productArt(p)}</div>
      <div><b>${p.name}</b><small>${CATEGORIES[p.cat].label} · ${fmt(p.price)}</small></div>
    </div>`).join('');
  box.querySelectorAll('.sr-item').forEach(el => el.addEventListener('click', () => {
    location.hash = '#/product/' + el.dataset.id;
    box.hidden = true;
    if (document.getElementById('searchInput')) document.getElementById('searchInput').value = '';
  }));
  box.hidden = false;
}
document.getElementById('searchInput')?.addEventListener('input', e => runSearch(e.target.value));

/* ---------- HEADER / SCROLL / MOBILE NAV ---------- */
const header = document.getElementById('siteHeader');
const onScroll = () => header?.classList.toggle('scrolled', window.scrollY > 10);
window.addEventListener('scroll', onScroll, {passive:true});
onScroll();

const burger = document.getElementById('burger');
const mobileNav = document.getElementById('mobileNav');
burger?.addEventListener('click', () => {
  const open = mobileNav.classList.toggle('open');
  burger.classList.toggle('open', open);
  burger.setAttribute('aria-expanded', open);
});
mobileNav?.addEventListener('click', e => { if (e.target.tagName === 'A') mobileNav.classList.remove('open'); });

const themeBtn = document.getElementById('themeBtn');
themeBtn?.addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('apexrig-theme', next);
  initTheme();
});

/* ---------- CART DRAWER ---------- */
const drawer = document.getElementById('cartDrawer');
const overlay = document.getElementById('drawerOverlay');
function openCart(){ drawer.classList.add('open'); drawer.setAttribute('aria-hidden','false'); overlay.hidden = false; overlay.classList.add('show'); }
function closeCart(){ drawer.classList.remove('open'); drawer.setAttribute('aria-hidden','true'); overlay.classList.add('hidden'); setTimeout(()=>overlay.hidden=true, 300); }
document.getElementById('cartBtn')?.addEventListener('click', openCart);
document.getElementById('cartClose')?.addEventListener('click', closeCart);
overlay?.addEventListener('click', closeCart);
document.getElementById('checkoutBtn')?.addEventListener('click', () => { closeCart(); location.hash = '#/checkout'; });

function renderCartItems(){
  const body = document.getElementById('cartItems');
  if (!body) return;
  if (!cart.length){
    body.innerHTML = `<div class="cart-empty"><div class="big">🖥️</div><p>Your rig is waiting.<br>Add a product to begin.</p></div>`;
    return;
  }
  body.innerHTML = cart.map(i => {
    const p = productById(i.id);
    if (!p) return '';
    return `
      <div class="ci">
        <div class="ci-art">${productArt(p)}</div>
        <div class="ci-info">
          <b>${p.name}</b>
          <small>${p.gpuSeries ? p.gpuSeries + ' · ' : ''}${p.cpu || ''}</small>
          <span class="ci-qty">
            <button data-q="dec" data-id="${p.id}">−</button>
            <b>${i.qty}</b>
            <button data-q="inc" data-id="${p.id}">+</button>
          </span>
        </div>
        <div class="ci-right">
          <span class="ci-price">${fmt(i.price * i.qty)}</span>
          <a href="#" class="ci-remove" data-rm="${p.id}">Remove</a>
        </div>
      </div>`;
  }).join('');
  body.querySelectorAll('[data-q]').forEach(btn => btn.addEventListener('click', e => {
    e.preventDefault(); setQty(btn.dataset.id, parseInt(btn.textContent) + (btn.dataset.q === 'inc' ? 1 : -1));
  }));
  body.querySelectorAll('[data-rm]').forEach(el => el.addEventListener('click', e => {
    e.preventDefault(); removeFromCart(el.dataset.rm);
  }));
}
document.getElementById('cartItems')?.addEventListener('click', e => {
  const rm = e.target.closest('[data-rm]'); if (rm) removeFromCart(rm.dataset.rm);
  const q = e.target.closest('[data-q]'); if (q) setQty(q.dataset.id, parseInt(q.textContent) + (q.dataset.q === 'inc' ? 1 : -1));
});

const promoApply = document.getElementById('promoApply');
const promoInput = document.getElementById('promoInput');
const promoMsg = document.getElementById('promoMsg');
promoApply?.addEventListener('click', () => {
  const code = promoInput.value.trim().toUpperCase();
  if (code === 'APEX10'){ appliedPromo = { rate: 0.10 }; promoMsg.textContent = '✓ APEX10 applied — 10% off!'; promoMsg.className = 'promo-msg ok'; }
  else { appliedPromo = null; promoMsg.textContent = 'Invalid code. Try APEX10'; promoMsg.className = 'promo-msg err'; }
  saveCart();
});
promoInput?.addEventListener('input', () => { appliedPromo = null; promoMsg.textContent = ''; saveCart(); });

function updateCartUIAll(){ updateCartUI(); renderCartItems(); }

/* ---------- QUICK VIEW ---------- */
const qv = document.getElementById('quickView');
function openQuickView(id){
  const p = productById(id);
  if (!p) return;
  document.getElementById('qvBody').innerHTML = `
    <div class="qv-art">${productArt(p, 'qv-art-svg')}</div>
    <div class="qv-info">
      <span class="chip chip-cyan">${CATEGORIES[p.cat].label}</span>
      <h3>${p.name}</h3>
      <div class="p-rating"><span class="stars">${stars(p.rating)}</span> <b>${p.rating}</b> (${p.reviews} reviews)</div>
      <p>${p.blurb || p.blurb || ''}</p>
      <div class="qv-price"><span class="price">${fmt(p.price)}</span> ${p.oldPrice ? `<s>${fmt(p.oldPrice)}</s>` : ''}</div>
      <div class="qv-actions">
        <button class="btn btn-primary" data-add="${p.id}">Add to Cart</button>
        <button class="btn btn-ghost" data-buy="${p.id}">Buy Now</button>
      </div>
    </div>`;
  qv.hidden = false;
  qv.querySelector('[data-add]').addEventListener('click', e => { addToCart(p.id); closeQuickView(); });
  qv.querySelector('[data-buy]').addEventListener('click', e => { addToCart(p.id); closeQuickView(); location.hash = '#/checkout'; });
}
function closeQuickView(){ qv.hidden = true; }
document.getElementById('quickView')?.addEventListener('click', e => { if (e.target.closest('[data-close-qv]')) closeQuickView(); });

/* ---------- REVEAL ON SCROLL ---------- */
const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(en => { if (en.isIntersecting){ en.target.classList.add('in'); revealObserver.unobserve(en.target); } });
}, { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

/* ---------- HERO COUNTERS ---------- */
function animateCounters(){
  const els = document.querySelectorAll('[data-count]');
  const run = () => {
    els.forEach(el => {
      const target = parseFloat(el.dataset.count);
      const dec = parseInt(el.dataset.dec || '0');
      const suffix = el.dataset.suffix || '';
      const dur = 1600, t0 = performance.now();
      const tick = now => {
        const t = Math.min(1, (now - t0) / dur);
        const eased = 1 - Math.pow(1 - t, 3);
        const val = target * eased;
        el.textContent = (dec ? val.toFixed(dec) : Math.round(val).toLocaleString('en-US')) + suffix;
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  };
  const io = new IntersectionObserver(entries => { if (entries[0].isIntersecting){ run(); io.disconnect(); } }, {threshold:0.4});
  const hero = document.querySelector('.hero');
  if (hero) io.observe(hero); else run();
}
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  updateCartUI();
  renderCartItems();
  animateCounters();
});
