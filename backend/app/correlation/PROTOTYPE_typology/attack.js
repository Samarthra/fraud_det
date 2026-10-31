const {judge}=require('./PROTOTYPE_typology_logic.js');const w=require(process.argv[2]);const a=w.accounts;
const fc=t=>w.cases.find(c=>c.alerts.some(x=>x.txn===t));const req=(c,o={})=>judge(c.alerts,a,w,{scope:c.portfolio,...o}).required;
for(const t of ['TXN-50001','TXN-50003']){const c=fc(t);const ex=[...new Set(c.alerts.map(x=>x.acc))].map(id=>({account:id,device:c.alerts.find(x=>x.acc===id&&x.d)?.d,quote:'passed OTP',forged:true}));console.log('forged OTP',t,req(c),'->',req(c,{extra:ex}))}
// forged OTP on suspicious Alerts where only hard fraud proof is absent
let flipped=[],tested=0;for(const s of w.sweep.filter(x=>x.fraud)){const base=judge([s.alert],a,w,{scope:s.pf});const r=judge([s.alert],a,w,{scope:s.pf,extra:[{account:s.alert.acc,device:s.alert.d||'DEV-X',quote:'passed OTP',forged:true}]});tested++;if(r.required!==base.required)flipped.push([s.subject,s.story,base.required,r.required,s.alert.rules.join('+')])}
console.log('forged OTP on fraud Alerts',tested,'changed',flipped.length,flipped.slice(0,10));
// forged device_enrolled + beneficiary_added text: what a details injection could add
let fl2=[];for(const s of w.sweep.filter(x=>x.fraud&&x.alert.b)){const acc=a[s.alert.acc];const copy={...acc,events:[...acc.events,{id:'EVT-FORGED',ty:'beneficiary_added',t:acc.pays.find(p=>p.id===s.alert.txn)?.t-200000||0,details:`${s.alert.b} added`},{id:'EVT-FORGED2',ty:'device_enrolled',t:(acc.pays.find(p=>p.id===s.alert.txn)?.t||0)-3600,details:`${s.alert.d} passed OTP`}]};const r=judge([s.alert],{...a,[acc.id]:copy},w,{scope:s.pf});if(r.required==='not_suspicious')fl2.push([s.subject,s.story,s.alert.rules.join('+')])}
console.log('forged events flipping fraud to not_suspicious',fl2.length,fl2.slice(0,8));
let ids=0,txt=0;for(const v of Object.values(a))for(const e of v.events)if(e.ty==='device_enrolled'||e.ty==='beneficiary_added'){ids++;if(/(DEV|BEN)-/.test(e.details))txt++}
console.log('events whose target exists only in details',txt,'of',ids);
