// ============================================================
// APEXRIG — CATALOG PAGE
// ============================================================
(function(){
  const grid = document.getElementById('productGrid');
  const filterCat = document.getElementById('filterCat');
  const priceRange = document.getElementById('priceRange');
  const minPriceEl = document.getElementById('minPrice');
  const maxPriceEl = document.getElementById('maxPrice');
  const filterGpu = document.getElementById('filterGpu');
  const filterCpu = document.getElementById('filterCpu');
  const filterRam = document.getElementById('filterRam');
  const filterStorage = document.getElementById('filterStorage');
  const sortBy = document.getElementById('sortBy');

  let state = {
    cat: 'all',
    minPrice: 100,
    maxPrice: 5000,
    gpu: '',
    cpu: '',
    ram: '',
    storage: '',
    sort: 'price'
  };

  function applyFilters(){
    let list = PRODUCTS.filter(p => {
      if (state.cat !== 'all' && p.cat !== state.cat) return false;
      if (p.price < state.minPrice || p.price > state.maxPrice) return false;
      if (state.gpu && !p.gpuSeries.toLowerCase().includes(state.gpu)) return false;
      if (state.cpu && p.brand.toLowerCase() !== state.cpu) return false;
      if (state.ram && p.ramGB < parseInt(state.ram)) return false;
      if (state.storage && !p.storageType.toLowerCase().includes(state.storage)) return false;
      return true;
    });
    if (state.sort === 'price') list.sort((a,b)=> a.price - b.price);
    else if (state.sort === 'popular') list.sort((a,b)=> b.popularity - a.popularity);
    else if (state.sort === 'perf') list.sort((a,b)=> b.renderScore - a.renderScore);
    renderGrid(list);
  }

  function renderGrid(list){
    if (!list.length){
      grid.innerHTML = `<div class="empty-state"><div class="big">🔍</div><p>No products match your filters.<br>Try widening your search.</p></div>`;
      return;
    }
    grid.innerHTML = list.map(p => `
      <article class="product-card reveal" data-id="${p.id}">
        <div class="pc-art">${productArt(p)}</div>
        <div class="pc-body">
          <div class="pc-top">
            <span class="chip chip-cyan">${CATEGORIES[p.cat].label}</span>
            ${p.badge ? `<span class="badge">${p.badge}</span>` : ''}
          </div>
          <h3 class="pc-name">${p.name}</h3>
          <div class="pc-rating"><span class="stars">${stars(p.rating)}</span> <b>${p.rating}</b> <span class="muted">(${p.reviews})</span></div>
          <div class="pc-specs">
            <span>${p.gpuSeries || '—'}</span>
            <span>${p.cpu || '—'}</span>
            <span>${p.ramGB ? p.ramGB + 'GB RAM' : '—'}</span>
          </div>
          <div class="pc-foot">
            <div class="pc-price">
              <span class="price">${fmt(p.price)}</span>
              ${p.oldPrice ? `<s>${fmt(p.oldPrice)}</s>` : ''}
            </div>
            <div class="pc-actions">
              <button class="btn btn-primary btn-sm" data-add="${p.id}">Add to Cart</button>
              <button class="btn btn-ghost btn-sm" data-view="${p.id}">Quick View</button>
            </div>
          </div>
        </div>
      </article>`).join('');
    grid.querySelectorAll('[data-add]').forEach(btn => btn.addEventListener('click', e => {
      e.preventDefault(); addToCart(btn.dataset.add);
    }));
    grid.querySelectorAll('[data-view]').forEach(btn => btn.addEventListener('click', e => {
      e.preventDefault(); openQuickView(btn.dataset.view);
    }));
    grid.querySelectorAll('.product-card').forEach(card => {
      card.addEventListener('click', e => {
        if (e.target.closest('button')) return;
        location.hash = '#/product/' + card.dataset.id;
      });
    });
  }

  filterCat.addEventListener('change', e => { state.cat = e.target.value; applyFilters(); });
  priceRange.addEventListener('input', e => {
    state.minPrice = parseInt(e.target.value);
    minPriceEl.textContent = fmt(state.minPrice);
    applyFilters();
  });
  filterGpu.addEventListener('change', e => { state.gpu = e.target.value; applyFilters(); });
  filterCpu.addEventListener('change', e => { state.cpu = e.target.value; applyFilters(); });
  filterRam.addEventListener('change', e => { state.ram = e.target.value; applyFilters(); });
  filterStorage.addEventListener('change', e => { state.storage = e.target.value; applyFilters(); });
  sortBy.addEventListener('change', e => { state.sort = e.target.value; applyFilters(); });

  // URL params
  const params = new URLSearchParams(location.search);
  if (params.get('cat')){
    state.cat = params.get('cat');
    filterCat.value = state.cat;
  }
  applyFilters();
})();