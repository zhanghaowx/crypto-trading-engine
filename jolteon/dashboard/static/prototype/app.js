const $ = (selector) => document.querySelector(selector);
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const state = { workspace:'trading', engine:'BTC/USD', period:'1h', feed:'Live', fills:'All', horizon:'+1s', showIds:false, health:'Normal', paramTab:'Engine', scope:'All symbols', group:'Market making', values:{}, saved:{}, acked:{}, run:'r7e88a', source:'All', compare:['r5c1d4','r7e88a'] };

// Two workspaces, because the engine records two independent facts about
// every run and only one of them changes how the screen behaves: data
// read as it happened keeps moving, data read from a recording never
// does. Execution mode - paper or real - rides along as a badge.
// The navigation names the page, so no page opens with a heading of its
// own; the style guide is a document rather than a screen and keeps one.
const pages = {
  monitor:{workspace:'trading', title:'Live monitor'},
  health:{workspace:'trading', title:'Engine health'},
  parameters:{workspace:'trading', title:'Parameters'},
  runs:{workspace:'research', title:'Runs'},
  run:{workspace:'research', title:'Run detail'},
  compare:{workspace:'research', title:'Compare runs'},
  guide:{workspace:null, title:'The Jolteon interface', description:'One visual language. Every page, every component, every state.'},
};
const navItems = { trading:[['health','Health'],['monitor','Live monitor'],['parameters','Parameters']], research:[['runs','Runs'],['compare','Compare']] };
const workspaces = [
  { id:'trading', label:'Trading', home:'monitor', note:'Live engine · refreshes while you watch' },
  { id:'research', label:'Research', home:'runs', note:'Finished runs · fixed results' },
];

// One engine per symbol, and only one of them is running. The other
// stopped two days ago, and every page that meets it has to say so
// quietly: nothing is down when nothing is running.
const engines = [
  { symbol:'BTC/USD', running:true, run:'a83f21' },
  { symbol:'ETH/USD', running:false, run:'b47e19', stopped:'22 Sep 16:00 UTC', ago:'2 days ago' },
];
const engineOf = (symbol=state.engine) => engines.find(e=>e.symbol===symbol);
const isRunning = () => engineOf().running;

// Selected groups from the production catalog, under the part of the
// engine each one configures, so a reader after a fee schedule is not
// scanning past the quoting rules to find it.
const sections = [
  ['Strategy', ['Market making','Quote offset','Fair price signals','Inventory adjustment']],
  ['Venues', ['Kraken','Binance.US']],
  ['Runtime', ['Heartbeat & polling','Logging & storage']],
];
const groups = {
  'Market making': [['Quote size', 'Quantity placed on each side of the book.', 0.001, 'asset', 0.0001], ['Max inventory', 'Maximum absolute inventory held by the strategy.', 0.01, 'asset', 0.001], ['Requote tolerance', 'Price movement required before replacing a quote.', 0, 'USD', 0.01], ['Book depth', 'Number of order book levels used by the strategy.', 10, 'levels', 1]],
  'Quote offset': [['Edge', 'Target edge added to the quote price.', 5, 'USD', 0.1], ['Half spread', 'Distance from fair price on either side.', 50, 'USD', 1]],
  'Fair price signals': [['Max adjustment', 'Maximum combined fair price adjustment.', 5, 'USD', 0.1], ['Momentum scale', 'Weight applied to the momentum signal.', 1, '×', 0.1], ['Microprice scale', 'Weight applied to the microprice signal.', 1, '×', 0.1]],
  'Inventory adjustment': [['Skew per unit', 'Fair price shift for each unit of inventory held.', 2, 'USD', 0.1], ['Max skew', 'Largest shift inventory may apply.', 10, 'USD', 0.5]],
  'Kraken': [['Book depth', 'Levels requested from the venue.', 10, 'levels', 1], ['Maker fee', 'Fee on an order that rests in the book.', 0.16, '%', 0.01], ['Taker fee', 'Fee on an order that trades at once.', 0.26, '%', 0.01]],
  'Binance.US': [['Book depth', 'Levels requested from the venue.', 20, 'levels', 1], ['Maker fee', 'Fee on an order that rests in the book.', 0, '%', 0.01], ['Taker fee', 'Fee on an order that trades at once.', 0.1, '%', 0.01]],
  'Heartbeat & polling': [['Heartbeat interval', 'Time between component status reports.', 10, 's', 1], ['Heartbeat timeout', 'Time without a report before marking a component down.', 30, 's', 1], ['Parameter polling', 'Time between reading parameter updates.', 1, 's', 0.1]],
  'Logging & storage': [['Write batch', 'Recorded signals written in one transaction.', 500, 'rows', 50], ['Flush interval', 'Longest a recorded signal waits before it is written.', 1, 's', 0.1]],
};
// Every value has a scope: the default for all symbols, or one symbol's
// override of it. A symbol inherits each default it does not override,
// and a field says which of those it is showing.
const scopes = ['All symbols', ...engines.map(e=>e.symbol)];
const overrides = { 'BTC/USD': {'Market making:Quote size':0.0005}, 'ETH/USD': {'Market making:Quote size':0.01, 'Market making:Max inventory':0.1} };
for (const scope of scopes) {
  state.values[scope] = {}; state.saved[scope] = {}; state.acked[scope] = {};
  for (const [group, fields] of Object.entries(groups)) for (const [label,,value] of fields) {
    const key = `${group}:${label}`;
    const held = overrides[scope]?.[key] ?? value;
    state.values[scope][key] = state.saved[scope][key] = state.acked[scope][key] = held;
  }
}
const scopeKey = () => state.scope==='All symbols' ? 'All symbols' : state.engine;
// A quantity is in the traded asset, which a default for every symbol
// cannot name and a symbol's own value can.
const unitFor = (unit) => unit==='asset' ? (scopeKey()==='All symbols' ? 'base asset' : shortAsset()) : unit;

// The parameters a run was tuned with, as the recording would hold them:
// an input the run cannot change, not a setting anyone can edit here.
const tuned = (edge, halfSpread, maxAdjustment, quoteSize=0.0005) => ({'Quote offset:Edge':edge, 'Quote offset:Half spread':halfSpread, 'Fair price signals:Max adjustment':maxAdjustment, 'Market making:Quote size':quoteSize, 'Market making:Max inventory':0.01});
const runs = [
  {id:'a83f21', feed:'realtime', exec:'Paper', status:'Running', ran:['23 Sep 10:12', null], data:null, fills:248, notional:42186.50, gross:145.29, fees:16.87, params:tuned(5,50,5)},
  {id:'a21c08', feed:'realtime', exec:'Paper', status:'Completed', ran:['23 Sep 08:00','23 Sep 12:00'], data:null, fills:412, notional:68452.10, gross:242.24, fees:27.38, params:tuned(5,50,5)},
  {id:'b47e19', feed:'realtime', exec:'Paper', status:'Interrupted', ran:['22 Sep 12:00','22 Sep 16:00'], data:null, fills:226, notional:38104.20, gross:107.42, fees:15.24, params:tuned(5,50,5)},
  {id:'r5c1d4', feed:'recorded', exec:'Simulated', status:'Completed', ran:['24 Sep 09:02','24 Sep 09:09'], data:['23 Sep 08:00','23 Sep 12:00'], capture:'a21c08', trades:184215, fills:398, notional:66120.40, gross:232.70, fees:26.44, params:tuned(5,50,5)},
  {id:'r7e88a', feed:'recorded', exec:'Simulated', status:'Completed', ran:['24 Sep 09:14','24 Sep 09:21'], data:['23 Sep 08:00','23 Sep 12:00'], capture:'a21c08', trades:184215, fills:351, notional:58890.10, gross:265.12, fees:23.55, params:tuned(7,50,5)},
  {id:'r9f210', feed:'recorded', exec:'Simulated', status:'Completed', ran:['24 Sep 09:26','24 Sep 09:33'], data:['23 Sep 08:00','23 Sep 12:00'], capture:'a21c08', trades:184215, fills:284, notional:47720.80, gross:252.90, fees:19.08, params:tuned(9,50,7)},
  {id:'rc4b73', feed:'recorded', exec:'Simulated', status:'Completed', ran:['24 Sep 10:05','24 Sep 10:11'], data:['22 Sep 12:00','22 Sep 16:00'], capture:'b47e19', trades:96480, fills:214, notional:36240.00, gross:118.60, fees:14.50, params:tuned(7,50,5)},
];
const byId = (id) => runs.find(r=>r.id===id) || runs[0];
const finished = () => runs.filter(r=>r.status!=='Running');
const isReplay = (run) => run.feed==='recorded';
const runningRun = () => runs.find(r=>r.status==='Running');

const badge = (label, type='neutral') => `<span class="badge ${type}"><span class="dot"></span>${label}</span>`;
const money = (n) => n.toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2});
const signed = (n) => `${n<0?'−':'+'}$${money(Math.abs(n))}`;
const signedSpan = (n) => `<span class="${n<0?'negative':'positive'}">${signed(n)}</span>`;
const netPnl = (run) => run.gross - run.fees;
const price = () => state.engine === 'BTC/USD' ? 83947.95 : 3248.62;
const shortAsset = () => state.engine.split('/')[0];
// The position is the one number a market maker watches, so it leads the
// strip and the panel, and the risk row is the same figure against its
// limit.
const position = () => state.engine === 'BTC/USD' ? {qty:'−0.0032 BTC', held:'0.0032 / 0.0100 BTC', value:268.69, used:32} : {qty:'−0.0480 ETH', held:'0.0480 / 0.1000 ETH', value:155.93, used:48};
const card = (title,subtitle,body,action='',foot='') => `<section class="card"><div class="card-head"><div><h2>${title}</h2>${subtitle?`<p>${subtitle}</p>`:''}</div>${action}</div>${body}${foot?`<div class="card-foot">${foot}</div>`:''}</section>`;
const segments = (items,current,attr) => `<div class="segmented">${items.map(x=>`<button ${attr}="${x}" aria-pressed="${x===current}">${x}</button>`).join('')}</div>`;
const table = (headers,rows,numeric=[]) => `<div class="table-wrap"><table><thead><tr>${headers.map((x,i)=>`<th scope="col" class="${numeric.includes(i)?'num':''}">${x}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((x,i)=>`<td class="${numeric.includes(i)?'num mono':''}">${x}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const engineSelect = () => `<select id="engine" aria-label="Engine">${engines.map(e=>`<option ${state.engine===e.symbol?'selected':''}>${e.symbol}</option>`).join('')}</select>`;
// Every page opens on a strip: labelled cells in one row, the scope and
// the figures a reader checks first, in place of a context bar and a
// row of metric tiles.
const cell = (label, value, cls='') => `<div class="strip-item${cls?` ${cls}`:''}"><span class="strip-label">${label}</span><span class="strip-value">${value}</span></div>`;
const strip = (cells, label) => `<div class="strip" role="region" aria-label="${label}">${cells.join('')}</div>`;

// A replay reads a window of the past during a few minutes of the
// present, so it has two clocks and neither one stands for the other.
const dataWindow = (run) => isReplay(run) ? `${run.data[0]}–${run.data[1].split(' ').pop()}` : `${run.ran[0]}–${(run.ran[1]||'now').split(' ').pop()}`;
const ranWindow = (run) => run.ran[1] ? `${run.ran[0]}–${run.ran[1].split(' ').pop()}` : `${run.ran[0]} · still going`;
const clockMinutes = (stamp) => {const [h,m]=stamp.split(' ').pop().split(':').map(Number);return h*60+m;};
const duration = (run) => {if(!run.ran[1])return 'still going';const spent=clockMinutes(run.ran[1])-clockMinutes(run.ran[0]);return spent>=60?`${Math.floor(spent/60)}h${spent%60?` ${spent%60}m`:''}`:`${spent}m`;};
const sourceBadge = (run) => isReplay(run) ? badge('Replay','info') : badge('Live feed','good');
const statusBadge = (run) => badge(run.status, run.status==='Running'?'good':run.status==='Interrupted'?'warn':'neutral');
const captureChip = (run) => isReplay(run) ? `<button class="chip" data-open-run="${run.capture}" title="Open the run that captured this data">↩ capture <span class="mono">${run.capture}</span></button>` : '';

// A signal that is not yet usable is an ordinary state, not a fault: it
// says so in a quiet badge, and its contribution is "–" rather than a
// red row.
const signalRows = [
  ['Momentum', 'Weighted', 'good', 1.24, 62],
  ['Order flow imbalance', 'Too weak to size from', 'neutral', null, 0],
  ['Inventory adjustment', 'Weighted', 'good', -0.46, 23],
  ['Microprice', 'Warming up', 'neutral', null, 0],
];
const signalSummary = () => {const weighted=signalRows.filter(r=>r[3]!==null);return {weighted, combined:weighted.reduce((sum,r)=>sum+r[3],0)};};
const shortVerdict = {'Too weak to size from':'Too weak'};
const componentKinds = [['Strategy','Market making'],['Execution','Paper execution'],['Market data','Public feed'],['Configuration','Parameters']];
const componentDown = () => state.health==='Feed delayed';

// While the engine runs, the newest fills have not lived long enough to
// be measured at the longer horizons, so those cells are empty rather
// than zero; a stopped session has had every horizon pass.
const fillHorizons = ['At fill','+100ms','+1s','+5s','+30s'];
const markoutBase = {'At fill':0.02,'+100ms':0.01,'+1s':0.04,'+5s':0.03,'+30s':0.05};
function sampleFills() {
 const hour=isRunning()?14:15, minute=isRunning()?31:59;
 return Array.from({length:8},(_,i)=>{
  const sell=i%3===0;
  const markout={};
  fillHorizons.forEach((h,n)=>{markout[h]=(isRunning()&&n>=3&&i<n-2)?null:(i%4===0?-1:1)*(markoutBase[h]+(i%2?.01:0));});
  return {time:`${hour}:${minute-Math.floor(i/2)}:${String(52-i*5).padStart(2,'0')}`, side:sell?'Sell':'Buy', trade:362859-i*137, order:362858-i*137, price:price()+(sell?3:-3)+i*.31, qty:state.engine==='BTC/USD'?'0.0005':'0.0100', fee:0.08, markout};
 });
}

const chartPaths = { '15m': '0,127 24,134 48,120 72,124 96,99 120,105 144,97 168,112 192,90 216,94 240,79 264,86 288,75 312,81 336,62 360,72 384,56 408,63 432,45 456,54 480,30 504,37 528,28 552,35 576,20 600,24', '1h':'0,146 24,138 48,144 72,130 96,132 120,110 144,117 168,107 192,117 216,94 240,96 264,101 288,87 312,94 336,61 360,70 384,56 408,62 432,44 456,51 480,32 504,39 528,27 552,30 576,15 600,20', '4h':'0,150 24,147 48,154 72,151 96,137 120,139 144,123 168,129 192,121 216,128 240,97 264,107 288,91 312,103 336,84 360,93 384,69 408,80 432,53 456,69 480,48 504,53 528,34 552,40 576,24 600,20' };

// ---- Live monitor: the cockpit ---------------------------------------
// The monitor is one screen, shaped around what a market maker watches:
// the position against its limit, where our quotes rest against the fair
// price, and what each fill earned. Nothing here scrolls at a desktop
// width; the detail a reader wants next is a panel away, not a page.
const panelRow = (label, value) => `<div class="panel-row"><span>${label}</span><span class="mono">${value}</span></div>`;
const ourQuotes = () => ({bid:price()-2.57-1.91, ask:price()+2.57+1.91});
function statusStrip() {
 const engine=engineOf(); const running=engine.running; const p=position();
 const run=running?runningRun():byId(engine.run);
 const {combined}=signalSummary(); const {bid,ask}=ourQuotes();
 const marked=running?128.42:netPnl(run);
 const feed = running
  ? `<span class="live-dot${state.feed==='Live'?'':' paused'}" aria-hidden="true"></span><span>${state.feed==='Live'?'Updated 3s ago':'Paused · 14:32:08 UTC'}</span>${segments(['Live','Paused'],state.feed,'data-feed')}`
  : `<span class="live-dot paused" aria-hidden="true"></span><span class="muted">Stopped ${engine.stopped}</span>`;
 const components = !running ? badge('Stopped','neutral') : componentDown() ? badge('1 of 4 down','bad') : badge('4 of 4 reporting','neutral');
 return strip([
  cell(`Engine · run <span class="mono">${run.id}</span>`, `${engineSelect()}${badge('Paper','info')}${running?badge('Live feed','good'):badge('Stopped','neutral')}`),
  cell('Feed', feed),
  cell('Position', `<span class="mono">${p.qty}</span><span class="track"><i style="width:${p.used}%"></i></span><span class="muted small">${p.used}%</span>`),
  cell('Marked PnL', `<span class="mono ${marked<0?'negative':'positive'}">${signed(marked)}</span>`),
  cell('Our quotes · fair', `<span class="mono"><span class="positive">${money(bid)}</span> <span class="muted">/</span> <span class="negative">${money(ask)}</span> <span class="muted">·</span> <span class="info">${money(price()+combined)}</span></span>`),
  cell('Components', components, 'grow'),
 ], 'Engine status');
}
function stoppedNotice() {
 const engine=engineOf(); const run=byId(engine.run);
 return `<div class="banner neutral" role="status"><span><strong>Nothing is running for ${state.engine}.</strong> Its last session, <b class="mono">${run.id}</b>, was ${run.status.toLowerCase()} ${engine.stopped} after ${duration(run)}. The figures below are its final state and will not change.</span><button class="chip" data-open-run="${run.id}">Open it in Research →</button></div>`;
}
function positionPanel(run) {
 const engine=engineOf(); const running=engine.running; const p=position();
 const {combined}=signalSummary();
 const marked=running?128.42:netPnl(run);
 const cash=marked+p.value;
 const [fills,buys,sells]=running?[248,126,122]:[run.fills,Math.ceil(run.fills/2),Math.floor(run.fills/2)];
 const fees=running?16.87:run.fees;
 const signalLines=signalRows.map(([name,verdict,tone,value])=>panelRow(`${name} ${badge(shortVerdict[verdict]||verdict,tone)}`, value===null?'<span class="muted">–</span>':signedSpan(value))).join('');
 const componentLines=componentKinds.map(([,name],i)=>{const down=running&&componentDown()&&i===2;return panelRow(name, running?badge(down?'Down · 42 s ago':'Normal · 2 s ago',down?'bad':'good'):badge('Stopped','neutral'));}).join('');
 return `<section class="card"><div class="card-head"><div><h2>Position</h2><p>${state.engine} · ${running?'live':'final'}</p></div>${badge('OK','good')}</div><div class="card-body">`
  +`<div class="panel-big">${p.qty}</div><div class="panel-sub">−$${money(p.value)} at ${running?'mid':'the last mid'}</div>`
  +`<div class="track"><i style="width:${p.used}%"></i></div><div class="risk-meta"><span class="mono">${p.held}</span><span>${p.used}% of limit</span></div>`
  +`<div class="panel-title">PnL</div><div class="panel-rows">${panelRow('Marked PnL',`<strong>${signedSpan(marked)}</strong>`)}${panelRow('Cash flow',signedSpan(cash))}${panelRow(running?'Inventory at mid':'Inventory at the last mid',signedSpan(-p.value))}${panelRow('Fees',`$${money(fees)}`)}${panelRow('Fills',`${fills} <span class="muted">· ${buys} buy / ${sells} sell</span>`)}</div>`
  +`<div class="panel-title">Fair price signals</div><div class="panel-rows">${signalLines}${panelRow('Combined adjustment',`<strong>${signed(combined)}</strong>`)}</div>`
  +`<div class="panel-title">Components</div><div class="panel-rows">${componentLines}</div>`
  +`</div></section>`;
}
// One column of prices with the market's bids and asks on either side,
// our own quotes tagged at the level they rest on, and the adjusted fair
// price drawn through it: where we quote against where we think the
// price is, in one look.
function ladder() {
 const engine=engineOf(); const mid=price(); const {combined}=signalSummary(); const fair=mid+combined;
 const levels=7, size=(i)=>0.0238+i*.0031, cum=(i)=>(i+1)*.0238+i*(i+1)*.0031/2, deepest=cum(levels-1);
 const rows=[];
 for(let i=levels-1;i>=0;i--) rows.push({side:'ask',price:mid+2.57+i*1.91,size:size(i),depth:cum(i)/deepest*100,own:i===1});
 rows.push({mid:true,price:mid});
 for(let i=0;i<levels;i++) rows.push({side:'bid',price:mid-2.57-i*1.91,size:size(i),depth:cum(i)/deepest*100,own:i===1});
 let fairDrawn=false;
 const html=rows.map(r=>{
  let out='';
  if(!fairDrawn&&r.price<fair){out+=`<div class="lad-fair"><span>fair ${money(fair)} · ${signed(combined)} adjustment</span></div>`;fairDrawn=true;}
  if(r.mid) return out+`<div class="lad-mid"><span>Mid <strong>${money(mid)}</strong></span><span>Spread <strong>5.14</strong> USD · ${(5.14/mid*1e4).toFixed(2)} bps</span></div>`;
  const bar=`style="--depth:${r.depth.toFixed(1)}%"`;
  return out+`<div class="lad-row ${r.side}${r.own?' own':''}"><span class="lad-size bid" ${r.side==='bid'?bar:''}>${r.side==='bid'?r.size.toFixed(4):''}</span><span class="lad-price">${r.own?'<span class="tag">ours</span>':''}${money(r.price)}</span><span class="lad-size ask" ${r.side==='ask'?bar:''}>${r.side==='ask'?r.size.toFixed(4):''}</span></div>`;
 }).join('');
 return card('Price ladder',`${state.engine} · 7 levels per side`,`<div class="lad-head"><span>Bid size (${shortAsset()})</span><span>Price (USD)</span><span>Ask size (${shortAsset()})</span></div><div class="ladder">${html}</div>`, engine.running?badge('Snapshot','neutral'):badge(`Last snapshot · ${engine.stopped}`,'neutral'), `<span>Depth is cumulative size · <span class="tag">ours</span> is our resting quote</span><span class="mono">fair ${signed(combined)}</span>`);
}
// The PnL line with every fill on it, so the eye can tell which fills
// earned it. Buys hang under the line, sells sit above it.
function pnlChart(run) {
 const running=isRunning(); const period=running?state.period:'4h';
 const W=560, H=210, sx=(W-70)/600;
 const pts=chartPaths[period].split(' ').map(p=>p.split(',').map(Number)).map(([x,y])=>[x*sx,y]);
 const line=pts.map(p=>p.join(',')).join(' ');
 const top=running?128.42:netPnl(run);
 const ticks=running?(period==='15m'?['14:17','14:22','14:27','14:32']:period==='4h'?['10:32','11:52','13:12','14:32']:['13:32','13:52','14:12','14:32']):['12:00','13:20','14:40','16:00'];
 const markers=pts.filter((_,i)=>i>=2&&i%2===0).map(([x,y],n)=>n%3===0
  ?`<path d="M${(x-4).toFixed(1)},${y-13} L${(x+4).toFixed(1)},${y-13} L${x.toFixed(1)},${y-6} Z" fill="var(--negative)"/>`
  :`<path d="M${(x-4).toFixed(1)},${y+13} L${(x+4).toFixed(1)},${y+13} L${x.toFixed(1)},${y+6} Z" fill="var(--positive)"/>`).join('');
 return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Illustrative marked PnL over ${running?`the selected ${period} window`:'the whole session'}, with each fill marked on the line. Not live data."><defs><linearGradient id="pnl-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--positive)" stop-opacity=".12"/><stop offset="100%" stop-color="var(--positive)" stop-opacity="0"/></linearGradient></defs>${[20,65,110,155].map((y,i)=>`<line class="chart-grid" x1="0" x2="${(600*sx).toFixed(1)}" y1="${y}" y2="${y}"/><text x="${(600*sx+10).toFixed(1)}" y="${y+4}">$${money(top*(3-i)/3)}</text>`).join('')}<polygon points="0,170 ${line} ${(600*sx).toFixed(1)},170" fill="url(#pnl-area)"/><polyline points="${line}" class="chart-line"/>${markers}${ticks.map((x,i)=>`<text x="${(i*190*sx).toFixed(1)}" y="200">${x}</text>`).join('')}</svg>`;
}
function pnlCard(run) {
 const running=isRunning();
 return card('Session PnL with fills', running?'Marked PnL · USD':`Marked PnL · USD · ${dataWindow(run)} UTC`, `<div class="card-body">${pnlChart(run)}</div>`, running?segments(['15m','1h','4h'],state.period,'data-period'):badge('Final','neutral'), `<span><span class="legend-line"></span> Marked PnL · <span class="positive">▲</span> buy · <span class="negative">▼</span> sell</span><span>${running?'Illustrative':'Whole session'} · Time (UTC)</span>`);
}
// One signed column, switched by horizon, in place of one per horizon;
// the identifiers wait behind a toggle; the symbol is the strip's.
function fillsTape(run) {
 const running=isRunning();
 const rows=sampleFills().filter(x=>state.fills==='All'||x.side===state.fills);
 const ids=state.showIds?['Trade','Order']:[];
 const h=state.horizon;
 const headers=['Time',...ids,'Side','Price',`Qty (${shortAsset()})`,h==='At fill'?'Edge at fill':`Markout ${h}`];
 const numeric=headers.map((_,i)=>i).filter(i=>i>=1+ids.length+1);
 const cells=(x)=>[x.time,...(state.showIds?[String(x.trade),String(x.order)]:[]),badge(x.side,x.side==='Buy'?'good':'bad'),money(x.price),x.qty,x.markout[h]===null?'<span class="muted">–</span>':signedSpan(x.markout[h])];
 const total=running?248:run.fills;
 return card('Fills', running?'Newest first · UTC':`Final fills of run ${run.id} · UTC`, `<div class="tape">${table(headers,rows.map(cells),numeric)}</div>`, `<div class="inline">${segments(['All','Buy','Sell'],state.fills,'data-fill')}${segments(fillHorizons,state.horizon,'data-horizon')}</div>`, `<span>${rows.length} of ${total} fills · a horizon not yet passed is “–”</span><span class="inline"><button class="text-button" id="toggle-ids" aria-pressed="${state.showIds}">${state.showIds?'Hide IDs':'Show IDs'}</button><button class="text-button" id="export">↓ Export CSV</button></span>`);
}
function quality(buy=126, sell=122, scope='This session') {return card('Execution quality',`Average markout per fill · ${scope}`,table(['Side','Fills','+100ms','+1s','+5s','+30s'],[['Buy',String(buy),'+$0.02','+$0.04','+$0.03','−$0.01'],['Sell',String(sell),'+$0.03','+$0.04','+$0.02','–']],[1,2,3,4,5]),'', '<span>USD, against recorded fair prices at each horizon · a missing measurement stays “–”</span>');}
function monitor() {
 const engine=engineOf(); const running=engine.running; const run=running?runningRun():byId(engine.run);
 const [buys,sells]=running?[126,122]:[Math.ceil(run.fills/2),Math.floor(run.fills/2)];
 return statusStrip()+(running?'':stoppedNotice())+`<div class="cockpit-grid">${positionPanel(run)}<div class="stack">${ladder()}${quality(buys,sells,running?'This session':'Whole session')}</div><div class="stack">${pnlCard(run)}${fillsTape(run)}</div></div>`;
}

// ---- Health -----------------------------------------------------------
// Health reads every engine, so it opens on the totals and then gives
// each engine a card of its components. A stopped engine's components
// stopped with it: they are not down, and the page does not count them.
const sampleErrors = [
  ['14:31:26','Public feed','Error','Heartbeat timeout exceeded · 42 s without a report'],
  ['14:28:03','Paper execution','Error','Order rejected by venue · price 83,944.12 outside allowed band'],
  ['14:22:47','Public feed','Warning','Order book snapshot arrived out of sequence · resynchronised from level 1'],
  ['14:05:12','Parameters','Error','Parameter store locked by another writer · retried after 1 s'],
  ['13:58:41','Market making','Warning','Quote replaced 14 times in 10 s · requote tolerance may be too tight'],
];
function errorRows(warning){
 const shown = warning ? sampleErrors : sampleErrors.slice(1);
 return shown.map(([time,component,level,message])=>[time,component,badge(level,level==='Error'?'bad':'warn'),message]);
}
const heartbeatBars = (down) => `<svg class="beats" viewBox="0 0 230 16" role="img" aria-label="Illustrative heartbeat history">${Array.from({length:32},(_,n)=>`<rect x="${n*7.2}" y="2" width="4" height="12" rx="1" fill="${down&&n>24?'var(--negative)':'var(--heartbeat-ok)'}"/>`).join('')}</svg>`;
function engineCard(engine, warning) {
 const run=byId(engine.run);
 const rows=componentKinds.map(([kind,name],i)=>{
  if(!engine.running) return [name,kind,badge('Stopped','neutral'),`<span class="muted">${engine.stopped}</span>`,'<span class="muted small">none expected while stopped</span>'];
  const down=warning&&i===2;
  return [name,kind,badge(down?'Down':'Normal',down?'bad':'good'),down?'42 s ago':'2 s ago',heartbeatBars(down)];
 });
 return `<section class="card"><div class="card-head"><div><h2>Kraken · ${engine.symbol} ${engine.running?badge('Running','good'):badge('Stopped','neutral')}</h2><p>Run <span class="mono">${run.id}</span> · ${run.exec} · ${engine.running?`started ${run.ran[0]} UTC`:`${run.status.toLowerCase()} ${engine.stopped} · ${engine.ago}`}</p></div>${engine.running?'':`<button class="chip" data-open-run="${run.id}">Open in Research →</button>`}</div>${table(['Component','Kind','State','Last seen','Heartbeat history'],rows)}</section>`;
}
function health() {
 const warning=componentDown();
 const quiet=state.health==='Normal';
 const rows=quiet?[]:errorRows(warning);
 const errorCount=rows.filter(r=>r[2].includes('Error')).length;
 const live=engines.filter(e=>e.running), stopped=engines.filter(e=>!e.running);
 const summary=strip([
  cell('Engines', `<strong>${live.length} / ${engines.length}</strong> running${stopped.length?` <span class="muted">· ${stopped.map(e=>e.symbol).join(', ')} stopped ${stopped[0].ago}</span>`:''}`),
  cell('Components down', warning?badge('1 · Public feed timed out','bad'):badge('0 · every running component reports in time','neutral')),
  cell('Recorded errors', `<strong>${errorCount}</strong>${rows.length-errorCount?` <span class="muted">· ${rows.length-errorCount} warning${rows.length-errorCount===1?'':'s'}</span>`:''}`),
  cell('Heartbeat timeout', '30 s'),
  cell('Snapshot', '<span class="mono">14:32:08 UTC</span>'),
  cell('Preview state', `<select id="health-state" aria-label="Preview state">${['Normal','Errors recorded','Feed delayed'].map(x=>`<option ${state.health===x?'selected':''}>${x}</option>`).join('')}</select>`, 'grow'),
 ], 'Health summary');
 return summary+(warning?'<div class="banner"><strong>Public feed needs attention.</strong> Last heartbeat was 42 seconds ago; the configured timeout is 30 seconds. Prices on the monitor may be stale.</div>':'')+`<div class="grid">${engines.map(e=>engineCard(e,warning)).join('')}</div>`+card('Error log','Recorded errors and warnings across all engines · newest first',rows.length?table(['Time (UTC)','Component','Level','Message'],rows):'<div class="empty"><div class="empty-icon">✓</div><h3>No errors recorded</h3><p>Errors will appear here with their engine, timestamp, and message.</p></div>',badge(rows.length?`${errorCount} error${errorCount===1?'':'s'} · ${rows.length-errorCount} warning${rows.length-errorCount===1?'':'s'}`:'0 errors',errorCount?'bad':rows.length?'warn':'neutral'),rows.length?'<span>An error does not always mean a component is down.</span>':'');
}

// ---- Parameters -------------------------------------------------------
// Six states a field can be in, kept apart: the default, an inherited
// default, a symbol's override, an edit not yet committed, a committed
// value the engine has not yet read, and one it has.
function pending(){return scopes.flatMap(scope=>Object.keys(state.values[scope]).filter(k=>state.values[scope][k]!==state.saved[scope][k]).map(k=>[scope,k]));}
function pendingLabel(){const changes=pending();if(!changes.length)return 'No unsaved changes';const touched=new Set(changes.map(([scope])=>scope)).size;return `${changes.length} unsaved change${changes.length===1?'':'s'}${touched>1?` across ${touched} scopes`:''}`;}
function fieldState(key){
 const scope=scopeKey(); const held=state.values[scope][key], saved=state.saved[scope][key], acked=state.acked[scope][key];
 if(held!==saved) return badge('Pending','warn');
 if(saved!==acked) return badge('Stored · awaiting engine','info');
 if(scope==='All symbols') return badge('Default','neutral');
 return saved!==state.saved['All symbols'][key] ? badge('Override','info') : badge('Inherited','neutral');
}
function settingsFields() {const scope=scopeKey();return groups[state.group].map(([label,help,,unit,step])=>{const key=`${state.group}:${label}`;const id=`field-${label.replaceAll(' ','-')}`;return `<div class="setting"><div><div class="setting-label"><label for="${id}">${label}</label><span data-state-for="${key}">${fieldState(key)}</span></div><p>${help}</p></div><div class="setting-control"><input id="${id}" data-field="${key}" type="number" min="0" step="${step}" value="${state.values[scope][key]}" required><span class="unit">${unitFor(unit)}</span></div></div>`}).join('');}
function parameters() {
 const engine=engineOf();
 const reaches = state.scope==='All symbols' ? engines.some(e=>e.running) : engine.running;
 const count=pending().length;
 const viewer=card('Viewer settings','Preferences for this preview only.',`<div class="setting"><div><label for="compact">Compact table rows</label><p>Reduce vertical spacing in data tables.</p></div><input type="checkbox" id="compact" ${document.body.classList.contains('compact')?'checked':''}></div><div class="setting"><div><h3>Time display</h3><p>One explicit timezone across this prototype.</p></div><span class="badge neutral">UTC</span></div>`);
 const scopeStrip=strip([
  cell('Applies to', segments(['All symbols',state.engine],scopeKey(),'data-scope')),
  cell('Reach', reaches?badge('Reaches the running engine','warn'):badge(`${state.engine} is stopped · applies when it next starts`,'neutral')),
  cell('Polled', 'every 1 s'),
  cell('Finished runs', '<span class="muted">keep the values they ran with</span>', 'grow'),
 ], 'Edit scope');
 const editor=`<div class="settings-layout"><aside class="settings-nav" aria-label="Parameter groups">${sections.map(([title,names])=>`<h4>${title}</h4>${names.map(x=>`<button data-group="${x}" aria-pressed="${x===state.group}">${x}</button>`).join('')}`).join('')}<p>Selected groups from the existing parameter catalog.</p></aside><div>${card(state.group,scopeKey()==='All symbols'?'Defaults for every symbol. A symbol may override any of them.':`Values for ${state.engine}. An inherited value follows the default until it is overridden here.`,`<form id="parameter-form">${settingsFields()}</form><details><summary>How changes take effect</summary><p>Committed values are stored apart from the engine's recording, and the engine reads them on its next poll. A field says “awaiting engine” until it has; a stopped engine reads them when it next starts. This prototype only demonstrates the flow.</p></details>`)}<div class="save-bar"><div><p id="pending-label">${pendingLabel()}</p><small>Review the exact values and their scope before applying.</small></div><div class="actions"><button id="revert" ${!count?'disabled':''}>Revert</button><button id="review" class="primary" ${!count?'disabled':''}>Review changes</button></div></div></div></div>`;
 return statusStrip()+`<div class="tabs" aria-label="Parameter type">${['Engine','Dashboard'].map(x=>`<button data-param-tab="${x}" aria-pressed="${state.paramTab===x}">${x}</button>`).join('')}</div>`+(state.paramTab==='Dashboard'?viewer:scopeStrip+editor);
}

// ---- Research ---------------------------------------------------------
const horizons=[['At fill',1,1],['+100ms',.9535,1],['+1s',.9185,.998],['+5s',.8665,.992],['+30s',.7905,.974]];
function economics(run){return horizons.map(([label,factor,share])=>{const gross=run.gross*factor,fees=run.fees*share;return {label,share,gross,fees,net:gross-fees,bps:(gross-fees)/run.notional*10000,adverse:factor===1?null:gross-run.gross};});}
function economicsCard(run){
 return card('Execution economics','Markout at each horizon, net of fees on measured fills',table(['Horizon','Measured','Gross (USD)','Fees (USD)','Net (USD)','Net (bps)','Adverse selection (USD)'],economics(run).map(r=>[r.label,`${(r.share*100).toFixed(1)}%`,signed(r.gross),`$${money(r.fees)}`,signedSpan(r.net),r.bps.toFixed(2),r.adverse===null?'–':signedSpan(r.adverse)]),[1,2,3,4,5,6]),badge('Final result'),'<span>Measured share is the notional with a recorded fair price close enough to measure against.</span>');
}
// The same card on both sides of the workspace split would be wrong:
// here the values are what the run was handed, and nothing on screen may
// suggest otherwise.
function parameterSetCard(run){
 const rows=Object.entries(run.params).map(([key,value])=>{const live=state.saved['BTC/USD'][key];return [key.replace(':',' · '),String(value),live===value?'<span class="muted">same</span>':`<span class="mono">${live}</span>`];});
 return card('Parameters this run used','Recorded with the run · read-only',table(['Parameter','This run','Current live value'],rows,[1,2]),badge('Frozen','neutral'),`<span>Editing belongs to the running engine, under Trading.</span><a class="text-button" href="#compare">Compare with another run ↗</a>`);
}
function readTheNumbers(run){
 return card('Read the numbers','Different measures answer different questions','<div class="card-body"><ul class="rules"><li><strong>Marked PnL</strong> combines cash flow with the value of remaining inventory.</li><li><strong>Net markout</strong> subtracts measured-fill fees from gross markout at each horizon.</li><li><strong>Measured share</strong> makes incomplete coverage explicit. Missing data is shown as “–”.</li>'+(isReplay(run)?`<li><strong>Two clocks.</strong> This run read ${dataWindow(run)} of recorded market data, and took ${duration(run)} of wall clock to do it.</li>`:`<li><strong>One clock.</strong> A live session reads the market as it happens, so its run window is its data window: ${duration(run)} in all.</li>`)+'<li><strong>Adverse selection</strong> is what a fill gave back as the market moved on, so it grows with the horizon.</li></ul></div>');
}
function runDetail(){
 const run=byId(state.run);
 const options=finished().map(r=>`<option value="${r.id}" ${state.run===r.id?'selected':''}>${r.id} · ${isReplay(r)?'Replay':'Live feed'} · ${dataWindow(r)}</option>`).join('');
 const head=strip([
  cell('Run', `<select id="run-select" aria-label="Run">${options}</select><a class="text-button" href="#runs">← All runs</a>`),
  cell('Mode', `${sourceBadge(run)}${badge(run.exec,'info')}${statusBadge(run)}${captureChip(run)}`),
  cell('Data window', `<span class="mono">${dataWindow(run)} UTC</span>`),
  cell('Ran', `<span class="mono">${ranWindow(run)}</span> <span class="muted">· ${duration(run)}${isReplay(run)?` · ${run.trades.toLocaleString('en-US')} market trades`:''}</span>`),
  cell('Marked PnL', `<span class="mono">${signedSpan(netPnl(run))}</span>`),
  cell('Notional', `<span class="mono">$${money(run.notional)}</span>`),
  cell('Fees', `<span class="mono">$${money(run.fees)}</span>`),
  cell('Fills', `<span class="mono">${run.fills}</span>`, 'grow'),
 ], 'Run scope');
 return head+`<div class="grid-wide"><div class="stack">${economicsCard(run)}${quality(Math.ceil(run.fills/2),Math.floor(run.fills/2),'Whole run')}</div><div class="stack">${parameterSetCard(run)}${readTheNumbers(run)}</div></div>`;
}
function runLibrary(){
 const shown=finished().filter(r=>state.source==='All'||(state.source==='Replay')===isReplay(r));
 const open=isRunning()?runningRun():null;
 const rows=shown.map(r=>[`<button class="link-id mono" data-open-run="${r.id}">${r.id}</button>`,`${sourceBadge(r)} ${badge(r.exec,'info')}`,`<span class="mono">${dataWindow(r)}</span>${isReplay(r)?`<span class="muted small"> · from ${r.capture}</span>`:'<span class="muted small"> · as it ran</span>'}`,`<span class="mono muted">${ranWindow(r)}</span>`,String(r.fills),`$${money(r.notional)}`,signedSpan(netPnl(r)),statusBadge(r)]);
 const head=strip([
  cell('Engine', `${engineSelect()}<span class="muted">Kraken / Market making</span>`),
  cell('Source', segments(['All','Live feed','Replay'],state.source,'data-source')),
  cell('Finished runs', `<strong>${finished().length}</strong> <span class="muted">· ${runs.filter(isReplay).length} replays over 2 captured windows</span>`),
  cell('Best net PnL', `<span class="mono positive">${signed(Math.max(...finished().map(netPnl)))}</span>`),
  cell('Live sessions', `<strong>${runs.filter(r=>!isReplay(r)).length}</strong> <span class="muted">· ${open?'1 still running':'none running'}</span>`),
  cell('Times', 'UTC', 'grow'),
 ], 'Library scope');
 return head+card('Finished runs',`${shown.length} shown · select a run to open it, or compare two of them`,table(['Run','Mode','Data window','Ran','Fills','Notional','Net PnL','Status'],rows,[4,5,6]),`<a class="text-button" href="#compare">Compare two runs ↗</a>`,`<span>${open?`Run <b class="mono">${open.id}</b> is still going and is not measured here.`:`Nothing is running for ${state.engine}; every recorded run has finished.`}</span>${open?'<a class="text-button" href="#monitor">Watch it live ↗</a>':''}`);
}
function compare(){
 const [a,b]=state.compare.map(byId);
 const sameWindow=dataWindow(a)===dataWindow(b);
 const select=(side,current)=>`<select data-compare="${side==='A'?0:1}" aria-label="Run ${side}">${finished().map(r=>`<option value="${r.id}" ${current===r.id?'selected':''}>${r.id} · ${isReplay(r)?'Replay':'Live feed'} · ${dataWindow(r)}</option>`).join('')}</select>`;
 // Only PnL has a direction that means better or worse. Fewer fills is
 // not a loss and a smaller fee bill is not a shortfall, so those deltas
 // carry their sign without carrying a colour.
 const delta=(x,y,format,semantic=false)=>{const d=y-x;const sign=d<0?'−':d>0?'+':'';const tone=semantic?(d<0?'negative':'positive'):'muted';return `<span class="mono">${format(y)}</span> <span class="small ${tone}">${sign}${format(Math.abs(d)).replace(/^[+−]/,'')} vs A</span>`;};
 const rowsA=economics(a),rowsB=economics(b);
 const diffs=Object.keys(a.params).filter(k=>a.params[k]!==b.params[k]);
 const head=strip([
  cell('Run A', select('A',a.id)),
  cell('Run B', select('B',b.id)),
  cell('Data window', sameWindow?`<span class="mono">${dataWindow(a)} UTC</span> <span class="muted">· both</span>`:badge('Different windows','warn')),
  cell('Net PnL · B', delta(netPnl(a),netPnl(b),v=>signed(v),true)),
  cell('Fills · B', delta(a.fills,b.fills,v=>String(Math.round(v)))),
  cell('Notional · B', delta(a.notional,b.notional,v=>`$${money(v)}`)),
  cell('Fees · B', delta(a.fees,b.fees,v=>`$${money(v)}`), 'grow'),
 ], 'Comparison scope');
 const params=card('What differed in the parameters',diffs.length?'Only the values that are not the same in both runs':'Both runs were handed the same parameters',diffs.length?table(['Parameter',`A · ${a.id}`,`B · ${b.id}`,'Change'],diffs.map(k=>[k.replace(':',' · '),String(a.params[k]),String(b.params[k]),`<span class="${b.params[k]>a.params[k]?'positive':'negative'}">${b.params[k]>a.params[k]?'↑':'↓'} ${(b.params[k]-a.params[k]).toFixed(4).replace(/\.?0+$/,'')}</span>`]),[1,2,3]):'<div class="empty"><div class="empty-icon">=</div><h3>Identical parameter sets</h3><p>Any difference in the results came from the data or from the run itself.</p></div>',badge(`${diffs.length} of ${Object.keys(a.params).length} differ`,diffs.length?'info':'neutral'),'<span>A replay is worth running when exactly one thing changes between two of them.</span>');
 const markouts=card('Net markout by horizon','Run B measured against run A at each horizon',table(['Horizon',`A · net (USD)`,`B · net (USD)`,'Δ (USD)','Δ (bps)'],rowsA.map((r,i)=>[r.label,signed(r.net),signed(rowsB[i].net),signedSpan(rowsB[i].net-r.net),(rowsB[i].bps-r.bps).toFixed(2)]),[1,2,3,4]),'',`<span>${sameWindow?'Same data, so the difference is the parameters and the run.':'Different data windows — read this comparison with care.'}</span>`);
 return head+(sameWindow?'':`<div class="banner"><strong>These runs read different data.</strong> Run A covers ${dataWindow(a)} and run B covers ${dataWindow(b)}, so the difference below is mostly the market, not the parameters. Replay both over one window to compare them.</div>`)+`<div class="grid">${params}${markouts}</div>`;
}

// ---- Style guide ------------------------------------------------------
function guide() {
 return `<section class="guide-intro"><div><div class="eyebrow">DESIGN SYSTEM / 02</div><h2>One screen.<br>Every number in its place.</h2><p>A cockpit for watching an engine trade: the position, the quotes against the fair price and what each fill earned, without scrolling.</p></div><div class="guide-principles"><div><strong>01 &nbsp; Context before content</strong><p>Every page opens on a strip that names the engine, run, mode and freshness.</p></div><div><strong>02 &nbsp; Live, stopped and finished look different</strong><p>Only a live feed gets a pulse and a refresh control. A stopped engine is quiet, not alarming.</p></div><div><strong>03 &nbsp; Dense, not crowded</strong><p>Small type, tight insets, one scale of spacing, and a rule between every row.</p></div></div></section><div class="grid">${card('Two workspaces','Market data mode decides which one a screen belongs to',`<div class="card-body"><div class="workspace-compare"><div><div class="eyebrow">TRADING</div><p class="small">One engine reading a live feed, right now.</p><ul class="rules"><li>Refreshes, and says when it last did.</li><li>Parameters are editable and reach the engine.</li><li>Component health matters.</li><li>Paper or real is a badge, not a separate place.</li></ul></div><div><div class="eyebrow">RESEARCH</div><p class="small">Runs that have finished — live sessions and replays alike.</p><ul class="rules"><li>Never refreshes; the numbers are final.</li><li>Parameters are a frozen input, shown read-only.</li><li>A replay states both its clocks and its capture.</li><li>Comparing two runs is the point of the workspace.</li></ul></div></div></div>`)}${card('Page anatomy','The same sequence on every page','<div class="card-body"><ol class="rules"><li>The navigation names the page; no heading repeats it.</li><li>A status strip: labelled cells with the scope, the mode, the freshness or the data window, and the figures a reader checks first.</li><li>Panels in an aligned grid, sized to fit one screen at a desktop width.</li><li>Tables and detail below, dense, ruled between rows.</li><li>Quiet empty and stopped states, and explicit error recovery.</li></ol></div>')}</div><div class="grid">${card('Color tokens','Slate: a neutral foundation with purposeful accents',`<div class="card-body swatches">${[['Canvas','--canvas'],['Surface','--surface'],['Text','--ink'],['Secondary','--muted'],['Brand','--accent'],['Positive','--positive'],['Negative','--negative'],['Warning','--warning']].map(([name,token])=>`<div class="swatch"><div class="swatch-color" style="background:var(${token})"></div><strong>${name}</strong><span class="mono">${cssVar(token)}</span></div>`).join('')}</div>`)}${card('Typography','One sans-serif family, tabular figures, a monospace stack for prices',`<div class="card-body"><div class="type-row"><span class="panel-big">−0.0032 BTC</span><small>26 / 500 · the panel's figure</small></div><div class="type-row"><h2>Card heading</h2><small>13 / 600</small></div><div class="type-row"><span class="strip-label">Strip label</span><small>10 / 600 · letter-spaced</small></div><div class="type-row"><span>Body and controls</span><small>12 / 400–500</small></div><div class="type-row"><span class="mono positive">+$128.42</span><small>monospace · tabular</small></div></div>`)}</div><div class="grid">${card('Status and interaction','Status must remain understandable without color',`<div class="card-body"><div class="status-samples">${badge('Running','good')}${badge('Live feed','good')}${badge('Replay','info')}${badge('Elevated','warn')}${badge('Down','bad')}${badge('Paper','info')}${badge('Stopped')}${badge('Warming up')}${badge('Frozen')}${badge('Completed')}</div><div class="actions"><button class="primary" id="guide-action">Primary action</button><button id="guide-secondary">Secondary</button><button disabled>Disabled</button></div><p class="small" style="margin-top:12px">One primary action per task. Visible keyboard focus. Labels on all controls. Stopped and warming up are neutral: only a stale feed, an elevated limit or a fault gets a colour.</p></div>`)}${card('Spacing and shape','A shared scale keeps dense screens readable',`<div class="card-body"><div class="space-samples">${[4,8,12,16,24,32].map(n=>`<div><i style="height:${n}px"></i><span>${n}px</span></div>`).join('')}</div><p class="small" style="margin-top:16px">Cards: 10px radius · Controls: 6px · Badges: 4px<br>Card inset: 12–16px · Grid gap: 16px · Row height: 26–32px</p></div>`)}</div><div class="grid">${card('Data and accessibility','Make precision and meaning explicit','<div class="card-body"><ul class="rules"><li>Right-align numbers. Put units in headers. Retain meaningful quantity precision.</li><li>Use + / − for signed money. Missing values are “–”, never zero.</li><li>One figure, one name: what Live calls marked PnL, Research calls marked PnL.</li><li>Label timezone, chart axes, series, and measurement coverage.</li><li>Never label recorded, paused or stopped data as live.</li><li>Stack panels on narrow screens. Scroll wide tables within their card.</li></ul></div>')}${card('Empty state','Absence of data is part of the design','<div class="empty"><div class="empty-icon">≡</div><h3>No fills in this run</h3><p>Executions will appear here once the selected engine records a fill.</p></div>')}</div>`;
}

const views = {monitor,health,parameters,runs:runLibrary,run:runDetail,compare,guide};
// The dot on Health means a component is down, and nothing else: a stopped
// engine has no components to be down, and a logged error is in the log.
function renderNav(page){
 const workspace=pages[page].workspace||state.workspace;
 $('#workspace-switch').innerHTML=workspaces.map(w=>`<button data-workspace="${w.id}" aria-pressed="${w.id===workspace}">${w.label}</button>`).join('');
 const down=componentDown();
 const items=navItems[workspace].map(([id,label])=>`<a href="#${id}" data-page="${id}"${id===page||(page==='run'&&id==='runs')?' aria-current="page"':''}${id==='health'&&down?' aria-label="Health · 1 component down"':''}>${label}${id==='health'&&down?' <span class="nav-dot" aria-hidden="true"></span>':''}</a>`).join('');
 $('#nav').innerHTML=items+`<span class="workspace-note">${workspaces.find(w=>w.id===workspace).note}</span><a href="#guide" data-page="guide" class="guide-link"${page==='guide'?' aria-current="page"':''}>Style guide <span aria-hidden="true">↗</span></a>`;
}
function render() {
 const active=document.activeElement;
 const focusSelector=active?.id?`#${active.id}`:Object.entries(active?.dataset||{}).map(([key,value])=>`[data-${key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())}="${value}"]`)[0];
 let page=location.hash.slice(1)||'monitor'; if(!pages[page])page='monitor';
 if(pages[page].workspace)state.workspace=pages[page].workspace;
 document.title=`Jolteon · ${pages[page].title}`;
 renderNav(page);
 const heading=pages[page].workspace?'':`<div class="page-heading"><div><div class="eyebrow">FOUNDATIONS</div><h1>${pages[page].title}</h1><p>${pages[page].description}</p></div><div class="actions"><span class="badge neutral">Version 2.0 · Cockpit</span></div></div>`;
 $('#main').innerHTML=heading+views[page]();
 if(focusSelector){const replacement=$(focusSelector);if(replacement&&!replacement.disabled)replacement.focus({preventScroll:true});}
}
function go(page){if(location.hash.slice(1)===page)render();else location.hash=page;}
let toastTimer, ackTimer;
function toast(text) {$('#toast').textContent=text;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}
function updatePending(){const count=pending().length;$('#pending-label').textContent=pendingLabel();$('#review').disabled=!count;$('#revert').disabled=!count;}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.workspace){state.workspace=b.dataset.workspace;go(workspaces.find(w=>w.id===state.workspace).home);return;}
 if(b.dataset.openRun){state.run=b.dataset.openRun;go('run');return;}
 if(b.dataset.feed){state.feed=b.dataset.feed;render();toast(state.feed==='Live'?'Updates resumed. This page follows the running engine.':'Updates paused. Values below are a snapshot, not live.');return;}
 if(b.dataset.scope){state.scope=b.dataset.scope==='All symbols'?'All symbols':'Symbol';render();return;}
 if(b.id==='toggle-ids'){state.showIds=!state.showIds;render();return;}
 for(const [attr,key] of [['period','period'],['fill','fills'],['horizon','horizon'],['paramTab','paramTab'],['group','group'],['source','source']])if(b.dataset[attr]){state[key]=b.dataset[attr];render();return;}
 if(b.id==='revert'){for(const scope of scopes)state.values[scope]={...state.saved[scope]};render();toast('Sample changes reverted.');}
 if(b.id==='review'){
  if(!$('#parameter-form').reportValidity())return;
  const rows=pending().map(([scope,k])=>[k.replace(':',' · '),scope,String(state.saved[scope][k]),String(state.values[scope][k])]);
  $('#change-list').innerHTML=table(['Parameter','Scope','Current','Proposed'],rows,[2,3]);$('#review-dialog').showModal();
 }
 if(b.id==='cancel-review')$('#review-dialog').close();
 if(b.id==='apply-changes'){
  // Stored is not acknowledged: the engine reads the store on its next
  // poll, and a stopped engine reads it when it next starts.
  const changed=pending();
  const reachable=changed.filter(([scope])=>scope==='All symbols'?engines.some(e=>e.running):engineOf(scope).running);
  for(const scope of scopes)state.saved[scope]={...state.values[scope]};
  $('#review-dialog').close();render();$('#parameter-form input')?.focus({preventScroll:true});
  toast(reachable.length?'Stored for the engine to read. A field says “awaiting engine” until it has.':'Stored. Nothing is running to read it; it applies when the engine next starts.');
  clearTimeout(ackTimer);
  if(reachable.length)ackTimer=setTimeout(()=>{for(const [scope,k] of reachable)state.acked[scope][k]=state.saved[scope][k];render();toast(`The engine read ${reachable.length} change${reachable.length===1?'':'s'}.`);},4000);
 }
 if(b.id==='guide-action'||b.id==='guide-secondary')toast('Example action · Confirmation belongs near the task.');
 if(b.id==='export'){
  const shown=sampleFills().filter(x=>state.fills==='All'||x.side===state.fills);
  const column=(h)=>`markout_${h.replace('+','').replaceAll(' ','_').toLowerCase()}_usd`;
  const rows=[['time_utc','side','trade','order','price_usd',`quantity_${shortAsset().toLowerCase()}`,'fee_usd',...fillHorizons.map(column)],...shown.map(x=>[x.time,x.side,x.trade,x.order,x.price.toFixed(2),x.qty,x.fee.toFixed(2),...fillHorizons.map(h=>x.markout[h]===null?'':x.markout[h].toFixed(2))])];
  const url=URL.createObjectURL(new Blob([rows.map(r=>r.join(',')).join('\n')],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='jolteon-sample-fills.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Sample fills exported.');
 }
});
document.addEventListener('change',e=>{
 if(e.target.id==='engine'){state.engine=e.target.value;render();}
 if(e.target.id==='run-select'){state.run=e.target.value;render();}
 if(e.target.dataset.compare){state.compare[Number(e.target.dataset.compare)]=e.target.value;render();}
 if(e.target.id==='health-state'){state.health=e.target.value;render();}
 if(e.target.id==='compact'){document.body.classList.toggle('compact',e.target.checked);toast('Table density updated for this preview.');}
});
document.addEventListener('input',e=>{
 const key=e.target.dataset.field;if(!key)return;
 if(e.target.validity.valid)state.values[scopeKey()][key]=Number(e.target.value);
 const holder=document.querySelector(`[data-state-for="${key}"]`);if(holder)holder.innerHTML=fieldState(key);
 updatePending();if(!e.target.validity.valid)$('#review').disabled=true;
});
document.addEventListener('submit',e=>e.preventDefault());
window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);$('#main').focus({preventScroll:true});});
render();
