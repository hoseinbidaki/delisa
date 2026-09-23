
/* DELISA v1.22 — lightweight homepage slider and motion sections */
(()=>{
  'use strict';
  let bootedPath='';
  function initReveals(root){
    const items=[...root.querySelectorAll('.home-reveal:not([data-reveal-bound])')];
    if(!items.length)return;
    const prefersReduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(prefersReduced || !('IntersectionObserver' in window)){
      items.forEach(el=>{el.dataset.revealBound='1';el.classList.add('is-visible')});
      return;
    }
    const io=new IntersectionObserver(entries=>{
      entries.forEach(entry=>{
        if(entry.isIntersecting){entry.target.classList.add('is-visible');io.unobserve(entry.target)}
      })
    },{rootMargin:'0px 0px -10% 0px',threshold:.12});
    items.forEach(el=>{el.dataset.revealBound='1';io.observe(el)});
  }
  function initHomeSlider(root){
    const slider=root.querySelector('[data-home-slider]');
    if(!slider || slider.dataset.bound==='1')return;
    slider.dataset.bound='1';
    const slides=[...slider.querySelectorAll('[data-slide]')];
    const dots=[...slider.querySelectorAll('[data-slide-dot]')];
    const prev=slider.querySelector('[data-slider-prev]');
    const next=slider.querySelector('[data-slider-next]');
    const progress=slider.querySelector('[data-slider-progress]');
    if(!slides.length)return;
    let index=Math.max(0,slides.findIndex(s=>s.classList.contains('is-active')));
    if(index<0)index=0;
    let timer=0, started=0;
    const duration=5600;
    const setSlide=(i, user=false)=>{
      index=(i+slides.length)%slides.length;
      slides.forEach((slide,idx)=>slide.classList.toggle('is-active', idx===index));
      dots.forEach((dot,idx)=>dot.classList.toggle('is-active', idx===index));
      if(progress){
        progress.style.transition='none';
        progress.style.width='0%';
        requestAnimationFrame(()=>{
          requestAnimationFrame(()=>{
            progress.style.transition=`width ${duration}ms linear`;
            progress.style.width='100%';
          })
        });
      }
      if(user)restart();
    };
    const tick=()=>setSlide(index+1);
    const stop=()=>{if(timer){clearInterval(timer);timer=0}};
    const start=()=>{if(timer||slides.length<2)return;setSlide(index);started=Date.now();timer=setInterval(tick,duration)};
    const restart=()=>{stop();start()};
    prev?.addEventListener('click',()=>setSlide(index-1,true));
    next?.addEventListener('click',()=>setSlide(index+1,true));
    dots.forEach((dot,idx)=>dot.addEventListener('click',()=>setSlide(idx,true)));
    slider.addEventListener('mouseenter',stop);
    slider.addEventListener('mouseleave',start);
    slider.addEventListener('focusin',stop);
    slider.addEventListener('focusout',start);
    document.addEventListener('visibilitychange',()=>{document.hidden?stop():start()});
    setSlide(index); start();
  }
  function initLookbook(root){
    const track=root.querySelector('[data-lookbook-track]');
    if(!track || track.dataset.bound==='1')return;
    track.dataset.bound='1';
    const prev=root.querySelector('[data-lookbook-prev]');
    const next=root.querySelector('[data-lookbook-next]');
    const amount=()=>Math.max(260, Math.round(track.clientWidth*0.82));
    prev?.addEventListener('click',()=>track.scrollBy({left:-amount(),behavior:'smooth'}));
    next?.addEventListener('click',()=>track.scrollBy({left:amount(),behavior:'smooth'}));
  }
  function boot(){
    const root=document.querySelector('.home-v122');
    const path=location.pathname+location.search+document.querySelector('#page-root')?.innerHTML.length;
    if(!root){bootedPath='';return}
    if(root.dataset.booted==='1' && bootedPath===path)return;
    root.dataset.booted='1';bootedPath=path;
    initReveals(root);initHomeSlider(root);initLookbook(root);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
  const pageRoot=document.querySelector('#page-root');
  if(pageRoot && 'MutationObserver' in window){
    new MutationObserver(()=>{boot()}).observe(pageRoot,{childList:true,subtree:false});
  }
})();
