/* Progressive enhancement only; the Python backend validates the final order. */
(()=>{'use strict';
const form=document.querySelector('.checkout-form');if(!form)return;
const input=form.querySelector('#coupon-code'),apply=form.querySelector('#coupon-apply'),feedback=document.querySelector('#coupon-feedback'),total=document.querySelector('#coupon-total'),savings=document.querySelector('#coupon-savings'),saving=document.querySelector('#coupon-discount'),subtotal=document.querySelector('#coupon-subtotal');
if(!input||!apply||!feedback||!total||!savings||!saving||!subtotal)return;
const money=n=>new Intl.NumberFormat('fa-IR').format(n)+' تومان';let latest=0;
function say(text,state=''){feedback.textContent=text;feedback.classList.remove('good','bad');if(state)feedback.classList.add(state)}
input.addEventListener('input',()=>{latest++;apply.disabled=false;savings.hidden=true;total.textContent=subtotal.textContent;say('برای اعمال کد، دکمه «اعمال کد» را بزن.');});
apply.addEventListener('click',async()=>{const id=++latest;apply.disabled=true;say('در حال بررسی کد...');try{
const resp=await fetch('/api/coupon/preview',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]')?.content||''},body:JSON.stringify({code:input.value.trim()})});
const data=await resp.json();if(id!==latest)return;if(!resp.ok)throw Error(data.error||'کد قابل استفاده نیست.');
total.textContent=money(data.total);savings.hidden=!data.discount;saving.textContent='− '+money(data.discount);say(data.discount?'تخفیف اعمال شد؛ مبلغ نهایی هنگام ثبت سفارش دوباره بررسی می‌شود.':'کدی وارد نشده است.',data.discount?'good':'');
}catch(err){if(id!==latest)return;savings.hidden=true;total.textContent=subtotal.textContent;say(err.message||'بررسی کد ممکن نشد.','bad')}finally{if(id===latest)apply.disabled=false}});
})();
