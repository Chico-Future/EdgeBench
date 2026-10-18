const families={
 DGC:['Device Grounding and Control','Resolve device references and execute one requested control while preserving unrelated state.'],
 MSC:['Multi-device Selection and Control','Select and control multiple targets through explicit, batch, room-dependent, and state-dependent instructions.'],
 AIR:['Ambiguity and Intent Resolution','Distinguish executable requests from under-specified intent and ask for missing information without acting.'],
 FAR:['Future Automation Registration','Register time-specific, state-driven, or combined future behavior while leaving current state unchanged.'],
 DCR:['Dialogue-context Resolution','Use dialogue history to resolve references, corrections, topic shifts, and the current request.'],
 PMU:['Personalized Memory Use','Select relevant user memory and preferences while respecting validity and superseded information.'],
 REQ:['Read-only Environment Queries','Answer structured questions about device status, counts, locations, capabilities, and comparisons without mutation.']
};
const code=document.getElementById('family-code'),title=document.getElementById('family-title'),copy=document.getElementById('family-copy');
document.querySelectorAll('.family-node').forEach(node=>node.addEventListener('click',()=>{document.querySelectorAll('.family-node').forEach(n=>n.classList.remove('selected'));node.classList.add('selected');const [t,c]=families[node.dataset.family];code.textContent=node.dataset.family;title.textContent=t;copy.textContent=c;}));
const rows=[...document.querySelectorAll('.model-row')], count=document.querySelector('.visible-count');
document.querySelectorAll('.filter').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(b=>b.classList.remove('active'));button.classList.add('active');const f=button.dataset.filter;let total=0;rows.forEach(row=>{const size=row.children[2].textContent.trim();const value=parseFloat(size);const band=Number.isFinite(value)&&(value<=1?'≤1B':value<=3?'1--3B':value<=7?'3--7B':row.dataset.platform);const show=f==='all'||(f==='local'&&row.dataset.platform!=='Server')||f===band||f===row.dataset.platform;row.hidden=!show;if(show)total++;});count.textContent=`${total} model${total===1?'':'s'}`;}));
const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting)e.target.classList.add('visible')}),{threshold:.12});document.querySelectorAll('.pulse-card,.viz-card,.family-node,.home-card').forEach(e=>observer.observe(e));
