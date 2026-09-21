/* DELISA v1.10 — micro UX and product selection restoration. No dependencies. */
(()=>{'use strict';
 const main=document.querySelector('#page-root');if(!main)return;
 // Remember non-sensitive product UI state so a real browser reload restores it.
 const key=()=>location.pathname.startsWith('/product/')?'delisa-product-v110:'+location.pathname:null;
 function saveProduct(){const k=key(),gallery=main.querySelector('.detail-gallery');if(!k||!gallery)return;
  const selected=main.querySelector('.color-option.is-selected');const photo=gallery.querySelector('.gallery-thumb.is-active');
  const quantity=main.querySelector('#product-qty');
  try{sessionStorage.setItem(k,JSON.stringify({color:selected?.dataset.selectColor||'',photo:Number(photo?.dataset.galleryIndex||0),qty:Math.max(1,Math.min(99,Number(quantity?.value||1)))}))}catch{}
 }
 function restoreProduct(){const k=key(),gallery=main.querySelector('.detail-gallery');if(!k||!gallery)return;
  let state;try{state=JSON.parse(sessionStorage.getItem(k)||'null')}catch{return}if(!state)return;
  if(state.color){const button=Array.from(main.querySelectorAll('[data-select-color]')).find(b=>b.dataset.selectColor===state.color);if(button&&!button.classList.contains('is-selected'))button.click()}
  if(Number.isInteger(state.photo)&&state.photo>=0){const photo=gallery.querySelector('[data-gallery-index="'+state.photo+'"]');if(photo&&!photo.classList.contains('is-active'))photo.click()}
  const qty=main.querySelector('#product-qty');if(qty&&Number.isFinite(state.qty))qty.value=String(Math.max(1,Math.min(Number(qty.max||99),state.qty)));
 }
 restoreProduct();
 let pending=false;
 const observer=new MutationObserver(()=>{
  if(pending)return;pending=true;queueMicrotask(()=>{pending=false;restoreProduct()});
 });
 // Only direct children: avoid work on every cart/search and minor DOM update.
 observer.observe(main,{childList:true});
 document.addEventListener('click',e=>{
  if(e.target.closest?.('[data-gallery-index],[data-select-color],[data-qty-step]'))queueMicrotask(saveProduct);
  const link=e.target.closest?.('a[href]');if(link&&key())saveProduct();
 });
 document.addEventListener('change',e=>{if(e.target.id==='product-qty')saveProduct()});
 window.addEventListener('pagehide',saveProduct);
 const saveScroll=()=>{try{sessionStorage.setItem('delisa-v110-scroll',JSON.stringify({path:location.pathname+location.search,y:window.scrollY}))}catch{}};
 window.addEventListener('pagehide',saveScroll);
 window.addEventListener('pageshow',event=>{if(event.persisted){document.documentElement.classList.remove('delisa-loading');restoreProduct()}});
 // Lightweight enhancement: native filters still work without JavaScript.
 document.addEventListener('change',event=>{
  const el=event.target;if(!el.matches?.('#shop-filter select'))return;
  const form=el.form;if(form?.requestSubmit)form.requestSubmit();
 });
 document.addEventListener('keydown',event=>{
  if(event.key!=='Escape')return;const details=document.querySelector('#shop-filter-details[open]');if(details)details.open=false;
 });
 document.addEventListener('click',event=>{
  const details=document.querySelector('#shop-filter-details[open]');
  if(details&&!details.contains(event.target))details.open=false;
 });
})();