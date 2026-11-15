// ============================================================
// APEXRIG — DATA LAYER
// Realistic sample catalog + PC builder parts + compatibility
// ============================================================

const CATEGORIES = {
  laptops:      { label:'Gaming Laptops', short:'Laptops',     art:'laptop' },
  desktops:     { label:'Desktop Rigs',   short:'Desktops',    art:'desktop' },
  workstations: { label:'Workstations',   short:'Workstations',art:'workstation' },
  peripherals:  { label:'Peripherals',    short:'Peripherals', art:'peripheral' }
};

const PRODUCTS = [
  /* ---------------- GAMING LAPTOPS ---------------- */
  {
    id:'lp-nova-x15', name:'Apex Nova X15 Ultra', cat:'laptops', price:4299, oldPrice:5199,
    badge:'NEW RELEASE', rating:4.9, reviews:412, popularity:98, stock:7,
    brand:'Intel', gpuSeries:'RTX 50', ramGB:64, storageType:'NVMe Gen5', storageGB:4000,
    blurb:'Our flagship 16" gaming laptop. Desktop-class RTX 5090 power in a 2.1kg chassis with a 240Hz QHD+ mini-LED display.',
    specs:{ CPU:'Intel Core i9-14900HX (24C/32T, 5.8GHz)', GPU:'NVIDIA GeForce RTX 5090 Laptop 24GB GDDR7',
      RAM:'64GB DDR5-6400 (2×32GB)', Storage:'4TB PCIe 5.0 NVMe SSD', Cooling:'Vapor chamber + dual 3D fans, liquid metal',
      PSU:'330W GaN adapter', Display:'16" QHD+ 240Hz mini-LED, 1000 nits', OS:'Windows 11 Pro', Weight:'2.1 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:142,fps4k:78},{game:'Valorant',fps1440:412,fps4k:280},
      {game:'Fortnite (Epic)',fps1440:198,fps4k:112},{game:'Black Myth: Wukong',fps1440:118,fps4k:64}],
    renderScore:18420,
    upgrades:[{id:'ram-96',label:'Upgrade to 96GB DDR5-6400',price:349},{id:'ssd-8',label:'Upgrade to 8TB Gen5 SSD',price:499},
      {id:'warranty',label:'Extend warranty to 5 years',price:199}]
  },
  {
    id:'lp-nova-x13', name:'Apex Nova X13 Pro', cat:'laptops', price:3499, oldPrice:3899,
    badge:'BEST SELLER', rating:4.8, reviews:1284, popularity:96, stock:14,
    brand:'AMD', gpuSeries:'RTX 50', ramGB:32, storageType:'NVMe Gen4', storageGB:2000,
    blurb:'A 14" powerhouse that travels light. Ryzen 9 efficiency meets RTX 5080 muscle for creators who game.',
    specs:{ CPU:'AMD Ryzen 9 8945HS (8C/16T, 5.2GHz)', GPU:'NVIDIA GeForce RTX 5080 Laptop 16GB GDDR7',
      RAM:'32GB DDR5-5600 (2×16GB)', Storage:'2TB PCIe 4.0 NVMe SSD', Cooling:'Dual-fan vapor chamber, 4 heat pipes',
      PSU:'240W GaN adapter', Display:'14" QHD+ 165Hz OLED, 600 nits', OS:'Windows 11 Pro', Weight:'1.6 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:118,fps4k:62},{game:'Valorant',fps1440:388,fps4k:255},
      {game:'Fortnite (Epic)',fps1440:172,fps4k:96},{game:'Black Myth: Wukong',fps1440:96,fps4k:52}],
    renderScore:15280,
    upgrades:[{id:'ram-64',label:'Upgrade to 64GB DDR5-5600',price:249},{id:'ssd-4',label:'Upgrade to 4TB Gen4 SSD',price:229},
      {id:'warranty',label:'Extend warranty to 5 years',price:199}]
  },
  {
    id:'lp-viper-16', name:'Apex Viper 16', cat:'laptops', price:2499, oldPrice:2799,
    badge:'DEAL', rating:4.7, reviews:863, popularity:88, stock:22,
    brand:'Intel', gpuSeries:'RTX 50', ramGB:32, storageType:'NVMe Gen4', storageGB:1000,
    blurb:'The sweet spot. 16" 240Hz QHD gaming with RTX 5070 Ti performance at a price that leaves room for peripherals.',
    specs:{ CPU:'Intel Core i7-14700HX (20C/28T, 5.5GHz)', GPU:'NVIDIA GeForce RTX 5070 Ti Laptop 12GB GDDR7',
      RAM:'32GB DDR5-5600 (2×16GB)', Storage:'1TB PCIe 4.0 NVMe SSD', Cooling:'Dual 84-blade fans, 5 heat pipes',
      PSU:'280W adapter', Display:'16" QHD 240Hz IPS, 500 nits', OS:'Windows 11 Home', Weight:'2.3 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:96,fps4k:48},{game:'Valorant',fps1440:356,fps4k:232},
      {game:'Fortnite (Epic)',fps1440:148,fps4k:82},{game:'Black Myth: Wukong',fps1440:78,fps4k:42}],
    renderScore:12840,
    upgrades:[{id:'ram-64',label:'Upgrade to 64GB DDR5-5600',price:229},{id:'ssd-2',label:'Upgrade to 2TB Gen4 SSD',price:129},
      {id:'warranty',label:'Extend warranty to 5 years',price:199}]
  },
  {
    id:'lp-strike-14', name:'Apex Strike 14', cat:'laptops', price:1799, oldPrice:1999,
    badge:'VALUE PICK', rating:4.6, reviews:2140, popularity:84, stock:31,
    brand:'AMD', gpuSeries:'RTX 40', ramGB:16, storageType:'NVMe Gen4', storageGB:1000,
    blurb:'Entry into the Apex ecosystem without compromise. 1080p esports monster that still handles AAA at high settings.',
    specs:{ CPU:'AMD Ryzen 7 8845HS (8C/16T, 5.1GHz)', GPU:'NVIDIA GeForce RTX 4060 Laptop 8GB GDDR6',
      RAM:'16GB DDR5-5600 (2×8GB)', Storage:'1TB PCIe 4.0 NVMe SSD', Cooling:'Dual-fan, 4 heat pipes',
      PSU:'180W adapter', Display:'14" FHD+ 165Hz IPS, 400 nits', OS:'Windows 11 Home', Weight:'1.7 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:62,fps4k:32},{game:'Valorant',fps1440:298,fps4k:190},
      {game:'Fortnite (Epic)',fps1440:104,fps4k:58},{game:'Black Myth: Wukong',fps1440:52,fps4k:28}],
    renderScore:8940,
    upgrades:[{id:'ram-32',label:'Upgrade to 32GB DDR5-5600',price:129},{id:'ssd-2',label:'Upgrade to 2TB Gen4 SSD',price:119},
      {id:'warranty',label:'Extend warranty to 5 years',price:199}]
  },
  {
    id:'lp-studio-16', name:'Apex Studio 16 Pro', cat:'laptops', price:2199, oldPrice:0,
    badge:'CREATOR', rating:4.8, reviews:376, popularity:79, stock:11,
    brand:'Intel', gpuSeries:'RTX 40', ramGB:32, storageType:'NVMe Gen4', storageGB:2000,
    blurb:'Color-accurate 4K OLED, RTX 4070 Studio drivers and a whisper-quiet chassis. Built for editors and 3D artists.',
    specs:{ CPU:'Intel Core Ultra 7 155H (16C/22T, 4.8GHz)', GPU:'NVIDIA GeForce RTX 4070 Laptop 8GB GDDR6',
      RAM:'32GB LPDDR5X-7467', Storage:'2TB PCIe 4.0 NVMe SSD', Cooling:'Triple-fan silent mode, vapor chamber',
      PSU:'200W USB-C PD', Display:'16" 4K OLED 120Hz, 100% DCI-P3', OS:'Windows 11 Pro', Weight:'1.9 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:74,fps4k:38},{game:'Valorant',fps1440:312,fps4k:204},
      {game:'Fortnite (Epic)',fps1440:118,fps4k:66},{game:'Black Myth: Wukong',fps1440:60,fps4k:32}],
    renderScore:11260,
    upgrades:[{id:'ram-64',label:'Upgrade to 64GB LPDDR5X',price:299},{id:'ssd-4',label:'Upgrade to 4TB Gen4 SSD',price:249},
      {id:'warranty',label:'Extend warranty to 5 years',price:199}]
  },

  /* ---------------- DESKTOP RIGS ---------------- */
  {
    id:'dr-titan-x', name:'Apex Titan X', cat:'desktops', price:4999, oldPrice:5499,
    badge:'FLAGSHIP', rating:4.9, reviews:642, popularity:99, stock:5,
    brand:'Intel', gpuSeries:'RTX 50', ramGB:64, storageType:'NVMe Gen5', storageGB:4000,
    blurb:'The no-compromise 4K/240Hz machine. Hand-assembled, cable-managed and stress-tested for 72 hours.',
    specs:{ CPU:'Intel Core i9-14900K (24C/32T, 6.0GHz)', GPU:'NVIDIA GeForce RTX 5090 32GB GDDR7',
      RAM:'64GB DDR5-6400 CL30 (2×32GB)', Storage:'4TB PCIe 5.0 NVMe SSD', Cooling:'360mm AIO liquid, 6× ARGB fans',
      PSU:'1200W 80+ Platinum ATX 3.1', Display:'—', OS:'Windows 11 Pro', Weight:'18.4 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:214,fps4k:128},{game:'Valorant',fps1440:640,fps4k:420},
      {game:'Fortnite (Epic)',fps1440:286,fps4k:168},{game:'Black Myth: Wukong',fps1440:176,fps4k:98}],
    renderScore:24680,
    upgrades:[{id:'ram-128',label:'Upgrade to 128GB DDR5-6400',price:449},{id:'ssd-8',label:'Add 8TB Gen5 SSD',price:699},
      {id:'warranty',label:'Extend warranty to 5 years',price:249}]
  },
  {
    id:'dr-vector-r', name:'Apex Vector R', cat:'desktops', price:3299, oldPrice:3699,
    badge:'BEST SELLER', rating:4.8, reviews:1108, popularity:95, stock:12,
    brand:'AMD', gpuSeries:'RTX 50', ramGB:32, storageType:'NVMe Gen4', storageGB:2000,
    blurb:'Ryzen 9 9950X + RTX 5080. The enthusiast build that dominates 1440p and streams without breaking a sweat.',
    specs:{ CPU:'AMD Ryzen 9 9950X (16C/32T, 5.7GHz)', GPU:'NVIDIA GeForce RTX 5080 16GB GDDR7',
      RAM:'32GB DDR5-6000 CL30 (2×16GB)', Storage:'2TB PCIe 4.0 NVMe SSD', Cooling:'280mm AIO liquid, 4× ARGB fans',
      PSU:'1000W 80+ Gold ATX 3.1', Display:'—', OS:'Windows 11 Pro', Weight:'15.2 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:168,fps4k:96},{game:'Valorant',fps1440:580,fps4k:380},
      {game:'Fortnite (Epic)',fps1440:238,fps4k:138},{game:'Black Myth: Wukong',fps1440:142,fps4k:78}],
    renderScore:19840,
    upgrades:[{id:'ram-64',label:'Upgrade to 64GB DDR5-6000',price:199},{id:'ssd-4',label:'Upgrade to 4TB Gen4 SSD',price:249},
      {id:'warranty',label:'Extend warranty to 5 years',price:249}]
  },
  {
    id:'dr-pulse-mini', name:'Apex Pulse Mini', cat:'desktops', price:1899, oldPrice:2099,
    badge:'SMALL FORM', rating:4.7, reviews:534, popularity:86, stock:18,
    brand:'AMD', gpuSeries:'RTX 40', ramGB:32, storageType:'NVMe Gen4', storageGB:1000,
    blurb:'A 14L mini-ITX rig that fits on any desk and still pushes 1440p Ultra. 7800X3D gaming magic inside.',
    specs:{ CPU:'AMD Ryzen 7 7800X3D (8C/16T, 5.0GHz)', GPU:'NVIDIA GeForce RTX 4070 Super 12GB GDDR6X',
      RAM:'32GB DDR5-6000 CL30 (2×16GB)', Storage:'1TB PCIe 4.0 NVMe SSD', Cooling:'240mm AIO, 3× 120mm fans',
      PSU:'750W 80+ Gold SFX', Display:'—', OS:'Windows 11 Home', Weight:'8.1 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:112,fps4k:62},{game:'Valorant',fps1440:520,fps4k:340},
      {game:'Fortnite (Epic)',fps1440:186,fps4k:104},{game:'Black Myth: Wukong',fps1440:94,fps4k:50}],
    renderScore:13420,
    upgrades:[{id:'ram-64',label:'Upgrade to 64GB DDR5-6000',price:189},{id:'ssd-2',label:'Upgrade to 2TB Gen4 SSD',price:119},
      {id:'warranty',label:'Extend warranty to 5 years',price:249}]
  },
  {
    id:'dr-starter-g', name:'Apex Starter G', cat:'desktops', price:1099, oldPrice:1249,
    badge:'ENTRY', rating:4.5, reviews:1876, popularity:82, stock:40,
    brand:'Intel', gpuSeries:'RTX 40', ramGB:16, storageType:'NVMe Gen4', storageGB:1000,
    blurb:'Your first real gaming PC. 1080p Ultra at 144+ FPS with a clear upgrade path to RTX 50 later.',
    specs:{ CPU:'Intel Core i5-14400F (10C/16T, 4.7GHz)', GPU:'NVIDIA GeForce RTX 4060 8GB GDDR6',
      RAM:'16GB DDR5-5600 (2×8GB)', Storage:'1TB PCIe 4.0 NVMe SSD', Cooling:'Tower air cooler, 3× ARGB fans',
      PSU:'650W 80+ Bronze', Display:'—', OS:'Windows 11 Home', Weight:'12.6 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:68,fps4k:34},{game:'Valorant',fps1440:420,fps4k:260},
      {game:'Fortnite (Epic)',fps1440:124,fps4k:68},{game:'Black Myth: Wukong',fps1440:58,fps4k:30}],
    renderScore:9120,
    upgrades:[{id:'ram-32',label:'Upgrade to 32GB DDR5-5600',price:99},{id:'ssd-2',label:'Upgrade to 2TB Gen4 SSD',price:109},
      {id:'warranty',label:'Extend warranty to 5 years',price:249}]
  },
  {
    id:'dr-obsidian', name:'Apex Obsidian Elite', cat:'desktops', price:6499, oldPrice:0,
    badge:'LIMITED', rating:5.0, reviews:188, popularity:93, stock:3,
    brand:'AMD', gpuSeries:'RTX 50', ramGB:128, storageType:'NVMe Gen5', storageGB:8000,
    blurb:'Limited-run showpiece. 9950X3D, RTX 5090, custom hard-line loop and a hand-finished obsidian chassis.',
    specs:{ CPU:'AMD Ryzen 9 9950X3D (16C/32T, 5.7GHz)', GPU:'NVIDIA GeForce RTX 5090 32GB GDDR7',
      RAM:'128GB DDR5-6400 CL30 (4×32GB)', Storage:'8TB PCIe 5.0 NVMe SSD', Cooling:'Custom hard-line loop, 9× ARGB fans',
      PSU:'1300W 80+ Titanium ATX 3.1', Display:'—', OS:'Windows 11 Pro', Weight:'21.8 kg' },
    benchmarks:[{game:'Cyberpunk 2077',fps1440:228,fps4k:136},{game:'Valorant',fps1440:680,fps4k:450},
      {game:'Fortnite (Epic)',fps1440:302,fps4k:178},{game:'Black Myth: Wukong',fps1440:188,fps4k:104}],
    renderScore:26140,
    upgrades:[{id:'ram-256',label:'Upgrade to 256GB DDR5-6400',price:899},{id:'ssd-16',label:'Add 16TB Gen5 SSD',price:1299},
      {id:'warranty',label:'Extend warranty to 5 years',price:249}]
  },

  /* ---------------- WORKSTATIONS ---------------- */
  {
    id:'ws-forge-z', name:'Apex Forge Z', cat:'workstations', price:4299, oldPrice:4799,
    badge:'PRO', rating:4.9, reviews:214, popularity:90, stock:9,
    brand:'AMD', gpuSeries:'RTX A', ramGB:128, storageType:'NVMe Gen4', storageGB:4000,
    blurb:'Threadripper workstation for CAD, simulation and 8K editing. ECC memory and ISV-certified drivers.',
    specs:{ CPU:'AMD Ryzen Threadripper 7960X (24C/48T, 5.3GHz)', GPU:'NVIDIA RTX A5000 24GB ECC',
      RAM:'128GB DDR5 ECC-5200 (4×32GB)', Storage:'4TB PCIe 4.0 NVMe SSD', Cooling:'360mm AIO, 6× silent fans',
      PSU:'1200W 80+ Platinum', Display:'—', OS:'Windows 11 Pro for Workstations', Weight:'19.2 kg' },
    benchmarks:[{game:'Blender (BMW)',fps1440:0,fps4k:0},{game:'DaVinci 8K',fps1440:0,fps4k:0},
      {game:'Unreal Editor',fps1440:0,fps4k:0},{game:'V-Ray GPU',fps1440:0,fps4k:0}],
    renderScore:38420,
    upgrades:[{id:'ram-256',label:'Upgrade to 256GB ECC',price:749},{id:'ssd-8',label:'Add 8TB Gen4 SSD',price:599},
      {id:'warranty',label:'Extend warranty to 5 years',price:299}]
  },
  {
    id:'ws-forge-z-max', name:'Apex Forge Z Max', cat:'workstations', price:7999, oldPrice:0,
    badge:'ENTERPRISE', rating:5.0, reviews:96, popularity:87, stock:4,
    brand:'AMD', gpuSeries:'RTX A', ramGB:256, storageType:'NVMe Gen5', storageGB:8000,
    blurb:'Dual-GPU rendering monster. 96-core Threadripper PRO and 48GB of VRAM for the heaviest production pipelines.',
    specs:{ CPU:'AMD Threadripper PRO 7995WX (96C/192T, 5.1GHz)', GPU:'2× NVIDIA RTX A6000 48GB ECC',
      RAM:'256GB DDR5 ECC-5200 (8×32GB)', Storage:'8TB PCIe 5.0 NVMe SSD', Cooling:'Dual 360mm AIO, 10× fans',
      PSU:'1600W 80+ Titanium', Display:'—', OS:'Windows 11 Pro for Workstations', Weight:'26.4 kg' },
    benchmarks:[{game:'Blender (BMW)',fps1440:0,fps4k:0},{game:'DaVinci 8K',fps1440:0,fps4k:0},
      {game:'Unreal Editor',fps1440:0,fps4k:0},{game:'V-Ray GPU',fps1440:0,fps4k:0}],
    renderScore:74260,
    upgrades:[{id:'ram-512',label:'Upgrade to 512GB ECC',price:1499},{id:'ssd-16',label:'Add 16TB Gen5 SSD',price:1199},
      {id:'warranty',label:'Extend warranty to 5 years',price:299}]
  },
  {
    id:'ws-render-one', name:'Apex Render One', cat:'workstations', price:2599, oldPrice:2899,
    badge:'CREATOR', rating:4.7, reviews:342, popularity:81, stock:15,
    brand:'Intel', gpuSeries:'RTX 40', ramGB:64, storageType:'NVMe Gen4', storageGB:2000,
    blurb:'The accessible pro rig. i9 + RTX 4080 for 4K editing, motion graphics and architectural viz.',
    specs:{ CPU:'Intel Core i9-14900K (24C/32T, 6.0GHz)', GPU:'NVIDIA GeForce RTX 4080 Super 16GB',
      RAM:'64GB DDR5-6000 (2×32GB)', Storage:'2TB PCIe 4.0 NVMe SSD', Cooling:'280mm AIO, 4× fans',
      PSU:'850W 80+ Gold', Display:'—', OS:'Windows 11 Pro', Weight:'14.8 kg' },
    benchmarks:[{game:'Blender (BMW)',fps1440:0,fps4k:0},{game:'DaVinci 8K',fps1440:0,fps4k:0},
      {game:'Unreal Editor',fps1440:0,fps4k:0},{game:'V-Ray GPU',fps1440:0,fps4k:0}],
    renderScore:22180,
    upgrades:[{id:'ram-128',label:'Upgrade to 128GB DDR5-6000',price:349},{id:'ssd-4',label:'Upgrade to 4TB Gen4 SSD',price:229},
      {id:'warranty',label:'Extend warranty to 5 years',price:299}]
  },

  /* ---------------- PERIPHERALS ---------------- */
  {
    id:'pr-keyboard', name:'Apex Strike K75 Keyboard', cat:'peripherals', price:179, oldPrice:199,
    badge:'HOT', rating:4.8, reviews:3210, popularity:92, stock:120,
    brand:'—', gpuSeries:'—', ramGB:0, storageType:'—', storageGB:0,
    blurb:'75% gasket-mounted mechanical keyboard with hot-swap switches, per-key RGB and 8000Hz polling.',
    specs:{ CPU:'—', GPU:'—', RAM:'—', Storage:'—', Cooling:'—', PSU:'USB-C, 4000mAh battery',
      Display:'OLED status screen', OS:'Windows / macOS / Linux', Weight:'0.9 kg' },
    benchmarks:[], renderScore:0,
    upgrades:[{id:'switches',label:'Add lubed switch upgrade kit',price:29},{id:'wrist',label:'Add magnetic wrist rest',price:39}]
  },
  {
    id:'pr-mouse', name:'Apex Glide M8 Mouse', cat:'peripherals', price:99, oldPrice:0,
    badge:'PRO GEAR', rating:4.9, reviews:2874, popularity:89, stock:200,
    brand:'—', gpuSeries:'—', ramGB:0, storageType:'—', storageGB:0,
    blurb:'58g symmetrical wireless mouse with a 36K DPI sensor, 8000Hz polling and 120-hour battery.',
    specs:{ CPU:'—', GPU:'—', RAM:'—', Storage:'—', Cooling:'—', PSU:'USB-C, 120h battery',
      Display:'—', OS:'Windows / macOS', Weight:'58 g' },
    benchmarks:[], renderScore:0,
    upgrades:[{id:'grip',label:'Add grip tape set',price:12},{id:'dock',label:'Add wireless charging dock',price:39}]
  },
  {
    id:'pr-headset', name:'Apex Echo H7 Headset', cat:'peripherals', price:149, oldPrice:179,
    badge:'DEAL', rating:4.7, reviews:1650, popularity:85, stock:75,
    blurb:'50mm planar drivers, spatial audio and a broadcast-grade detachable mic. 60-hour wireless.',
    specs:{ CPU:'—', GPU:'—', RAM:'—', Storage:'—', Cooling:'—', PSU:'USB-C, 60h battery',
      Display:'—', OS:'Windows / PS5 / Switch', Weight:'0.32 kg' },
    benchmarks:[], renderScore:0,
    upgrades:[{id:'pads',label:'Add cooling gel ear pads',price:19},{id:'stand',label:'Add headset stand',price:29}]
  },
  {
    id:'pr-monitor', name:'Apex Vision 27 4K 240Hz', cat:'peripherals', price:899, oldPrice:1099,
    badge:'NEW', rating:4.9, reviews:742, popularity:91, stock:26,
    blurb:'27" 4K QD-OLED at 240Hz with 0.03ms response, HDR True Black 400 and a built-in KVM.',
    specs:{ CPU:'—', GPU:'—', RAM:'—', Storage:'—', Cooling:'—', PSU:'Internal, 90W typical',
      Display:'27" 4K QD-OLED 240Hz, 0.03ms, HDR400', OS:'—', Weight:'6.4 kg' },
    benchmarks:[], renderScore:0,
    upgrades:[{id:'arm',label:'Add premium monitor arm',price:99},{id:'cal',label:'Add factory calibration report',price:49}]
  }
];

/* ============================================================
   PC BUILDER — PARTS + COMPATIBILITY
   ============================================================ */
const BUILDER_PARTS = {
  case: [
    { id:'case-mid', name:'Apex Vector Mid Tower', price:149, formFactors:['ATX','mATX','ITX'], maxGpu:360, maxCooler:170, art:'case' },
    { id:'case-full', name:'Apex Monolith Full Tower', price:249, formFactors:['ATX','mATX','ITX'], maxGpu:420, maxCooler:185, art:'case' },
    { id:'case-itx', name:'Apex Nano ITX Cube', price:179, formFactors:['ITX'], maxGpu:330, maxCooler:75, art:'case' }
  ],
  cpu: [
    { id:'cpu-i9', name:'Intel Core i9-14900K', price:589, socket:'LGA1700', brand:'Intel', tdp:253, cores:'24C/32T', art:'cpu' },
    { id:'cpu-i5', name:'Intel Core i5-14600K', price:299, socket:'LGA1700', brand:'Intel', tdp:181, cores:'14C/20T', art:'cpu' },
    { id:'cpu-r9', name:'AMD Ryzen 9 9950X', price:649, socket:'AM5', brand:'AMD', tdp:170, cores:'16C/32T', art:'cpu' },
    { id:'cpu-r7', name:'AMD Ryzen 7 7800X3D', price:399, socket:'AM5', brand:'AMD', tdp:120, cores:'8C/16T', art:'cpu' }
  ],
  motherboard: [
    { id:'mb-z790', name:'Apex Z790 Hero (ATX)', price:399, socket:'LGA1700', formFactor:'ATX', ramType:'DDR5', art:'mobo' },
    { id:'mb-b760', name:'Apex B760M (mATX)', price:189, socket:'LGA1700', formFactor:'mATX', ramType:'DDR5', art:'mobo' },
    { id:'mb-x670', name:'Apex X670E Pro (ATX)', price:429, socket:'AM5', formFactor:'ATX', ramType:'DDR5', art:'mobo' },
    { id:'mb-b650', name:'Apex B650I (ITX)', price:259, socket:'AM5', formFactor:'ITX', ramType:'DDR5', art:'mobo' }
  ],
  gpu: [
    { id:'gpu-5090', name:'NVIDIA RTX 5090 32GB', price:1999, length:304, tdp:575, art:'gpu' },
    { id:'gpu-5080', name:'NVIDIA RTX 5080 16GB', price:1099, length:304, tdp:360, art:'gpu' },
    { id:'gpu-5070', name:'NVIDIA RTX 5070 Ti 16GB', price:749, length:280, tdp:300, art:'gpu' },
    { id:'gpu-4060', name:'NVIDIA RTX 4060 8GB', price:299, length:240, tdp:115, art:'gpu' }
  ],
  ram: [
    { id:'ram-16', name:'16GB DDR5-5600 (2×8GB)', price:69, capacity:16, art:'ram' },
    { id:'ram-32', name:'32GB DDR5-6000 (2×16GB)', price:119, capacity:32, art:'ram' },
    { id:'ram-64', name:'64GB DDR5-6400 (2×32GB)', price:229, capacity:64, art:'ram' }
  ],
  storage: [
    { id:'ssd-1', name:'1TB PCIe 4.0 NVMe', price:79, capacity:1000, art:'ssd' },
    { id:'ssd-2', name:'2TB PCIe 4.0 NVMe', price:139, capacity:2000, art:'ssd' },
    { id:'ssd-4', name:'4TB PCIe 5.0 NVMe', price:329, capacity:4000, art:'ssd' }
  ],
  cooling: [
    { id:'cool-air', name:'Apex Tower Air Cooler', price:59, sockets:['LGA1700','AM5'], height:160, art:'cooler' },
    { id:'cool-240', name:'Apex 240mm AIO Liquid', price:129, sockets:['LGA1700','AM5'], height:55, art:'cooler' },
    { id:'cool-360', name:'Apex 360mm AIO Liquid', price:189, sockets:['LGA1700','AM5'], height:55, art:'cooler' }
  ],
  psu: [
    { id:'psu-650', name:'650W 80+ Bronze', price:79, watts:650, art:'psu' },
    { id:'psu-850', name:'850W 80+ Gold', price:129, watts:850, art:'psu' },
    { id:'psu-1200', name:'1200W 80+ Platinum', price:229, watts:1200, art:'psu' }
  ]
};

const BUILDER_STEPS = [
  { key:'case', label:'Case', icon:'▣' },
  { key:'cpu', label:'CPU', icon:'◈' },
  { key:'motherboard', label:'Motherboard', icon:'▤' },
  { key:'gpu', label:'Graphics Card', icon:'▥' },
  { key:'ram', label:'Memory', icon:'▦' },
  { key:'storage', label:'Storage', icon:'▧' },
  { key:'cooling', label:'Cooling', icon:'❄' },
  { key:'psu', label:'Power Supply', icon:'⚡' }
];

/* Compatibility engine — returns {ok, issues[]} for a selection */
function checkBuild(sel){
  const issues = [];
  const c = sel.case, cpu = sel.cpu, mb = sel.motherboard, gpu = sel.gpu, cool = sel.cooling, psu = sel.psu;
  if (cpu && mb && cpu.socket !== mb.socket)
    issues.push(`CPU socket ${cpu.socket} does not match motherboard socket ${mb.socket}.`);
  if (c && mb && !c.formFactors.includes(mb.formFactor))
    issues.push(`${mb.formFactor} motherboard does not fit the ${c.name} (supports ${c.formFactors.join(', ')}).`);
  if (c && gpu && gpu.length > c.maxGpu)
    issues.push(`GPU is ${gpu.length}mm — the ${c.name} supports up to ${c.maxGpu}mm.`);
  if (c && cool && cool.height > c.maxCooler)
    issues.push(`Cooler is ${cool.height}mm tall — the ${c.name} supports up to ${c.maxCooler}mm.`);
  if (cpu && cool && !cool.sockets.includes(cpu.socket))
    issues.push(`Cooler does not support the ${cpu.socket} socket.`);
  if (psu && cpu && gpu){
    const draw = cpu.tdp + gpu.tdp + 120;
    if (psu.watts < draw) issues.push(`Estimated draw is ~${draw}W — the ${psu.watts}W PSU is too small.`);
  }
  return { ok: issues.length === 0, issues };
}

function buildTotal(sel){
  return Object.values(sel).reduce((s,p)=> s + (p ? p.price : 0), 0);
}
function buildDraw(sel){
  const cpu = sel.cpu, gpu = sel.gpu;
  return (cpu ? cpu.tdp : 0) + (gpu ? gpu.tdp : 0) + 120;
}
