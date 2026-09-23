/* DELISA v1.27 — tiny auth interactions, delegated for native/soft navigation. */
(()=>{'use strict';
 document.addEventListener('click',e=>{
   const button=e.target.closest('[data-dl-password-toggle]');
   if(!button)return;
   const input=document.getElementById(button.getAttribute('aria-controls'));
   if(!input)return;
   const visible=input.type==='password';
   input.type=visible?'text':'password';
   button.textContent=visible?'پنهان':'نمایش';
   button.setAttribute('aria-label',visible?'پنهان‌کردن رمز عبور':'نمایش رمز عبور');
   button.setAttribute('aria-pressed',visible?'true':'false');
 });
 document.addEventListener('submit',e=>{
   const form=e.target.closest('[data-dl-auth-form]');
   if(!form||e.defaultPrevented)return;
   const button=form.querySelector('button[type="submit"]');
   if(!button||!form.checkValidity())return;
   button.disabled=true;
   const label=button.querySelector('span');if(label)label.textContent='در حال بررسی…';
   // In case the browser cancels submission without a navigation, do not trap users.
   setTimeout(()=>{if(form.isConnected){button.disabled=false;if(label)label.textContent=form.action.endsWith('/login')?'ورود به حساب':'ساخت حساب دلیسا'}},5000);
 },true);
})();
