const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function api(path, options={}) {
  const res = await fetch(path, {headers:{"Content-Type":"application/json"}, ...options});
  const data = await res.json().catch(()=>({detail:"Unexpected response"}));
  if(!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}
function fmt(s){return s ? new Date(s).toLocaleString() : "—"}
async function refresh(){
  try {
    const [tasks, contributors] = await Promise.all([api("/api/tasks"),api("/api/contributors")]);
    const counts = {total:tasks.length, assigned:tasks.filter(t=>t.status==="assigned").length, pending:tasks.filter(t=>["queued","routing"].includes(t.status)).length, attention:tasks.filter(t=>["unresolved","unassigned","failed"].includes(t.status)).length};
    $("#stats").innerHTML = [["Total tasks",counts.total],["Assigned",counts.assigned],["Routing",counts.pending],["Needs attention",counts.attention]].map(([a,b])=>`<div class="stat"><span>${a}</span><strong>${b}</strong></div>`).join("");
    $("#tasks").innerHTML = tasks.length ? tasks.map(t=>`<tr>
      <td>${esc(t.title)}<div class="muted">#${t.id} · ${esc(t.priority)} priority</div></td>
      <td>${esc(t.expertise)}</td><td>${esc(t.assignee_name||"—")}</td>
      <td><span class="status ${esc(t.status)}">${esc(t.status)}</span></td><td>${fmt(t.created_at)}</td>
      <td><button class="small-btn secondary" onclick="details(${t.id})">History</button>
      ${["unresolved","unassigned","failed","queued"].includes(t.status)?`<button class="small-btn" onclick="act(${t.id},'retry')">Retry</button>`:""}
      ${t.status==="assigned"?`<button class="small-btn secondary" onclick="act(${t.id},'complete')">Complete</button><button class="small-btn secondary" onclick="decline(${t.id})">Decline</button>`:""}
      ${!["completed","cancelled"].includes(t.status)?`<button class="small-btn danger" onclick="act(${t.id},'cancel')">Cancel</button>`:""}
      </td></tr>`).join("") : `<tr><td colspan="6" class="empty">No tasks yet. Create one above.</td></tr>`;
    $("#contributors").innerHTML = contributors.map(c=>`<span class="chip"><strong>${esc(c.name)}</strong><br><span class="muted">${esc(c.expertise)}</span></span>`).join("");
  } catch(e) { $("#form-message").textContent = e.message; }
}
$("#task-form").addEventListener("submit", async e=>{
  e.preventDefault(); const form=e.currentTarget; const data=Object.fromEntries(new FormData(form));
  $("#form-message").textContent="Creating task…";
  try { const out=await api("/api/tasks",{method:"POST",body:JSON.stringify(data)}); form.reset(); $("#form-message").textContent=`Task #${out.id} created. Refresh in 5–20 seconds to see routing result.`; await refresh(); }
  catch(err){$("#form-message").textContent=err.message}
});
$("#contributor-form").addEventListener("submit", async e=>{
  e.preventDefault(); const form=e.currentTarget;
  try {await api("/api/contributors",{method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(form)))});form.reset();await refresh()}
  catch(err){alert(err.message)}
});
$("#refresh").onclick=refresh;
$("#close-details").onclick=()=>$("#details-panel").hidden=true;
window.act=async(id,action)=>{
  let contributor_id=null;
  if(action==="reassign"){
    contributor_id=Number(prompt("Enter contributor ID:"));
    if(!contributor_id)return;
  }
  try {await api(`/api/tasks/${id}/intervene`,{method:"POST",body:JSON.stringify({action,contributor_id,note:"Operator action from dashboard"})});await refresh();if(!$("#details-panel").hidden)await details(id)}
  catch(e){alert(e.message)}
};
window.decline=async id=>{try{await api(`/api/tasks/${id}/decline`,{method:"POST"});await refresh()}catch(e){alert(e.message)}};
window.details=async id=>{
  try {
    const d=await api(`/api/tasks/${id}`); $("#details-panel").hidden=false; $("#detail-title").textContent=`Task #${id}: ${d.task.title}`;
    const assignments=d.assignments.map(a=>`<div class="event"><strong>Assignment: ${esc(a.status)} · ${esc(a.contributor_name)}</strong>${esc(a.reason)}<div class="muted">${fmt(a.created_at)}${a.ended_at?" · ended "+fmt(a.ended_at):""}</div></div>`).join("");
    const events=d.events.map(ev=>`<div class="event"><strong>${esc(ev.event_type.replaceAll("_"," "))}</strong>${esc(ev.detail)}<div class="muted">${fmt(ev.created_at)}</div></div>`).join("");
    const contributorOptions=(await api("/api/contributors")).filter(c=>c.active).map(c=>`<option value="${c.id}">${esc(c.name)} — ${esc(c.expertise)}</option>`).join("");
    $("#details").innerHTML=`<p><strong>Status:</strong> ${esc(d.task.status)} · <strong>Expertise:</strong> ${esc(d.task.expertise)}</p>
      ${d.task.status!=="completed"&&d.task.status!=="cancelled"?`<form id="reassign-form" class="inline-form" style="margin:12px 0"><select name="contributor_id" required><option value="">Choose matching contributor</option>${contributorOptions}</select><button type="submit">Manual reassign</button></form>`:""}
      <h3>Assignment history</h3>${assignments||'<p class="muted">No assignments yet.</p>'}<h3>Audit events</h3>${events||'<p class="muted">No events yet.</p>'}`;
    const rf=$("#reassign-form"); if(rf)rf.onsubmit=async ev=>{ev.preventDefault();try{await api(`/api/tasks/${id}/intervene`,{method:"POST",body:JSON.stringify({action:"reassign",contributor_id:Number(new FormData(rf).get("contributor_id")),note:"Manual reassignment from task history"})});await refresh();await details(id)}catch(err){alert(err.message)}};
    $("#details-panel").scrollIntoView({behavior:"smooth",block:"start"});
  } catch(e){alert(e.message)}
};
refresh(); setInterval(refresh,12000);
