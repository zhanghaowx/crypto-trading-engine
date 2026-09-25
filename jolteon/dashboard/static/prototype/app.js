const $ = (selector) => document.querySelector(selector);
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const themes = [
  { id: 'slate', label: 'Slate', dot: '#ae9417' },
  { id: 'sage', label: 'Sage', dot: '#cb8674' },
  { id: 'morandi', label: 'Morandi', dot: '#bd8a90' },
];
const state = { workspace:'trading', engine:'BTC/USD', period:'1h', liveTab:'Overview', feed:'Live', health:'Normal', paramTab:'Engine', group:'Market making', fills:'All', values:{}, saved:{}, run:'r7e88a', source:'All', compare:['r5c1d4','r7e88a'] };

// Two workspaces, because the engine records two independent facts about
// every run and only one of them changes how the screen behaves: data
// read as it happened keeps moving, data read from a recording never
// does. Execution mode - paper or real - rides along as a badge.
const pages = {
  monitor:{workspace:'trading', title:'Live monitor', description:'One engine, trading right now. Everything here keeps moving.'},
  health:{workspace:'trading', title:'Engine health', description:'Connection and component status across your engines.'},
  parameters:{workspace:'trading', title:'Parameters', description:'Change what the running engine does. Edits reach it within seconds.'},
  runs:{workspace:'research', title:'Runs', description:'Every finished run, whether it read a live feed or a recording.'},
  run:{workspace:'research', title:'Run detail', description:'What one finished run did, and the parameters it used.'},
  compare:{workspace:'research', title:'Compare runs', description:'Two runs over one data window, and what differed between them.'},
  guide:{workspace:null, title:'The Jolteon interface', description:'One visual language. Every page, every component, every state.'},
};
const navItems = { trading:[['health','Health'],['monitor','Live monitor'],['parameters','Parameters']], research:[['runs','Runs'],['compare','Compare']] };
const workspaces = [
  { id:'trading', label:'Trading', home:'monitor', note:'Live engine · refreshes while you watch' },
  { id:'research', label:'Research', home:'runs', note:'Finished runs · fixed results' },
];
const groups = {
  'Market making': [['Quote size', 'Quantity placed on each side of the book.', 0.0005, 'BTC', 0.0001], ['Max inventory', 'Maximum absolute inventory held by the strategy.', 0.01, 'BTC', 0.001], ['Requote tolerance', 'Price movement required before replacing a quote.', 0, 'USD', 0.01], ['Book depth', 'Number of order book levels used by the strategy.', 10, 'levels', 1]],
  'Quote offset': [['Edge', 'Target edge added to the quote price.', 5, 'USD', 0.1], ['Half spread', 'Distance from fair price on either side.', 50, 'USD', 1]],
  'Fair price signals': [['Max adjustment', 'Maximum combined fair price adjustment.', 5, 'USD', 0.1], ['Momentum scale', 'Weight applied to the momentum signal.', 1, '×', 0.1], ['Microprice scale', 'Weight applied to the microprice signal.', 1, '×', 0.1]],
  'Feed & execution': [['Book depth', 'Levels requested from the venue.', 10, 'levels', 1], ['Max retries', 'Attempts before reporting a connection failure.', 3, 'tries', 1], ['Retry interval', 'Wait between connection attempts.', 5, 's', 1]],
  'Runtime': [['Heartbeat interval', 'Time between component status reports.', 10, 's', 1], ['Heartbeat timeout', 'Time without a report before marking a component down.', 30, 's', 1], ['Parameter polling', 'Time between reading parameter updates.', 1, 's', 0.1]]
};
for (const [group, fields] of Object.entries(groups)) for (const [label,,value] of fields) state.values[`${group}:${label}`] = state.saved[`${group}:${label}`] = value;

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
const running = () => runs.find(r=>r.status==='Running');

const badge = (label, type='neutral') => `<span class="badge ${type}"><span class="dot"></span>${label}</span>`;
const money = (n) => n.toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2});
const signed = (n) => `${n<0?'−':'+'}$${money(Math.abs(n))}`;
const signedSpan = (n) => `<span class="${n<0?'negative':'positive'}">${signed(n)}</span>`;
const netPnl = (run) => run.gross - run.fees;
const price = () => state.engine === 'BTC/USD' ? 83947.95 : 3248.62;
const shortAsset = () => state.engine.split('/')[0];
const spark = (color='var(--positive)') => `<svg class="spark" viewBox="0 0 100 35" aria-hidden="true"><path d="M0 30 L8 26 L15 28 L23 17 L31 21 L40 16 L48 20 L57 9 L66 13 L74 6 L81 9 L90 4 L100 2" fill="none" stroke="${color}" stroke-width="2"/></svg>`;
const kpi = (label,value,note,positive=false,mini=false) => `<article class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value ${positive?'positive':''}">${value}</div><div class="kpi-note ${mini?'has-spark':''}">${note}</div>${mini?spark():''}</article>`;
const card = (title,subtitle,body,action='',foot='') => `<section class="card"><div class="card-head"><div><h2>${title}</h2>${subtitle?`<p>${subtitle}</p>`:''}</div>${action}</div>${body}${foot?`<div class="card-foot">${foot}</div>`:''}</section>`;
const segments = (items,current,attr) => `<div class="segmented">${items.map(x=>`<button ${attr}="${x}" aria-pressed="${x===current}">${x}</button>`).join('')}</div>`;
const table = (headers,rows,numeric=[]) => `<div class="table-wrap"><table><thead><tr>${headers.map((x,i)=>`<th scope="col" class="${numeric.includes(i)?'num':''}">${x}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((x,i)=>`<td class="${numeric.includes(i)?'num mono':''}">${x}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const engineSelect = () => `<label>Engine <select id="engine">${['BTC/USD','ETH/USD'].map(x=>`<option ${state.engine===x?'selected':''}>${x}</option>`).join('')}</select></label>`;

// A replay reads a window of the past during a few minutes of the
// present, so it has two clocks and neither one stands for the other.
const dataWindow = (run) => isReplay(run) ? `${run.data[0]}–${run.data[1].split(' ').pop()}` : `${run.ran[0]}–${(run.ran[1]||'now').split(' ').pop()}`;
const ranWindow = (run) => run.ran[1] ? `${run.ran[0]}–${run.ran[1].split(' ').pop()}` : `${run.ran[0]} · still going`;
const clockMinutes = (stamp) => {const [h,m]=stamp.split(' ').pop().split(':').map(Number);return h*60+m;};
const duration = (run) => {if(!run.ran[1])return 'still going';const spent=clockMinutes(run.ran[1])-clockMinutes(run.ran[0]);return spent>=60?`${Math.floor(spent/60)}h${spent%60?` ${spent%60}m`:''}`:`${spent}m`;};
const sourceBadge = (run) => isReplay(run) ? badge('Replay','info') : badge('Live feed','good');
const statusBadge = (run) => badge(run.status, run.status==='Running'?'good':run.status==='Interrupted'?'warn':'neutral');
const captureChip = (run) => isReplay(run) ? `<button class="chip" data-open-run="${run.capture}" title="Open the run that captured this data">↩ capture <span class="mono">${run.capture}</span></button>` : '';

function chart() {
  const paths = { '15m': '0,127 24,134 48,120 72,124 96,99 120,105 144,97 168,112 192,90 216,94 240,79 264,86 288,75 312,81 336,62 360,72 384,56 408,63 432,45 456,54 480,30 504,37 528,28 552,35 576,20 600,24', '1h':'0,146 24,138 48,144 72,130 96,132 120,110 144,117 168,107 192,117 216,94 240,96 264,101 288,87 312,94 336,61 360,70 384,56 408,62 432,44 456,51 480,32 504,39 528,27 552,30 576,15 600,20', '4h':'0,150 24,147 48,154 72,151 96,137 120,139 144,123 168,129 192,121 216,128 240,97 264,107 288,91 312,103 336,84 360,93 384,69 408,80 432,53 456,69 480,48 504,53 528,34 552,40 576,24 600,20' };
  const labels = state.period==='15m'?['14:17','14:22','14:27','14:32']:state.period==='4h'?['10:32','11:52','13:12','14:32']:['13:32','13:52','14:12','14:32'];
  const width=Math.max(300, Math.min(1320, innerWidth-(innerWidth>760?64:36))-44);
  const scale=(width-64)/600;
  const points=paths[state.period].split(' ').map(p=>{const [x,y]=p.split(',');return `${Number(x)*scale},${y}`;}).join(' ');
  return `<svg class="chart" viewBox="0 0 ${width} 205" role="img" aria-label="Illustrative marked PnL increases over the selected ${state.period} window, with intermittent declines. Not live data."><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--positive)" stop-opacity=".12"/><stop offset="100%" stop-color="var(--positive)" stop-opacity="0"/></linearGradient></defs>${[20,65,110,155].map((y,i)=>`<line class="chart-grid" x1="0" x2="${600*scale}" y1="${y}" y2="${y}"/><text x="${600*scale+14}" y="${y+4}">$${money((state.engine==='BTC/USD'?128.42:64.21)*(3-i)/3)}</text>`).join('')}<polygon points="0,170 ${points} ${600*scale},170" fill="url(#area)"/><polyline points="${points}" class="chart-line"/>${labels.map((x,i)=>`<text x="${i*190*scale}" y="199">${x}</text>`).join('')}</svg>`;
}
function orderBook() {
 const side = (buy) => `<div class="book-side"><h3 class="${buy?'positive':'negative'}">${buy?'Bids':'Asks'} <span class="muted">· USD</span></h3><table><thead><tr><th scope="col" class="num">Price</th><th scope="col" class="num">Size (${shortAsset()})</th><th scope="col" class="num">Total</th></tr></thead><tbody>${Array.from({length:7},(_,i)=>`<tr class="depth" style="--depth:${(((i+1)*.0238+i*(i+1)*.0031/2)/.2317*100).toFixed(1)}%;--depth-color:${buy?'var(--positive-soft)':'var(--negative-soft)'}"><td class="num ${buy?'positive':'negative'}">${money(price()+(buy?-1:1)*(2.57+i*1.91))}</td><td class="num">${(0.0238+i*.0031).toFixed(4)}</td><td class="num">${((i+1)*.0238+i*(i+1)*.0031/2).toFixed(4)}</td></tr>`).join('')}</tbody></table></div>`;
 return card('Order book',`${state.engine} · 7 levels per side`,`<div class="book-sides">${side(true)}${side(false)}</div><div class="book-mid"><span class="small muted">Mid price</span><strong class="mono">${money(price())}</strong><span class="small muted">Spread <b class="mono">5.14</b> USD</span></div><div class="book-note"><span>Depth shading shows cumulative size</span><span class="mono">${(5.14/price()*10000).toFixed(2)} bps</span></div>`,badge('Snapshot','neutral'));
}
function risk() { return card('Risk limits','Current usage against configured limits',`<div class="card-body"><div class="risk-row"><div class="risk-label"><span>Inventory</span>${badge('OK','good')}</div><div class="track"><i style="width:32%"></i></div><div class="risk-meta"><span class="mono">0.0032 / 0.0100 ${shortAsset()}</span><span>32% used</span></div></div></div>`,`<a class="text-button" href="#parameters">View limits ↗</a>`); }
function signals() { return card('Fair price signals','Contribution to adjusted fair price',`<div class="card-body">${[['Momentum','+$1.24',62],['Order flow imbalance','+$0.82',41],['Inventory adjustment','−$0.46',23]].map(([name,value,w])=>`<div class="signal-row"><span>${name}</span><span class="signal-value"><span class="signal-meter"><i style="width:${w}%"></i></span><span class="mono ${value.startsWith('−')?'negative':'positive'}">${value}</span></span></div>`).join('')}</div>`, '', `<span>Combined adjustment</span><strong class="mono positive">+$1.60</strong>`); }
function fills() {
 const rows=Array.from({length:8},(_,i)=>({time:`14:${31-Math.floor(i/2)}:${String(52-i*5).padStart(2,'0')}`,side:i%3===0?'Sell':'Buy',price:money(price()+(i%3===0?3:-3)+i*.31),qty:'0.0005',fee:'$0.08',edge:i%4===0?'−$0.02':'+$0.04'})).filter(x=>state.fills==='All'||x.side===state.fills);
 return card('Recent fills','Illustrative executions from this session',table(['Time (UTC)','Side','Price (USD)',`Quantity (${shortAsset()})`,'Fee (USD)','Markout +1s (USD)'],rows.map(x=>[x.time,badge(x.side,x.side==='Buy'?'good':'bad'),x.price,x.qty,x.fee,`<span class="${x.edge.startsWith('−')?'negative':'positive'}">${x.edge}</span>`]),[2,3,4,5]),segments(['All','Buy','Sell'],state.fills,'data-fill'),`<span>${rows.length} sample fills · Newest first</span><button class="text-button" id="export">↓ Export sample CSV</button>`);
}
function quality() {return card('Execution quality','Average markout per fill; missing measurements remain an en dash.',table(['Side','Fills','+100ms (USD)','+1s (USD)','+5s (USD)','+30s (USD)'],[['Buy','126','+$0.02','+$0.04','+$0.03','−$0.01'],['Sell','122','+$0.03','+$0.04','+$0.02','–']],[1,2,3,4,5]),'', '<span>Markout is measured against recorded fair prices at each horizon.</span>');}

// Only a page reading a live feed carries this. It is the one control on
// the prototype that stops time, so what it says has to stay true when
// it is off.
function liveContext() {
 const live = state.feed==='Live';
 const run = running();
 return `<section class="context" aria-label="Session context">${engineSelect()}<span class="separator"></span><span class="small">Kraken <span class="muted">/</span> Market making</span>${badge('Paper','info')}${badge('Live feed','good')}<span class="end live-state">${live?`<span class="live-dot" aria-hidden="true"></span><span class="small">Updated 3s ago</span>`:`<span class="live-dot paused" aria-hidden="true"></span><span class="small muted">Paused · 14:32:08 UTC</span>`}${segments(['Live','Paused'],state.feed,'data-feed')}</span><span class="small muted mono run-id">Run ${run.id}</span></section>`;
}
function monitor() {
 const pnl=state.engine==='BTC/USD'?'128.42':'64.21';
 return liveContext()+`<div class="kpis">${kpi('Marked PnL',`+$${pnl}`,'Cash flow + inventory at mid',true,true)}${kpi('Traded notional',state.engine==='BTC/USD'?'$42,186.50':'$18,249.80','This session · USD')}${kpi('Fills','248','126 buy / 122 sell')}${kpi('Trading fees','$16.87','Total fees · This session')}</div><div class="tabs" aria-label="Live view">${['Overview','Fills','Execution quality'].map(x=>`<button data-live-tab="${x}" aria-pressed="${state.liveTab===x}">${x}</button>`).join('')}</div>`+(state.liveTab==='Fills'?fills():state.liveTab==='Execution quality'?quality():`<div class="grid">${orderBook()}<div class="stack">${risk()}${signals()}</div></div><div class="wide">${card('Session performance','Marked PnL · USD',`<div class="card-body">${chart()}</div>`,segments(['15m','1h','4h'],state.period,'data-period'),'<span><span class="legend-line"></span> Marked PnL</span><span>Illustrative trend · Time (UTC)</span>')}</div>${fills()}`);
}
function health() {
 const warning=state.health==='Feed delayed';
 return `<section class="context"><span class="small"><strong>All engines</strong> <span class="muted">/ 1 configured · Kraken · BTC/USD</span></span><span class="end small muted">Sample snapshot · 14:32:08 UTC</span><label>Preview state <select id="health-state"><option ${!warning?'selected':''}>Normal</option><option ${warning?'selected':''}>Feed delayed</option></select></label></section>${warning?'<div class="banner"><strong>Public feed needs attention.</strong> Last heartbeat was 42 seconds ago; the configured timeout is 30 seconds. Prices below may be stale.</div>':''}<div class="kpis">${kpi('Components reporting',warning?'3 / 4':'4 / 4','Strategy, execution, feed, parameters')}${kpi('Components down',warning?'1':'0',warning?'Public feed timed out':'All heartbeats within timeout')}${kpi('Recorded errors',warning?'1':'0','This sample session')}${kpi('Heartbeat timeout','30 s','Configured threshold')}</div><div class="health-grid">${['Market making','Paper execution','Public feed','Parameters'].map((name,i)=>`<article class="card health-tile"><div class="eyebrow">${['STRATEGY','EXECUTION','MARKET DATA','CONFIGURATION'][i]}</div><h3>${name}</h3>${badge(warning&&i===2?'Down':'Normal',warning&&i===2?'bad':'good')}<p>Last seen ${warning&&i===2?'42':'2'} seconds ago</p><svg viewBox="0 0 230 30" role="img" aria-label="Illustrative heartbeat history">${Array.from({length:32},(_,n)=>`<rect x="${n*7.2}" y="5" width="4" height="22" rx="1" fill="${warning&&i===2&&n>24?'var(--negative)':'var(--heartbeat-ok)'}"/>`).join('')}</svg><p>Sample heartbeat history</p></article>`).join('')}</div>${card('Error log','Recorded errors across all engines',warning?table(['Time (UTC)','Component','Level','Message'],[['14:31:26','Public feed',badge('Error','bad'),'Heartbeat timeout exceeded · 42 s']]):'<div class="empty"><div class="empty-icon">✓</div><h3>No errors recorded</h3><p>Errors will appear here with their engine, timestamp, and message.</p></div>',badge(warning?'1 error':'0 errors',warning?'bad':'neutral'))}`;
}
function pending(){return Object.keys(state.values).filter(k=>state.values[k]!==state.saved[k]);}
function settingsFields() {return groups[state.group].map(([label,help,,unit,step])=>{const key=`${state.group}:${label}`;return `<div class="setting"><div><label for="field-${label.replaceAll(' ','-')}">${label}</label><p>${help}</p></div><div class="setting-control"><input id="field-${label.replaceAll(' ','-')}" aria-label="${label}" data-field="${key}" type="number" min="0" step="${step}" value="${state.values[key]}" required><span class="unit">${unit}</span></div></div>`}).join('');}
function parameters() {
 return `<div class="tabs" aria-label="Parameter type">${['Engine','Dashboard'].map(x=>`<button data-param-tab="${x}" aria-pressed="${state.paramTab===x}">${x}</button>`).join('')}</div>`+(state.paramTab==='Dashboard'?card('Viewer settings','Preferences for this preview only.',`<div class="setting"><div><label for="compact">Compact table rows</label><p>Reduce vertical spacing in data tables.</p></div><input type="checkbox" id="compact" ${document.body.classList.contains('compact')?'checked':''}></div><div class="setting"><div><h3>Time display</h3><p>One explicit timezone across this prototype.</p></div><span class="badge neutral">UTC</span></div>`):`<section class="context"><span class="small muted">Applies to</span><strong class="small">Kraken · BTC/USD</strong>${badge('Symbol override','info')}${badge('Reaches the running engine','warn')}<span class="end small muted">Polled every 1s · A finished run keeps the values it ran with</span></section><div class="settings-layout"><aside class="settings-nav" aria-label="Parameter groups">${Object.keys(groups).map(x=>`<button data-group="${x}" aria-pressed="${x===state.group}">${x}</button>`).join('')}<p>Selected groups from the existing parameter catalog.</p></aside><div>${card(state.group,'Defaults and symbol overrides share the same field layout.',`<form id="parameter-form">${settingsFields()}</form><details><summary>How changes take effect</summary><p>In the production dashboard, committed values are stored separately from engine recordings. Engine reports indicate whether they have been read. This prototype only demonstrates the review flow.</p></details>`)}<div class="save-bar"><div><p id="pending-label">${pending().length?`${pending().length} unsaved change${pending().length===1?'':'s'}`:'No unsaved changes'}</p><small>Review the exact values before applying.</small></div><div class="actions"><button id="revert" ${!pending().length?'disabled':''}>Revert</button><button id="review" class="primary" ${!pending().length?'disabled':''}>Review changes</button></div></div></div></div>`);
}

const horizons=[['At fill',1,1],['+100ms',.9535,1],['+1s',.9185,.998],['+5s',.8665,.992],['+30s',.7905,.974]];
function economics(run){return horizons.map(([label,factor,share])=>{const gross=run.gross*factor,fees=run.fees*share;return {label,share,gross,fees,net:gross-fees,bps:(gross-fees)/run.notional*10000,adverse:factor===1?null:gross-run.gross};});}
function economicsCard(run){
 return card('Execution economics','Markout at each horizon, net of fees on measured fills.',table(['Horizon','Measured notional','Gross (USD)','Fees (USD)','Net (USD)','Net (bps)','Adverse selection (USD)'],economics(run).map(r=>[r.label,`${(r.share*100).toFixed(1)}%`,signed(r.gross),`$${money(r.fees)}`,signedSpan(r.net),r.bps.toFixed(2),r.adverse===null?'–':signedSpan(r.adverse)]),[1,2,3,4,5,6]),badge('Final result'),'<span>Measured share is based on availability of recorded fair prices.</span>');
}
// The same card on both sides of the workspace split would be wrong:
// here the values are what the run was handed, and nothing on screen may
// suggest otherwise.
function parameterSetCard(run){
 const rows=Object.entries(run.params).map(([key,value])=>{const live=state.saved[key];return [key.replace(':',' · '),String(value),live===value?'<span class="muted">same</span>':`<span class="mono">${live}</span>`];});
 return card('Parameters this run used',`Recorded with the run. Read-only.`,table(['Parameter','This run','Current live value'],rows,[1,2]),badge('Frozen','neutral'),`<span>Editing parameters belongs to the running engine, under Trading.</span><a class="text-button" href="#compare">Compare with another run ↗</a>`);
}
function runDetail(){
 const run=byId(state.run);
 const options=finished().map(r=>`<option value="${r.id}" ${state.run===r.id?'selected':''}>${r.id} · ${isReplay(r)?'Replay':'Live feed'} · ${dataWindow(r)}</option>`).join('');
 return `<section class="context" aria-label="Run scope"><label>Run <select id="run-select">${options}</select></label>${sourceBadge(run)}${badge(run.exec,'info')}${statusBadge(run)}${captureChip(run)}<span class="end clocks"><span><b class="small">Data</b> <span class="mono small">${dataWindow(run)} UTC</span></span><span class="muted small">Ran ${ranWindow(run)} UTC · ${duration(run)}${isReplay(run)?` · ${run.trades.toLocaleString('en-US')} market trades`:''}</span></span></section><div class="kpis">${kpi('Marked PnL',signed(netPnl(run)),'Inventory valued at latest recorded mid',netPnl(run)>0,true)}${kpi('Traded notional',`$${money(run.notional)}`,'Whole run · USD')}${kpi('Trading fees',`$${money(run.fees)}`,'Whole run')}${kpi('Fills',String(run.fills),'Completed executions')}</div><div class="wide">${economicsCard(run)}</div><div class="grid">${parameterSetCard(run)}${card('Read the numbers','Different measures answer different questions.','<div class="card-body"><ul class="rules"><li><strong>Marked PnL</strong> combines cash flow with the value of remaining inventory.</li><li><strong>Net markout</strong> subtracts measured-fill fees from gross markout at each horizon.</li><li><strong>Measured share</strong> makes incomplete coverage explicit. Missing data is shown as “–”.</li>'+(isReplay(run)?`<li><strong>Two clocks.</strong> This run read ${dataWindow(run)} of recorded market data, and took ${duration(run)} of wall clock to do it.</li><li><strong>Adverse selection</strong> is what a fill gave back as the market moved on, so it grows with the horizon.</li>`:`<li><strong>One clock.</strong> A live session reads the market as it happens, so its run window is its data window: ${duration(run)} in all.</li><li><strong>Adverse selection</strong> is what a fill gave back as the market moved on, so it grows with the horizon.</li>`)+'</ul></div>')}</div>`;
}
function runLibrary(){
 const shown=finished().filter(r=>state.source==='All'||(state.source==='Replay')===isReplay(r));
 const open=running();
 const rows=shown.map(r=>[`<button class="link-id mono" data-open-run="${r.id}">${r.id}</button>`,`${sourceBadge(r)} ${badge(r.exec,'info')}`,`<span class="mono">${dataWindow(r)}</span>${isReplay(r)?`<span class="muted small"> · from ${r.capture}</span>`:'<span class="muted small"> · as it ran</span>'}`,`<span class="mono muted">${ranWindow(r)}</span>`,String(r.fills),signedSpan(netPnl(r)),statusBadge(r)]);
 return `<section class="context" aria-label="Library scope">${engineSelect()}<span class="separator"></span><span class="small">Kraken <span class="muted">/</span> Market making</span>${segments(['All','Live feed','Replay'],state.source,'data-source')}<span class="end small muted">${shown.length} finished run${shown.length===1?'':'s'} · All times UTC</span></section><div class="kpis">${kpi('Finished runs',String(finished().length),'Live sessions and replays')}${kpi('Replays',String(runs.filter(isReplay).length),'Over 2 captured windows')}${kpi('Best net PnL',signed(Math.max(...finished().map(netPnl))),'Across every finished run',true)}${kpi('Live sessions',String(runs.filter(r=>!isReplay(r)).length),'1 still running')}</div>${card('Finished runs','Select a run to open it, or compare two of them.',table(['Run','Mode','Data window','Ran','Fills','Net PnL','Status'],rows,[4,5]),`<a class="text-button" href="#compare">Compare two runs ↗</a>`,`<span>${open?`Run <b class="mono">${open.id}</b> is still going and is not measured here.`:'Every recorded run has finished.'}</span>${open?'<a class="text-button" href="#monitor">Watch it live ↗</a>':''}`)}`;
}
function compare(){
 const [a,b]=state.compare.map(byId);
 const sameWindow=dataWindow(a)===dataWindow(b);
 const select=(side,current)=>`<label>Run ${side} <select data-compare="${side==='A'?0:1}">${finished().map(r=>`<option value="${r.id}" ${current===r.id?'selected':''}>${r.id} · ${isReplay(r)?'Replay':'Live feed'} · ${dataWindow(r)}</option>`).join('')}</select></label>`;
 const delta=(x,y)=>y-x;
 // Only PnL has a direction that means better or worse. Fewer fills is
 // not a loss and a smaller fee bill is not a shortfall, so those deltas
 // carry their sign without carrying a colour.
 const deltaKpi=(label,x,y,format,note,semantic=false)=>{const d=delta(x,y);const sign=d<0?'−':d>0?'+':'';const tone=semantic?(d<0?'negative':'positive'):'mono';return kpi(label,format(y),`${note} · <span class="${tone}">${sign}${format(Math.abs(d)).replace(/^[+−]/,'')}</span> vs A`,false);};
 const rowsA=economics(a),rowsB=economics(b);
 const diffs=Object.keys(a.params).filter(k=>a.params[k]!==b.params[k]);
 return `<section class="context" aria-label="Comparison scope">${select('A',a.id)}${select('B',b.id)}<span class="end small muted">${sameWindow?`Both read ${dataWindow(a)} UTC`:'Different data windows'}</span></section>${sameWindow?'':`<div class="banner"><strong>These runs read different data.</strong> Run A covers ${dataWindow(a)} and run B covers ${dataWindow(b)}, so the difference below is mostly the market, not the parameters. Replay both over one window to compare them.</div>`}<div class="kpis">${deltaKpi('Net PnL',netPnl(a),netPnl(b),v=>signed(v),'Run B',true)}${deltaKpi('Fills',a.fills,b.fills,v=>String(Math.round(v)),'Run B')}${deltaKpi('Traded notional',a.notional,b.notional,v=>`$${money(v)}`,'Run B')}${deltaKpi('Trading fees',a.fees,b.fees,v=>`$${money(v)}`,'Run B')}</div><div class="wide">${card('What differed in the parameters',diffs.length?'Only the values that are not the same in both runs.':'Both runs were handed the same parameters.',diffs.length?table(['Parameter',`A · ${a.id}`,`B · ${b.id}`,'Change'],diffs.map(k=>[k.replace(':',' · '),String(a.params[k]),String(b.params[k]),`<span class="${b.params[k]>a.params[k]?'positive':'negative'}">${b.params[k]>a.params[k]?'↑':'↓'} ${(b.params[k]-a.params[k]).toFixed(4).replace(/\.?0+$/,'')}</span>`]),[1,2,3]):'<div class="empty"><div class="empty-icon">=</div><h3>Identical parameter sets</h3><p>Any difference in the results below came from the data or from the run itself.</p></div>',badge(`${diffs.length} of ${Object.keys(a.params).length} differ`,diffs.length?'info':'neutral'),'<span>A replay is worth running when exactly one thing changes between two of them.</span>')}</div><div class="wide">${card('Net markout by horizon','Run B measured against run A at each horizon.',table(['Horizon',`A · net (USD)`,`B · net (USD)`,'Δ (USD)','Δ (bps)'],rowsA.map((r,i)=>[r.label,signed(r.net),signed(rowsB[i].net),signedSpan(rowsB[i].net-r.net),(rowsB[i].bps-r.bps).toFixed(2)]),[1,2,3,4]),'',`<span>${sameWindow?'Same data, so the difference is the parameters and the run.':'Different data windows — read this comparison with care.'}</span>`)}</div>`;
}
function guide() {
 return `<section class="guide-intro"><div><div class="eyebrow">DESIGN SYSTEM / 01</div><h2>Quiet surfaces.<br>Clear decisions.</h2><p>A focused workspace for monitoring an engine, understanding a session, and changing a parameter with confidence.</p></div><div class="guide-principles"><div><strong>01 &nbsp; Context before content</strong><p>Always show the engine, run, mode, and freshness.</p></div><div><strong>02 &nbsp; Live and finished look different</strong><p>Only a live feed gets a pulse and a refresh control.</p></div><div><strong>03 &nbsp; Consistency builds trust</strong><p>Repeat the same spacing, number formats, and component anatomy.</p></div></div></section><div class="wide">${card('Two workspaces','Market data mode decides which one a screen belongs to.',`<div class="card-body"><div class="workspace-compare"><div><div class="eyebrow">TRADING</div><p class="small">One engine reading a live feed, right now.</p><ul class="rules"><li>Refreshes, and says when it last did.</li><li>Parameters are editable and reach the engine.</li><li>Component health matters.</li><li>Paper or real is a badge, not a separate place.</li></ul></div><div><div class="eyebrow">RESEARCH</div><p class="small">Runs that have finished — live sessions and replays alike.</p><ul class="rules"><li>Never refreshes; the numbers are final.</li><li>Parameters are a frozen input, shown read-only.</li><li>A replay states both its clocks and its capture.</li><li>Comparing two runs is the point of the workspace.</li></ul></div></div></div>`)}</div><div class="grid">${card('Color tokens','A neutral foundation with purposeful accents.',`<div class="card-body swatches">${[['Canvas','--canvas'],['Surface','--surface'],['Text','--ink'],['Secondary','--muted'],['Brand','--accent'],['Positive','--positive'],['Negative','--negative'],['Warning','--warning']].map(([name,token])=>`<div class="swatch"><div class="swatch-color" style="background:var(${token})"></div><strong>${name}</strong><span class="mono">${cssVar(token)}</span></div>`).join('')}</div>`)}${card('Typography','One sans-serif family. Tabular figures for data.',`<div class="card-body"><div class="type-row"><span style="font-size:29px;font-weight:600;letter-spacing:-.9px">Page heading</span><small>29 / 600</small></div><div class="type-row"><h2>Card heading</h2><small>15 / 600</small></div><div class="type-row"><span>Body and controls</span><small>14 / 400–500</small></div><div class="type-row"><span class="muted small">Context and supporting text</span><small>12 / 400</small></div><div class="type-row"><span class="mono positive" style="font-size:26px">+$128.42</span><small>28 / tabular</small></div></div>`)}</div><div class="grid">${card('Status and interaction','Status must remain understandable without color.',`<div class="card-body"><div class="status-samples">${badge('Running','good')}${badge('Live feed','good')}${badge('Replay','info')}${badge('Elevated','warn')}${badge('Down','bad')}${badge('Paper','info')}${badge('Frozen')}${badge('Completed')}</div><div class="actions"><button class="primary" id="guide-action">Primary action</button><button id="guide-secondary">Secondary</button><button disabled>Disabled</button></div><p class="small" style="margin-top:16px">One primary action per task. Visible keyboard focus. Labels on all controls.</p></div>`)}${card('Spacing and shape','A shared scale keeps dense screens readable.',`<div class="card-body"><div class="space-samples">${[4,8,12,16,24,32].map(n=>`<div><i style="height:${n}px"></i><span>${n}px</span></div>`).join('')}</div><p class="small" style="margin-top:22px">Cards: 10px radius · Controls: 6px · Card inset: 20–24px<br>Section gap: 20–24px · Desktop page inset: 32px</p></div>`)}</div><div class="grid">${card('Page anatomy','Use this sequence on every page.','<div class="card-body"><ol class="rules"><li>Page title, one-line purpose, optional page action.</li><li>Scope bar: engine, mode, run, and either freshness or data window.</li><li>Up to four summary metrics, where meaningful.</li><li>Main task in an aligned grid; details below.</li><li>Quiet empty states and explicit error recovery.</li></ol></div>')}${card('Data and accessibility','Make precision and meaning explicit.','<div class="card-body"><ul class="rules"><li>Right-align numbers. Put units in headers. Retain meaningful quantity precision.</li><li>Use + / − for signed money. Missing values are “–”, never zero.</li><li>Label timezone, chart axes, series, and measurement coverage.</li><li>Never label recorded or paused data as live.</li><li>Stack cards on narrow screens. Scroll wide tables within their card.</li></ul></div>')}</div><div class="wide">${card('Empty state','Absence of data is part of the design.','<div class="empty"><div class="empty-icon">≡</div><h3>No fills in this run</h3><p>Executions will appear here once the selected engine records a fill.</p></div>')}</div>`;
}

const views = {monitor,health,parameters,runs:runLibrary,run:runDetail,compare,guide};
function renderNav(page){
 const workspace=pages[page].workspace||state.workspace;
 $('#workspace-switch').innerHTML=workspaces.map(w=>`<button data-workspace="${w.id}" aria-pressed="${w.id===workspace}">${w.label}</button>`).join('');
 const items=navItems[workspace].map(([id,label])=>`<a href="#${id}" data-page="${id}"${id===page||(page==='run'&&id==='runs')?' aria-current="page"':''}>${label}${id==='health'?' <span class="nav-dot"></span>':''}</a>`).join('');
 $('#nav').innerHTML=items+`<span class="workspace-note">${workspaces.find(w=>w.id===workspace).note}</span><a href="#guide" data-page="guide" class="guide-link"${page==='guide'?' aria-current="page"':''}>Style guide <span aria-hidden="true">↗</span></a>`;
 const dot=$('.nav-dot');
 if(dot){dot.style.background=state.health==='Feed delayed'?'var(--negative)':'var(--positive)';$('[data-page=health]').setAttribute('aria-label',state.health==='Feed delayed'?'Health · 1 component down':'Health');}
}
function render() {
 const active=document.activeElement;
 const focusSelector=active?.id?`#${active.id}`:Object.entries(active?.dataset||{}).map(([key,value])=>`[data-${key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())}="${value}"]`)[0];
 let page=location.hash.slice(1)||'monitor'; if(!pages[page])page='monitor';
 if(pages[page].workspace)state.workspace=pages[page].workspace;
 document.title=`Jolteon · ${pages[page].title}`;
 renderNav(page);
 const eyebrow=pages[page].workspace?`${pages[page].workspace.toUpperCase()} / ${pages[page].title.toUpperCase()}`:'FOUNDATIONS';
 $('#main').innerHTML=`<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${pages[page].title}</h1><p>${pages[page].description}</p></div><div class="actions">${page==='monitor'?badge('Sample session','neutral'):page==='run'?'<a class="text-button" href="#runs">← All runs</a>':page==='guide'?'<span class="badge neutral">Version 1.0 · Proposed</span>':''}</div></div>`+views[page]();
 if(focusSelector){const replacement=$(focusSelector);if(replacement&&!replacement.disabled)replacement.focus({preventScroll:true});}
}
function go(page){if(location.hash.slice(1)===page)render();else location.hash=page;}
function applyTheme(id, {announce=true}={}) {
 document.documentElement.dataset.theme = id;
 document.querySelectorAll('#theme-switch button').forEach(b=>b.setAttribute('aria-pressed', String(b.dataset.themeChoice===id)));
 try { localStorage.setItem('jolteon-proto-theme', id); } catch {}
 render();
 if (announce) toast(`Palette set to ${themes.find(t=>t.id===id).label}. This choice stays in this browser only.`);
}
function initTheme() {
 $('#theme-switch').innerHTML = themes.map(t=>`<button data-theme-choice="${t.id}" aria-pressed="false" aria-label="${t.label} palette"><span class="theme-dot" style="--dot:${t.dot}"></span><span>${t.label}</span></button>`).join('');
 let saved = 'slate';
 try { saved = localStorage.getItem('jolteon-proto-theme') || 'slate'; } catch {}
 if (!themes.some(t=>t.id===saved)) saved = 'slate';
 applyTheme(saved, {announce:false});
}
let toastTimer;
function toast(text) {$('#toast').textContent=text;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}
function updatePending(){const count=pending().length;$('#pending-label').textContent=count?`${count} unsaved change${count===1?'':'s'}`:'No unsaved changes';$('#review').disabled=!count;$('#revert').disabled=!count;}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.themeChoice){applyTheme(b.dataset.themeChoice);return;}
 if(b.dataset.workspace){state.workspace=b.dataset.workspace;go(workspaces.find(w=>w.id===state.workspace).home);return;}
 if(b.dataset.openRun){state.run=b.dataset.openRun;go('run');return;}
 if(b.dataset.feed){state.feed=b.dataset.feed;render();toast(state.feed==='Live'?'Updates resumed. This page follows the running engine.':'Updates paused. Values below are a snapshot, not live.');return;}
 for(const [attr,key] of [['period','period'],['liveTab','liveTab'],['fill','fills'],['paramTab','paramTab'],['group','group'],['source','source']])if(b.dataset[attr]){state[key]=b.dataset[attr];render();return;}
 if(b.id==='revert'){state.values={...state.saved};render();toast('Sample changes reverted.');}
 if(b.id==='review'){
  if(!$('#parameter-form').reportValidity())return;
  const rows=pending().map(k=>[k.replace(':',' · '),'BTC/USD',String(state.saved[k]),String(state.values[k])]);
  $('#change-list').innerHTML=table(['Parameter','Scope','Current','Proposed'],rows,[2,3]);$('#review-dialog').showModal();
 }
 if(b.id==='cancel-review')$('#review-dialog').close();
 if(b.id==='apply-changes'){state.saved={...state.values};$('#review-dialog').close();render();$('#parameter-form input')?.focus({preventScroll:true});toast('Applied to demo. No engine settings were changed.');}
 if(b.id==='guide-action'||b.id==='guide-secondary')toast('Example action · Confirmation belongs near the task.');
 if(b.id==='export'){
  const rows=[['time_utc','side','price_usd','quantity','fee_usd','markout_1s_usd'],...Array.from({length:8},(_,i)=>[`14:${31-Math.floor(i/2)}:${String(52-i*5).padStart(2,'0')}`,i%3===0?'Sell':'Buy',(price()+(i%3===0?3:-3)+i*.31).toFixed(2),'0.0005','0.08',i%4===0?'-0.02':'0.04']).filter(x=>state.fills==='All'||x[1]===state.fills)];
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
document.addEventListener('input',e=>{if(e.target.dataset.field){if(e.target.validity.valid)state.values[e.target.dataset.field]=Number(e.target.value);updatePending();if(!e.target.validity.valid)$('#review').disabled=true;}});
document.addEventListener('submit',e=>e.preventDefault());
window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);$('#main').focus({preventScroll:true});});
initTheme();
