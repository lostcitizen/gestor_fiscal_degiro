// Future JavaScript code can go here.
console.log("main.js loaded");

// --- START dashboard.html JS ---
// --- GLOBAL CONFIG ---
Apex.chart = { foreColor: '#e2e8f0', fontFamily: 'Inter, sans-serif' };

let rawData = {};
let globalChart = null;
let globalPortChart = null;
let currentViewYear = null;

let sortConfig = {
    'buys': { key: 'date', dir: 'desc' },
    'sales': { key: 'date', dir: 'desc' },
    'divs': { key: 'date', dir: 'desc' },
    'port': { key: 'total_cost', dir: 'desc' },
    'global-port': { key: 'total_cost', dir: 'desc' }
};

fetch('/api/data').then(res => res.json()).then(data => {
    rawData = data;
    fillYearSelect();
    initGlobal();
});

function fmt(n) { return new Intl.NumberFormat('es-ES', {style:'currency', currency:'EUR'}).format(n); }

function parseDate(dateStr) {
    if(!dateStr) return new Date(0);
    const parts = dateStr.split('-');
    if(parts.length === 3) return new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
    return new Date(dateStr);
}

function getTooltipText(note) {
    if (!note) return "";
    if (note.includes("BLOQ")) return "Pérdida bloqueada temporalmente: Has comprado las mismas acciones 2 meses antes o después de la venta con pérdidas. No puedes deducirla hasta vender las acciones recompradas.";
    if (note.includes("OPA")) return "OPA, Fusión o Liquidación: Salida de acciones compensada con entrada de efectivo en cuenta, no como operación de mercado.";
    if (note.includes("DERECHOS")) return "Venta de Derechos: Ingreso por venta de derechos de suscripción preferente en ampliaciones de capital.";
    if (note.includes("CANJE")) return "Canje/Split Inverso: Salida de acciones antiguas por cambio de ISIN o reorganización, sin flujo de efectivo.";
    if (note.includes("NO ADQ")) return "Advertencia de Datos: No se encontró la compra original de estas acciones en el historial proporcionado (coste asumido 0).";
    return note;
}

function fillYearSelect() {
    const sel = document.getElementById('yearSelect');
    sel.innerHTML = '<option value="" disabled selected>Año...</option>';
    const yearsCopy = [...rawData.global.years_list];
    yearsCopy.sort().reverse().forEach(y => {
        const opt = document.createElement('option');
        opt.value = y; opt.innerText = y;
        sel.appendChild(opt);
    });
}

function showGlobalView() {
    document.getElementById('yearView').classList.add('d-none');
    document.getElementById('globalView').classList.remove('d-none');
    document.getElementById('yearSelect').value = ""; 
    currentViewYear = null;
    initGlobal(); 
}

function handleSort(tableId, key) {
    const conf = sortConfig[tableId];
    if (conf.key === key) conf.dir = conf.dir === 'asc' ? 'desc' : 'asc';
    else { conf.key = key; conf.dir = 'desc'; }
    updateSortIcons(tableId, key, conf.dir);
    if (tableId === 'global-port') renderGlobalPortfolioTable();
    else renderYearTables(currentViewYear);
}

function updateSortIcons(tableId, activeKey, dir) {
    const ths = document.querySelectorAll(`#tbl-${tableId} thead th`);
    ths.forEach(th => {
        th.classList.remove('th-active');
        const icon = th.querySelector('i');
        if(icon) icon.className = 'bi bi-arrow-down-up sort-icon';
    });
    const targetTh = Array.from(ths).find(th => th.getAttribute('onclick')?.includes(`'${activeKey}'`));
    if (targetTh) {
        targetTh.classList.add('th-active');
        const icon = targetTh.querySelector('i');
        if(icon) icon.className = `bi bi-arrow-${dir === 'asc' ? 'up' : 'down'} sort-icon`;
    }
}

function getSortedData(dataArray, config) {
    const key = config.key; const dir = config.dir;
    return [...dataArray].sort((a, b) => {
        let valA = a[key], valB = b[key];
        if (key === 'date') { valA = parseDate(valA).getTime(); valB = parseDate(valB).getTime(); }
        else if (typeof valA === 'string') { valA = valA.toLowerCase(); valB = valB.toLowerCase(); }
        if (valA < valB) return dir === 'asc' ? -1 : 1;
        if (valA > valB) return dir === 'asc' ? 1 : -1;
        return 0;
    });
}

// --- GLOBAL ---
function initGlobal() {
    const g = rawData.global;
    
    // P&L Dual Display
    document.getElementById('g-pnl').innerText = fmt(g.total_pnl);
    document.getElementById('g-pnl').className = `kpi-val ${g.total_pnl>=0?'text-green':'text-red'}`;
    document.getElementById('g-pnl-real').innerText = `Real (Financiero): ${fmt(g.total_pnl_real)}`;

    document.getElementById('g-divs').innerText = fmt(g.total_divs_net);
    document.getElementById('g-fees').innerText = fmt(g.total_fees);
    document.getElementById('g-port').innerText = fmt(g.current_portfolio_value);

    if(globalChart) globalChart.destroy();
    globalChart = new ApexCharts(document.querySelector("#chartGlobalMain"), {
        series: [{ name: 'P&L Real (Ventas)', type: 'column', data: g.chart_pnl }, { name: 'Dividendos', type: 'line', data: g.chart_divs }],
        chart: { 
            height: 350, type: 'line', toolbar: {show: false}, background: 'transparent',
            events: { dataPointSelection: (e, c, cfg) => { 
                const y = g.years_list[cfg.dataPointIndex]; renderYearView(y); document.getElementById('yearSelect').value = y; 
            }}
        },
        stroke: { width: [0, 3], curve: 'smooth' }, labels: g.years_list, xaxis: { type: 'category', tooltip: { enabled: false } },
        yaxis: [{ title: { text: 'P&L Operaciones (€)' }, labels: { formatter: (val) => val.toFixed(0) } }, { opposite: true, title: { text: 'Dividendos (€)' }, labels: { formatter: (val) => val.toFixed(0) } }],
        colors: ['#3b82f6', '#10b981'], plotOptions: { bar: { borderRadius: 4, columnWidth: '40%' } }, legend: { position: 'top' }, theme: { mode: 'dark' }
    });
    globalChart.render();

    renderGlobalPortfolioTable();
    renderGlobalPortChart(g.current_portfolio);
}

function renderGlobalPortfolioTable() {
    const g = rawData.global;
    const sortedData = getSortedData(g.current_portfolio, sortConfig['global-port']);
    const portBody = document.getElementById('global-port-body'); portBody.innerHTML = '';
    sortedData.forEach(p => {
        portBody.innerHTML += `<tr><td class="ps-3 fw-medium">${p.name}</td><td class="text-muted small">${p.isin}</td><td class="text-end font-monospace">${p.qty}</td><td class="text-end font-monospace text-muted">${p.avg_price.toFixed(4)} €</td><td class="text-end font-monospace fw-bold">${fmt(p.total_cost)}</td></tr>`;
    });
    updateSortIcons('global-port', sortConfig['global-port'].key, sortConfig['global-port'].dir);
}

function renderGlobalPortChart(portfolioData) {
    if(globalPortChart) globalPortChart.destroy();
    const labels = [], data = [];
    const validPort = portfolioData.filter(p => p.total_cost > 0).sort((a,b) => b.total_cost - a.total_cost).slice(0, 10);
    validPort.forEach(p => { labels.push(p.name); data.push(Number(p.total_cost.toFixed(2))); });
    
    globalPortChart = new ApexCharts(document.querySelector("#chartGlobalPort"), {
        series: data, labels: labels, chart: { type: 'donut', height: 350, background: 'transparent' },
        stroke: { show: true, width: 2, colors: ['#1e293b'] }, legend: { position: 'bottom', fontSize: '12px' },
        plotOptions: { pie: { donut: { labels: { show: false } } } },
        colors: ['#3b82f6', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316', '#eab308', '#22c55e', '#14b8a6'], theme: { mode: 'dark' }
    });
    if(data.length > 0) globalPortChart.render();
    else document.querySelector("#chartGlobalPort").innerHTML = '<div class="text-center text-muted py-5">Cartera vacía o cerrada</div>';
}

// --- YEAR VIEW ---
function renderYearView(year) {
    if(!year) return;
    currentViewYear = year;
    const d = rawData.years[year];
    document.getElementById('globalView').classList.add('d-none');
    document.getElementById('yearView').classList.remove('d-none');
    document.getElementById('lblYear').innerText = year;
    
    // Update Download Button Link
    document.getElementById('btnDownload').href = `/download/${year}`;

    // P&L Year Dual Display
    document.getElementById('y-pnl').innerText = fmt(d.total_pnl);
    document.getElementById('y-pnl').className = `fs-4 fw-bold ${d.total_pnl>=0?'text-green':'text-red'}`;
    document.getElementById('y-pnl-real').innerText = `Real (Financiero): ${fmt(d.total_pnl_real)}`;

    let divSum = d.dividends.reduce((acc, x) => acc + x.net, 0);
    document.getElementById('y-divs').innerText = fmt(divSum);
    document.getElementById('y-port').innerText = fmt(d.portfolio_value);
    document.getElementById('y-fees').innerText = fmt(d.fees.trading + d.fees.connectivity);

    renderYearTables(year);
}

function renderYearTables(year) {
    const d = rawData.years[year];

    // BUYS
    const buysSorted = getSortedData(d.purchases, sortConfig['buys']);
    const tbBuys = document.getElementById('body-buys'); tbBuys.innerHTML = '';
    buysSorted.forEach(b => {
        tbBuys.innerHTML += `<tr>
            <td class="ps-3 text-secondary">${parseDate(b.date).toLocaleDateString()}</td>
            <td class="fw-medium">${b.product}</td>
            <td class="text-end font-monospace">${b.qty}</td>
            <td class="text-end font-monospace">${fmt(b.price)}</td>
            <td class="text-end font-monospace">${fmt(b.total)}</td>
            <td class="text-end font-monospace text-secondary">${fmt(b.fee)}</td>
        </tr>`;
    });
    updateSortIcons('buys', sortConfig['buys'].key, sortConfig['buys'].dir);

    // SALES
    const salesSorted = getSortedData(d.sales, sortConfig['sales']);
    const tbSales = document.getElementById('body-sales'); tbSales.innerHTML = '';
    salesSorted.forEach(s => {
        let color = s.pnl >= 0 ? 'text-green' : 'text-red';
        
        // Tooltip Logic
        let badge = '';
        if(s.blocked) {
            if (s.blocked_status === 'active') {
                badge = `<span class="badge badge-custom bg-danger bg-opacity-25 text-danger border border-danger" 
                         data-bs-toggle="tooltip" data-bs-placement="top" title="${getTooltipText('BLOQ')}">BLOQUEADO (Hasta ${s.unlock_date})</span>`;
            } else {
                 badge = `<span class="badge badge-custom bg-warning bg-opacity-10 text-warning border border-warning" 
                     data-bs-toggle="tooltip" data-bs-placement="top" title="Bloqueo expirado el ${s.unlock_date}. Ya puedes compensar esta pérdida.">DESBLOQUEADO (${s.unlock_date})</span>`;
            }
        } else if (s.wash_sale_risk) {
            badge = `<span class="badge badge-custom bg-info bg-opacity-25 text-info border border-info" 
                     data-bs-toggle="tooltip" data-bs-placement="top" 
                     title="Pérdida deducible actualmente. PRECAUCIÓN: Si recompras este valor antes del ${s.repurchase_safe_date}, esta pérdida pasará a estar BLOQUEADA.">RIESGO RECOMPRA (Hasta ${s.repurchase_safe_date})</span>`;
        } else if (s.loss_consolidated) {
            badge = `<span class="badge badge-custom bg-success bg-opacity-10 text-success border border-success" 
                     data-bs-toggle="tooltip" data-bs-placement="top" 
                     title="Pérdida firme. Superaste el periodo de 2 meses (${s.repurchase_safe_date}) sin realizar recompras que bloquearan esta pérdida.">DEDUCIBLE</span>`;
        } else if(s.note) {
            let tooltipContent = getTooltipText(s.note);
            let displayNote = s.note.replace('⚠️ NO ADQ ', '');
            badge = `<span class="badge badge-custom bg-info bg-opacity-10 text-info border border-info"
                     data-bs-toggle="tooltip" data-bs-placement="top" title="${tooltipContent}">${displayNote}</span>`;
        }

        if(s.blocked && s.blocked_status === 'active') color = 'text-white text-opacity-50 text-decoration-line-through';
        else if (s.blocked) color = 'text-warning'; // Desbloqueado but was blocked logic (optional, keep readable)
        
        tbSales.innerHTML += `<tr>
            <td class="ps-3 text-secondary">${parseDate(s.date).toLocaleDateString()}</td>
            <td class="fw-medium">${s.product}</td>
            <td class="text-end font-monospace">${s.qty}</td>
            <td class="text-end font-monospace">${fmt(s.sale_net)}</td>
            <td class="text-end font-monospace text-muted">${fmt(s.cost_basis)}</td>
            <td class="text-end font-monospace fw-bold ${color}">${fmt(s.pnl)}</td>
            <td>${badge}</td>
        </tr>`;
    });
    updateSortIcons('sales', sortConfig['sales'].key, sortConfig['sales'].dir);

    // Re-init Bootstrap tooltips for new elements
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // DIVIDENDS
    const divsSorted = getSortedData(d.dividends, sortConfig['divs']);
    const tbDivs = document.getElementById('body-divs'); tbDivs.innerHTML = '';
    divsSorted.forEach(div => {
        tbDivs.innerHTML += `<tr>
            <td class="ps-3 text-secondary">${parseDate(div.date).toLocaleDateString()}</td>
            <td class="fw-medium">${div.product}</td>
            <td><span class="badge bg-secondary bg-opacity-25 text-secondary">${div.currency}</span></td>
            <td class="text-end font-monospace">${div.gross.toFixed(2)}</td>
            <td class="text-end font-monospace text-danger text-opacity-75">-${div.wht.toFixed(2)}</td>
            <td class="text-end font-monospace fw-bold text-green text-opacity-75">+${div.net.toFixed(2)}</td>
        </tr>`;
    });
    updateSortIcons('divs', sortConfig['divs'].key, sortConfig['divs'].dir);

    // PORTFOLIO
    const portSorted = getSortedData(d.portfolio, sortConfig['port']);
    const tbPort = document.getElementById('body-port'); tbPort.innerHTML = '';
    portSorted.forEach(p => {
        tbPort.innerHTML += `<tr>
            <td class="ps-3 fw-medium">${p.name}</td>
            <td class="text-muted small">${p.isin}</td>
            <td class="text-end font-monospace">${p.qty}</td>
            <td class="text-end font-monospace text-muted">${p.avg_price.toFixed(4)} €</td>
            <td class="text-end font-monospace fw-bold">${fmt(p.total_cost)}</td>
        </tr>`;
    });
    updateSortIcons('port', sortConfig['port'].key, sortConfig['port'].dir);
}
// --- END dashboard.html JS ---