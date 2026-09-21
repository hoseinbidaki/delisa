/* DELISA v1.5: progressive detail controls only. No library, no page-init dependence. */
(()=>{'use strict';
 const previewUrls=new WeakMap();
 document.addEventListener('change',event=>{
  const input=event.target;if(!input.matches?.('input[type=\"file\"][name=\"image\"]'))return;
  const holder=input.closest('label');if(!holder)return;
  const before=previewUrls.get(input);if(before)URL.revokeObjectURL(before);
  let image=holder.querySelector('.upload-preview-local');
  const original=input.closest('form')?.querySelector('.edit-preview:not(.upload-preview-local)');
  const file=input.files?.[0];
  if(!file||!['image/jpeg','image/png','image/webp'].includes(file.type)){image?.remove();if(original)original.hidden=false;return}
  if(!image){image=document.createElement('img');image.className='upload-preview-local';image.alt='پیش‌نمایش تصویر انتخاب‌شده';holder.append(image)}
  const url=URL.createObjectURL(file);previewUrls.set(input,url);image.src=url;
  if(original)original.hidden=true;
 });
 document.addEventListener('click',event=>{
  const reveal=event.target.closest('[data-password-toggle]');
  if(reveal){
   const input=reveal.parentElement?.querySelector('input');if(!input)return;
   const visible=input.type==='password';input.type=visible?'text':'password';
   reveal.textContent=visible?'پنهان':'نمایش';reveal.setAttribute('aria-pressed',String(visible));
   reveal.setAttribute('aria-label',visible?'پنهان کردن رمز عبور':'نمایش رمز عبور');return;
  }
  const step=event.target.closest('[data-qty-step]');if(!step)return;
  const field=document.querySelector('#product-qty');if(!field||field.disabled)return;
  const min=Number(field.min||1),max=Math.max(min,Number(field.max||9999));
  const current=Number(field.value)||min;
  field.value=String(Math.min(max,Math.max(min,current+Number(step.dataset.qtyStep))));
  field.dispatchEvent(new Event('change',{bubbles:true}));
 });
})();
