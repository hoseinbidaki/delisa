/* DELISA 1.19.1: delegated address form validation across normal and soft navigation. */
(()=>{'use strict';
 const normalizedPhone=value=>String(value||'').replace(/[۰-۹]/g,c=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(c)).replace(/[٠-٩]/g,c=>'٠١٢٣٤٥٦٧٨٩'.indexOf(c)).replace(/[\s\-\u200c]/g,'');
 const hideFieldError=field=>{field.removeAttribute('aria-invalid');const error=field.closest('label')?.querySelector('.address-field-error');if(error)error.remove()};
 const errorFor=(field,message)=>{field.setAttribute('aria-invalid','true');const label=field.closest('label');if(!label)return;let el=label.querySelector('.address-field-error');if(!el){el=document.createElement('small');el.className='address-field-error';label.append(el)}el.textContent=message};
 document.addEventListener('input',e=>{if(e.target.closest?.('#address-form'))hideFieldError(e.target)},true);
 document.addEventListener('change',e=>{if(e.target.closest?.('#address-form'))hideFieldError(e.target)},true);
 document.addEventListener('submit',e=>{
  const form=e.target;if(!form?.matches?.('#address-form'))return;
  const feedback=form.querySelector('.address-form-feedback'),button=form.querySelector('#address-save-button');
  const fields={recipient:form.elements.namedItem('recipient'),phone:form.elements.namedItem('phone'),province:form.elements.namedItem('province'),city:form.elements.namedItem('city'),address:form.elements.namedItem('address')};
  for(const field of Object.values(fields))hideFieldError(field);
  if(feedback){feedback.hidden=true;feedback.textContent=''}
  const number=normalizedPhone(fields.phone.value);fields.phone.value=number;
  const errors=[];
  if(!fields.recipient.value.trim())errors.push([fields.recipient,'نام گیرنده را وارد کن.']);
  if(!/^(?:\+98|0)?9[0-9]{9}$/.test(number))errors.push([fields.phone,'شماره موبایل معتبر وارد کن؛ مثل ۰۹۱۲۳۴۵۶۷۸۹.']);
  if(!fields.province.value.trim())errors.push([fields.province,'استان را انتخاب کن.']);
  if(!fields.city.value.trim())errors.push([fields.city,'نام شهر را وارد کن.']);
  if(fields.address.value.trim().length<8)errors.push([fields.address,'نشانی دقیق باید حداقل ۸ کاراکتر باشد.']);
  if(errors.length){
   e.preventDefault();for(const [field,message] of errors)errorFor(field,message);
   if(feedback){feedback.textContent='لطفاً موارد مشخص‌شده را اصلاح کن تا آدرس ذخیره شود.';feedback.hidden=false;feedback.scrollIntoView({behavior:'smooth',block:'center'})}
   setTimeout(()=>{button?.classList.remove('is-busy','is-address-saving');button?.removeAttribute('aria-busy')},220);
   errors[0][0].focus({preventScroll:true});return;
  }
  if(button){button.classList.add('is-address-saving');button.setAttribute('aria-busy','true')}
 },true);
})();
