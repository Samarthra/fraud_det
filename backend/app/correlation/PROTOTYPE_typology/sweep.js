const {judge}=require('./PROTOTYPE_typology_logic.js');const w=require(process.argv[2]);const a=w.accounts;
const rows={};for(const s of w.sweep){const r=judge([s.alert],a,w,{scope:s.pf});const k=`${s.fraud?'FRAUD ':'benign'} ${s.story}`;rows[k]=rows[k]||{n:0,suspicious:0,not_suspicious:0,none:0};rows[k].n++;rows[k][r.required]++;if((!s.fraud&&r.required==='suspicious')||(s.fraud&&r.required==='not_suspicious'))console.log('WRONG',s.subject,s.story,r.required,r.proved.map(p=>p.id),s.alert.rules)}
console.table(rows);
for(const c of w.cases){const r=judge(c.alerts,a,w,{scope:c.portfolio});if(/TXN-5000/.test(c.alerts.map(x=>x.txn).join()))console.log(c.id,c.cat,r.required,[...new Set(r.proved.map(p=>p.id))],r.uncovered.slice(0,6))}
console.log(Object.entries(w.cases.reduce((m,c)=>{const q=judge(c.alerts,a,w,{scope:c.portfolio}).required;m[q]=(m[q]||0)+1;return m},{})))
