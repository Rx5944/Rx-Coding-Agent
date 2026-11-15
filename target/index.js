// ============================================================
// APEXRIG — HOMEPAGE LOGIC
// Renders category grid, featured deals, best sellers, hero art
// ==============================================

(function () {
  'use strict';

  // --- Hero product art ---
  const heroProduct = document.getElementById('heroProduct');
  if (heroProduct) {
    const flagship = PRODUCTS.find(p => p.id === 'lp-nova-x15') || PRODUCTS[0];
    heroProduct.innerHTML = productArt(flagship);
  }

  // --- Category grid ---
  const catGrid = document.getElementById('catGrid');
  if (catGrid) {
    const cats = [
      { key: 'laptops', label: 'Gaming Laptops', desc: 'RTX 50-series mobile beasts', icon: '💻' },
      { key: 'desktops', label: 'Desktop Rigs', desc: 'Hand-built & stress-tested', icon: '🖥️' },
      { key: 'workstations', label: 'Workstations', desc: 'Creator-grade power', icon: '🧠' },
      { key: 'peripherals', label: 'Peripherals', desc: 'Monitors, keyboards, audio', icon: '🎧' }
    ];
    catGrid.innerHTML = cats.map(c => {
      const count = PRODUCTS.filter(p => p.category === c.key).length;
      const sample = PRODUCTS.find(p => p.category === c.key);
      return `<a href="catalog.html?cat=${c.key}" class="cat-card cat-${c.key}">
        <div class="cat-art">${sample ? productArt(sample) : ''}</div>
        <div class="cat-meta">
          <h3>${c.label}</h3>
          <p>${c.desc}</p>
          <span>${count} products →</span>
        </div>
      </a>`;
    }).join('');
  }

  // --- Featured Deals (products with deal flag) ---
  const dealsGrid = document.getElementById('dealsGrid');
  if (dealsGrid) {
    const deals = PRODUCTS.filter(p => p.deal).slice(0, 4);
    dealsGrid.innerHTML = deals.map(p => productCard(p)).join('');
  }

  // --- Best Sellers (top by popularity) ---
  const bsGrid = document.getElementById('bsGrid');
  if (bsGrid) {
    const best = [...PRODUCTS].sort((a, b) => (b.popularity || 0) - (a.popularity || 0)).slice(0, 4);
    bsGrid.innerHTML = best.map(p => productCard(p)).join('');
  }

  // --- Newsletter form ---
  const nlForm = document.getElementById('nlForm');
  if (nlForm) {
    nlForm.addEventListener('submit', e => {
      e.preventDefault();
      const input = nlForm.querySelector('input[type="email"]');
      if (input.value) {
        toast('Welcome to the Apex Legion! Check your inbox.', 'success');
        input.value = '';
      }
    });
  }

  // --- Count-up stats ---
  const stats = document.querySelectorAll('[data-count]');
  if (stats.length) {
    const io = new IntersectionObserver(entries => {
      entries.forEach(en => {
        if (!en.isIntersecting) return;
        const el = en.target;
        io.unobserve(el);
        const target = parseFloat(el.dataset.count);
        const dec = parseInt(el.dataset.dec || '0', 10);
        const suffix = el.dataset.suffix || '';
        const dur = 1200;
        const start = performance.now();
        function tick(now) {
          const t = Math.min((now - start) / dur, 1);
          const eased = 1 - Math.pow(1 - t, 3);
          el.textContent = (target * eased).toFixed(dec) + suffix;
          if (t < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
    }, { threshold: 0.5 });
    stats.forEach(s => io.observe(s));
  }
})();
