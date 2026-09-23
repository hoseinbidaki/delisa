/* DELISA 1.19.2 · checkout discount and saved-address interaction.
   One delegated handler: works after app-like navigation. No dependencies. */
(()=>{'use strict';
const byId=id=>document.getElementById(id);
const money=n=>new Intl.NumberFormat('fa-IR').format(n)+' تومان';
const panels=()=>({form:byId('delisa-checkout'),input:byId('coupon-code'),button:byId('coupon-apply'),message:byId('coupon-feedback'),subtotal:byId('coupon-subtotal'),total:byId('coupon-total'),savings:byId('coupon-savings'),discount:byId('coupon-discount')});
let seq=0,controller=null;
function setStatus(message,state=''){
 const p=byId('coupon-feedback');if(!p)return;
 p.textContent=message;p.classList.toggle('good',state==='good');p.classList.toggle('bad',state==='bad');
}
function resetPreview(){const p=panels();if(!p.input)return;
 seq++;controller?.abort();controller=null;
 if(p.total&&p.subtotal)p.total.textContent=p.subtotal.textContent;
 if(p.savings)p.savings.hidden=true;
 if(p.button){p.button.disabled=false;p.button.classList.remove('is-checking');p.button.removeAttribute('aria-busy')}
 setStatus('برای دیدن مبلغ نهایی، «بررسی کد» رو بزن.');
}
function updateAddressMode(){const form=byId('delisa-checkout');if(!form)return;
 const chosen=form.querySelector('input[name="saved_address_id"]:checked');
 const manual=form.querySelector('#checkout-manual-option');
 if(!chosen&&manual)manual.checked=true;
 const useSaved=!!(form.querySelector('input[name="saved_address_id"]:checked')?.value);
 const section=byId('checkout-manual-fields');if(!section)return;
 section.classList.toggle('is-disabled',useSaved);section.classList.toggle('is-muted',useSaved);
 section.querySelectorAll('input,select,textarea').forEach(el=>{el.disabled=useSaved});
}
async function checkCode(){const p=panels();if(!p.form||!p.input||!p.button||!p.total||!p.savings)return;
 const code=p.input.value.trim();if(!code){resetPreview();setStatus('اول کد تخفیف رو وارد کن.','bad');p.input.focus();return;}
 const id=++seq;controller?.abort();controller=new AbortController();p.button.disabled=true;p.button.classList.add('is-checking');p.button.setAttribute('aria-busy','true');
 setStatus('در حال بررسی کد تخفیف…');
 try{
  const resp=await fetch('/api/coupon/preview',{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content||''},body:JSON.stringify({code})});
  const data=await resp.json();if(id!==seq||!document.contains(p.form))return;
  if(!resp.ok)throw new Error(data.error||'امکان استفاده از این کد نیست.');
  p.total.textContent=money(data.total);p.savings.hidden=!data.discount;
  if(p.discount)p.discount.textContent='− '+money(data.discount);
  setStatus(data.discount?'کد معتبره و تخفیف روی مبلغ نمایشی اعمال شد.':'کدی وارد نشده است.',data.discount?'good':'');
 }catch(err){if(id!==seq||err.name==='AbortError')return;
  if(p.subtotal)p.total.textContent=p.subtotal.textContent;p.savings.hidden=true;
  setStatus(err.message||'اتصال برقرار نشد. دوباره تلاش کن.','bad');
 }finally{if(id===seq&&document.contains(p.form)){p.button.disabled=false;p.button.classList.remove('is-checking');p.button.removeAttribute('aria-busy')}}
}
document.addEventListener('click',e=>{if(e.target.closest('#coupon-apply')){e.preventDefault();checkCode()}});
document.addEventListener('input',e=>{if(e.target.matches?.('#coupon-code'))resetPreview()});
document.addEventListener('keydown',e=>{if(e.target.matches?.('#coupon-code')&&e.key==='Enter'){e.preventDefault();checkCode()}});
document.addEventListener('change',e=>{if(e.target.matches?.('#delisa-checkout input[name="saved_address_id"]'))updateAddressMode()});
/* Observe only the main child list; do not walk the DOM or run on scroll. */
const root=byId('page-root');if(root)new MutationObserver(()=>{if(byId('delisa-checkout'))updateAddressMode()}).observe(root,{childList:true});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',updateAddressMode,{once:true});else updateAddressMode();
})();