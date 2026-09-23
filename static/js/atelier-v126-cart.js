/* DELISA v1.26 — enhance the existing live cart, never replace cart logic. */
(()=>{
  'use strict';
  function init(){
    const foot=document.querySelector('#cart-foot');
    const cart=document.querySelector('#cart-drawer');
    if(!foot||!cart||foot.dataset.delisaActionsBound==='1')return;
    foot.dataset.delisaActionsBound='1';
    function update(){
      // The app recreates this footer after every cart change. Enhance each render.
      const checkout=foot.querySelector('a[href="/checkout"],a[href^="/checkout?"]');
      if(!checkout)return;
      checkout.classList.add('dl-cart-checkout');
      if(checkout.textContent.trim()!=='تکمیل سفارش ←')checkout.textContent='تکمیل سفارش ←';
      if(foot.querySelector('.dl-cart-continue'))return;
      const keepShopping=document.createElement('button');
      keepShopping.type='button';
      keepShopping.className='dl-cart-continue btn';
      keepShopping.textContent='ادامه خرید';
      keepShopping.setAttribute('aria-label','بستن سبد و ادامه مشاهده محصولات');
      keepShopping.addEventListener('click',()=>{
        // Same trusted close handler as the drawer’s × button: clears overlay,
        // unlocks scroll, closes sheet, and leaves the current page unchanged.
        const close=cart.querySelector('.drawer-top [data-close]');
        if(close){close.click();return}
        cart.classList.remove('open');
        cart.setAttribute('aria-hidden','true');
        const backdrop=document.querySelector('#backdrop');
        if(backdrop){backdrop.classList.remove('show');backdrop.hidden=true}
        document.body.classList.remove('lock');
      });
      foot.append(keepShopping);
    }
    // childList only: no self-trigger from updating text or class names.
    new MutationObserver(update).observe(foot,{childList:true});
    update();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
