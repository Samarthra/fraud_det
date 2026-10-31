// PROTOTYPE, throwaway. Pure rules over plain records: no DOM. Lift the definitions, not this file.
const H=3600, D=86400;
const RULES={takeover_h:2,fails:3,fail_min:60,mule:5,payout_h:72,share:.5,ring_d:30,quiet_d:1,payee_h:24};
const LEGIT_FREE=new Set(['amount_spike','off_hours']);
const FRAUD=new Set(['account_takeover','mule_payment','loan_proceeds_diversion','staged_claim_ring']);
const NAMES={account_takeover:'Account takeover',mule_payment:'Mule payment',loan_proceeds_diversion:'Loan proceeds diversion',staged_claim_ring:'Staged claim ring',verified_device_change:'Verified device change',established_payee:'Established payee'};
const live=(rows,off)=>rows.filter(r=>!off.has(r.id));
const idIn=(text,prefix)=>((text||'').match(new RegExp(prefix+'-[A-Za-z0-9]+'))||[])[0];

function compromise(acc,before,off){
  const from=before-RULES.takeover_h*H, out=[];
  for(const e of live(acc.events,off)) if((e.ty==='sim_swap'||e.ty==='password_reset')&&e.t>=from&&e.t<=before) out.push({ref:e.id,text:e.ty.replace('_',' ')});
  const logins=live(acc.logins,off).slice().sort((a,b)=>a.t-b.t); let fails=[];
  for(const l of logins){ if(l.o==='failure'){fails.push(l);continue}
    const near=fails.filter(f=>l.t-f.t<=RULES.fail_min*60);
    if(near.length>=RULES.fails&&l.t>=from&&l.t<=before) out.push({ref:l.id,text:`${near.length} failed logins then a success`,refs:[...near.map(f=>f.id),l.id]});
    fails=[] }
  return out }

function proveAccount(acc,world,extra,off,scope,span){
  const inSpan=t=>t>=span[0]&&t<=span[1];
  const proved=[],near=[]; const pays=live(acc.pays,off).filter(p=>inSpan(p.t));
  const texts=[...acc.events.filter(e=>!off.has(e.id)&&e.ty==='device_enrolled'&&/passed OTP/.test(e.details)).map(e=>({device:idIn(e.details,'DEV'),quote:'passed OTP',ref:e.id})),...extra.filter(x=>x.account===acc.id)];
  for(const p of pays){
    if(p.first){ const c=compromise(acc,p.t,off);
      if(p.newd&&c.length) proved.push({id:'account_takeover',subject:p.b,device:p.d,proof:[...c.map(x=>[x.text,x.ref]),[`device ${p.d} is new to this account`,p.id],[`${p.id} pays first-time beneficiary ${p.b}, ₹${p.amt}`,p.id]]});
      else if(p.newd) near.push({id:'account_takeover',missing:'a compromise signal within 2 hours'});
      else if(c.length) near.push({id:'account_takeover',missing:'a device new to this account'});
      if(p.payers7>=RULES.mule) proved.push({id:'mule_payment',subject:p.b,proof:[[`${p.id} is the first payment to ${p.b}`,p.id],[`${p.payers7} accounts paid ${p.b} within 7 days (other Portfolios as a bare count)`,p.id]]});
      for(const l of live(acc.payouts,off)){ const gap=p.t-l.t;
        if(gap>=0&&gap<=RULES.payout_h*H&&p.amt>=RULES.share*l.amt) proved.push({id:'loan_proceeds_diversion',subject:l.id,proof:[[`${l.id} paid out ₹${l.amt} into ${acc.id}`,l.id],[`${p.id} sent ₹${p.amt} to first-time beneficiary ${p.b} ${Math.round(gap/H)} hours later`,p.id]]}) }
      const added=acc.events.filter(e=>!off.has(e.id)&&e.ty==='beneficiary_added'&&idIn(e.details,'BEN')===p.b)[0];
      if(added&&p.t-added.t>=RULES.payee_h*H&&p.payersAll===1) proved.push({id:'established_payee',subject:p.b,textDependent:true,proof:[[`${p.b} was added ${Math.round((p.t-added.t)/H)} hours before its first payment (the ID is read from details)`,added.id],[`only this account has ever paid ${p.b}`,p.id]]});
    } }
  for(const x of texts){ const e=acc.events.find(v=>v.ty==='device_enrolled'&&idIn(v.details,'DEV')===x.device&&!off.has(v.id))||acc.events.find(v=>v.ty==='device_enrolled'&&!off.has(v.id));
    if(!e||!inSpan(e.t)) continue; const quiet=e.t-RULES.quiet_d*D;
    const blockers=[...live(acc.logins,off).filter(l=>l.o==='failure'&&l.t>=quiet&&l.t<=e.t+H).map(l=>l.id),...live(acc.events,off).filter(v=>(v.ty==='sim_swap'||v.ty==='password_reset')&&v.t>=quiet&&v.t<=e.t+H).map(v=>v.id)];
    if(blockers.length) near.push({id:'verified_device_change',missing:`blocked by ${blockers.slice(0,4).join(', ')}`});
    else proved.push({id:'verified_device_change',subject:x.device,device:x.device,proof:[[`${x.device} enrolled`,e.id],[`text fact otp_verified quotes "${x.quote}"${x.forged?' (FORGED BY THIS TEST)':''}`,x.ref||e.id],['no failed login, SIM swap or password reset in the 24 hours before',e.id]]}) }
  for(const c of world.claims.filter(c=>c.c===acc.c&&!off.has(c.id)&&inSpan(c.t))){
    const mates=world.claims.filter(o=>o.id!==c.id&&!off.has(o.id)&&o.c!==c.c&&o.hh!==c.hh&&Math.abs(o.t-c.t)<=RULES.ring_d*D&&((o.d&&o.d===c.d)||(o.ip&&o.ip===c.ip)||(o.ph&&o.ph===c.ph)));
    if(mates.length){ const own=mates.filter(m=>m.pf.includes(scope)); proved.push({id:'staged_claim_ring',subject:c.id,proof:[[`${c.id} shares a device, IP or phone with ${mates.length} other claim(s) within 30 days`,c.id],...own.map(m=>[`linked claim ${m.id}`,m.id]),...(mates.length>own.length?[[`${mates.length-own.length} linked claim(s) outside this Portfolio, count only`,c.id]]:[])]}) } }
  return {proved,near} }

function judge(alerts,accounts,world,opts={}){
  const off=opts.off||new Set(),extra=opts.extra||[],scope=opts.scope||'portfolio-1',seen={},all=[],near=[];
  const ts=alerts.map(a=>a.t),span=[Math.min(...ts)-7*D,Math.max(...ts)];
  for(const id of new Set(alerts.map(a=>a.acc))){ const acc=accounts[id]; if(!acc) continue; const r=proveAccount(acc,world,extra,off,scope,span); seen[id]=r.proved; all.push(...r.proved.map(p=>({...p,account:id}))); near.push(...r.near.map(n=>({...n,account:id}))) }
  const fraud=all.filter(p=>FRAUD.has(p.id));
  const uncovered=[];
  for(const a of alerts) for(const r of a.rules){ if(LEGIT_FREE.has(r)) continue;
    const here=seen[a.acc]||[];
    const ok=(r==='new_device'&&here.some(p=>p.id==='verified_device_change'&&(!a.d||p.device===a.d)))||(r==='new_beneficiary'&&here.some(p=>p.id==='established_payee'&&p.subject===a.b));
    if(!ok) uncovered.push(`${a.id}: ${r}`) }
  const legit=all.filter(p=>!FRAUD.has(p.id));
  const required=fraud.length?'suspicious':(!uncovered.length&&legit.length?'not_suspicious':'none');
  return {required,proved:all,near,uncovered} }
if(typeof module!=='undefined') module.exports={judge,NAMES,FRAUD};
