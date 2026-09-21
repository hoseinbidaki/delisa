"""Generate tasteful placeholder fashion illustrations, not product photography."""
from pathlib import Path
ART=Path(__file__).resolve().parent/'static'/'img'
ART.mkdir(parents=True,exist_ok=True)

def svg(body, bg='#e4ddd2',width=700,height=875):
 return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="{bg}"/><stop offset="1" stop-color="#ccc3b5"/></linearGradient>
<linearGradient id="fabric" x2="0" y2="1"><stop stop-color="#f4efe6"/><stop offset="1" stop-color="#d7cbb9"/></linearGradient>
<linearGradient id="navy" x2="0" y2="1"><stop stop-color="#293649"/><stop offset="1" stop-color="#111c2b"/></linearGradient>
<filter id="shadow"><feGaussianBlur stdDeviation="27"/></filter>
</defs><rect width="100%" height="100%" fill="url(#bg)"/><ellipse cx="345" cy="784" rx="180" ry="26" opacity=".17" filter="url(#shadow)"/>
<circle cx="105" cy="90" r="180" fill="#fff" opacity=".16"/><rect x="24" y="24" width="652" height="827" fill="none" stroke="#fff" opacity=".33"/>
{body}<text x="38" y="828" fill="#695e55" font-family="Georgia,serif" font-size="20" letter-spacing="5" opacity=".75">DELISA</text></svg>'''

face='''<path d="M330 188c-36 0-58 25-59 70-2 29 16 62 57 67 42-3 58-36 58-67-1-42-23-70-56-70z" fill="#a98571"/><path d="M270 251c0-49 18-77 61-77 51 0 63 42 60 84-10-13-19-18-27-38-29 26-61 32-94 31z" fill="#292925"/><path d="M307 317v54l48 1v-58z" fill="#a98571"/>
<path d="M278 270q-20 78-45 112" stroke="#25231f" stroke-width="26" stroke-linecap="round" fill="none" opacity=".95"/>'''
neck='''<path d="M307 348q24 28 49 0l15 19-41 55-40-55z" fill="#c6a18b"/>'''
vest='''<path d="M283 349l-68 38-37 263 86 20 15-155 10 212h114l8-211 19 155 82-22-39-264-72-36-57 47z" fill="url(#fabric)" stroke="#c3b5a3" stroke-width="2"/>
<path d="M283 349l49 90 43-88-25-12-18 40-26-41z" fill="#ddd2c2" stroke="#baac9b" stroke-width="2"/>
<path d="M330 439v280M252 606h48M380 608h49" stroke="#b0a18d" stroke-width="2" fill="none"/>
<circle cx="342" cy="479" r="3.5" fill="#a4988a"/><circle cx="342" cy="533" r="3.5" fill="#a4988a"/><circle cx="342" cy="585" r="3.5" fill="#a4988a"/>'''
shirt='''<path d="M286 348l-95 50-25 179 72 19 35-107-5 240h143l-5-240 35 107 72-19-25-179-95-50-52 45z" fill="url(#navy)" stroke="#344259" stroke-width="2"/>
<path d="M285 346l45 99-57 57-8-137zM390 346l-60 99 55 57 16-137z" fill="#35435b" stroke="#536077" stroke-width="2"/>
<path d="M329 445v280" stroke="#687084" stroke-width="1.5"/><g fill="#b7aca0"><circle cx="338" cy="488" r="2.5"/><circle cx="338" cy="543" r="2.5"/><circle cx="338" cy="599" r="2.5"/></g>'''
pants='''<path d="M215 230h280l24 125-62 418-91-4-38-282-42 282-95 4-46-420z" fill="url(#fabric)" stroke="#b4a995" stroke-width="2"/>
<path d="M206 274h291M328 324v160M230 680l65 5M376 685l66-5" stroke="#b9ab97" stroke-width="2"/><path d="M300 249h47v23h-47z" fill="#b2a48e"/>'''
setbody='''<path d="M281 349l-68 40-28 206 74 13 17-109 2 127h135l4-127 17 109 74-13-28-206-68-40-58 49z" fill="url(#navy)" stroke="#344259" stroke-width="2"/>
<path d="M285 350l45 91-48 45-13-118zM385 350l-55 91 48 45 21-118z" fill="#35445c"/><path d="M275 595h141l49 190h-88l-44-139-42 139h-95z" fill="#28364a" stroke="#354259" stroke-width="2"/>'''

for name,body,bg in [
 ('vest',face+neck+vest,'#e9e0d4'),('shirt',face+neck+shirt,'#d8d4ce'),
 ('pants',pants,'#e5ddd0'),('set',face+neck+setbody,'#d4cec3'),
 ('vest2',face+neck+vest,'#d4c9bc'),('shirt2',face+neck+shirt,'#e0d8ca')]:
 (ART/(name+'.svg')).write_text(svg(body,bg),encoding='utf-8')
hero='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 780" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="g"><stop stop-color="#bcb1a5"/><stop offset="1" stop-color="#ece3d5"/></linearGradient><linearGradient id="dress" x2="0" y2="1"><stop stop-color="#f6f0e6"/><stop offset="1" stop-color="#d8cbb8"/></linearGradient></defs>
<rect width="1500" height="780" fill="url(#g)"/><path d="M0 640L1500 490v290H0z" fill="#bcb0a1" opacity=".23"/><circle cx="1020" cy="320" r="390" fill="#fff" opacity=".11"/>
<path d="M990 230c-110 0-159 77-147 210l-60 340h452l-60-344c0-133-57-206-185-206z" fill="#33312c"/>
<path d="M975 163c-75 0-101 57-97 133 4 87 56 137 121 137 66-7 100-63 96-138-5-72-47-132-120-132z" fill="#ba9179"/>
<path d="M859 260c-7-126 57-176 138-165 90 4 136 70 118 180-28-29-28-78-40-104-47 54-112 81-216 89z" fill="#2d2926"/>
<path d="M961 407v50l83 2v-55" fill="#ba9179"/>
<path d="M945 442L824 500 752 780h495l-67-280-131-58-53 69z" fill="url(#dress)"/>
<path d="M945 442l48 95 56-95 38 21-94 153-89-153z" fill="#ede5d8"/><path d="M993 536v244M832 625h85M1071 625h101" stroke="#b9aa98" stroke-width="2"/>
<path d="M812 505c-34 21-60 88-86 200M1191 505c42 42 64 106 91 190" stroke="#ba9179" stroke-width="32" fill="none" stroke-linecap="round"/>
<rect x="0" y="0" width="1500" height="780" fill="none" stroke="#fff" opacity=".2" stroke-width="22"/></svg>'''
(ART/'hero.svg').write_text(hero,encoding='utf-8')
edit='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 900"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#b9b0a7"/><stop offset="1" stop-color="#eee4d6"/></linearGradient></defs><rect width="1000" height="900" fill="url(#g)"/><ellipse cx="520" cy="830" rx="300" ry="45" fill="#8d8173" opacity=".12"/><path d="M515 120c-72 0-121 62-120 145 0 88 40 152 123 157 83-9 121-76 116-158-4-80-44-144-119-144z" fill="#ad8774"/><path d="M397 265c-20-138 36-215 132-212 94 2 143 79 117 213-37-39-48-79-51-105-51 56-112 83-198 104z" fill="#25272a"/><path d="M467 408v70l100 2v-78z" fill="#ad8774"/><path d="M460 473L298 558l-75 342h583l-72-342-172-85-49 95z" fill="#1c293d"/><path d="M458 474l53 114 49-114 55 30-107 181-100-181z" fill="#33425a"/><path d="M505 590v305M365 758h82M609 757h84" stroke="#566276" stroke-width="2"/><text x="58" y="845" fill="#fff" font-family="Georgia" font-size="34" letter-spacing="9" opacity=".75">DELISA</text></svg>'''
(ART/'editorial.svg').write_text(edit,encoding='utf-8')
(ART/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#18243a"/><text x="32" y="46" font-family="Georgia" font-size="43" text-anchor="middle" fill="#f5f0e8">D</text></svg>',encoding='utf-8')
print('Generated SVG placeholders')
