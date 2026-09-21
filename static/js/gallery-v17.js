/* DELISA v1.7: delegated gallery/color actions work after soft page navigation. */
(()=>{'use strict';
 let lightbox=null,pics=[],index=0,returnFocus=null,touchStart=null;
 const stage=()=>document.querySelector('.detail-gallery[data-gallery-json]');
 const photos=()=>{try{const a=JSON.parse(stage()?.dataset.galleryJson||'[]');return Array.isArray(a)?a:[]}catch{return []}};
 function selectPhoto(i){
   const gallery=stage(),list=photos(),photo=list[i];if(!gallery||!photo)return;
   const img=gallery.querySelector('#detail-main-photo');if(img){img.src=photo.image;img.alt='تصویر '+(i+1)+' محصول'}
   gallery.querySelector('#gallery-current').textContent=String(i+1);
   gallery.querySelectorAll('[data-gallery-index]').forEach((b,j)=>{b.classList.toggle('is-active',j===i);b.setAttribute('aria-pressed',String(j===i))});
 }
 function updateLb(){if(!lightbox||lightbox.hidden)return;const img=lightbox.querySelector('img');img.src=pics[index].image;img.alt='نمای '+(index+1)+' محصول';lightbox.querySelector('.lb-foot').textContent=(index+1)+' / '+pics.length}
 function closeLb(){if(!lightbox)return;lightbox.hidden=true;document.body.classList.remove('lb-lock');if(returnFocus?.isConnected)returnFocus.focus()}
 function openLb(button){pics=photos();if(!pics.length)return;
   const gallery=stage();index=Math.max(0,Array.from(gallery.querySelectorAll('[data-gallery-index]')).findIndex(el=>el.classList.contains('is-active')));
   if(!lightbox){lightbox=document.createElement('div');lightbox.className='delisa-lightbox';lightbox.hidden=true;lightbox.setAttribute('role','dialog');lightbox.setAttribute('aria-modal','true');lightbox.setAttribute('aria-label','تصاویر بزرگ محصول');
    lightbox.innerHTML='<button class="lb-control lb-close" type="button" aria-label="بستن">×</button><button class="lb-control lb-prev" type="button" aria-label="تصویر قبل">‹</button><div class="lb-photo-wrap"><img alt="" draggable="false"><div class="lb-foot"></div></div><button class="lb-control lb-next" type="button" aria-label="تصویر بعد">›</button>';
    document.body.append(lightbox);
    lightbox.querySelector('.lb-close').addEventListener('click',closeLb);
    lightbox.querySelector('.lb-prev').addEventListener('click',()=>{index=(index-1+pics.length)%pics.length;updateLb()});
    lightbox.querySelector('.lb-next').addEventListener('click',()=>{index=(index+1)%pics.length;updateLb()});
    lightbox.addEventListener('click',e=>{if(e.target===lightbox)closeLb()});
    lightbox.querySelector('img').addEventListener('touchstart',e=>{touchStart=e.touches[0]?.clientX??null},{passive:true});
    lightbox.querySelector('img').addEventListener('touchend',e=>{if(touchStart===null)return;const diff=(e.changedTouches[0]?.clientX??touchStart)-touchStart;touchStart=null;if(Math.abs(diff)<45)return;index=(index+(diff>0?-1:1)+pics.length)%pics.length;updateLb()},{passive:true});
   }
   returnFocus=button;lightbox.hidden=false;document.body.classList.add('lb-lock');updateLb();lightbox.querySelector('.lb-close').focus();
 }
 document.addEventListener('click',e=>{
   const thumb=e.target.closest('[data-gallery-index]');if(thumb){selectPhoto(Number(thumb.dataset.galleryIndex));return}
   const zoom=e.target.closest('[data-open-lightbox]');if(zoom){openLb(zoom);return}
   const color=e.target.closest('[data-select-color]');if(color){
     const wrapper=color.closest('.product-colors');if(!wrapper)return;
     wrapper.querySelectorAll('[data-select-color]').forEach(btn=>{const selected=btn===color;btn.classList.toggle('is-selected',selected);btn.setAttribute('aria-pressed',String(selected))});
     wrapper.querySelector('#current-color').textContent=color.dataset.selectColor;
     const list=photos();const idx=list.findIndex(p=>p.color===color.dataset.selectColor);if(idx>=0)selectPhoto(idx);
   }
 });
 document.addEventListener('keydown',e=>{if(!lightbox||lightbox.hidden)return;
   if(e.key==='Escape'){e.preventDefault();closeLb()}
   if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();index=(index+(e.key==='ArrowRight'?-1:1)+pics.length)%pics.length;updateLb()}
 });
})();
